"""SQLite persistence for imported activity summaries."""

import json
import hashlib
from pathlib import Path
import sqlite3
from typing import Literal
from datetime import date, datetime

from .models import Activity


class ActivityRepository:
    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

    def initialize(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS activities (
                    activity_id TEXT PRIMARY KEY,
                    started_at TEXT NOT NULL,
                    activity_type TEXT NOT NULL,
                    distance_m REAL,
                    duration_s REAL,
                    elevation_gain_m REAL,
                    average_heart_rate_bpm REAL,
                    source_json TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS activity_streams (
                    activity_id TEXT PRIMARY KEY,
                    downloaded_zip BLOB NOT NULL,
                    sha256 TEXT NOT NULL,
                    points_json TEXT NOT NULL
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS wellness_snapshots (
                    source TEXT NOT NULL,
                    start_date TEXT NOT NULL,
                    end_date TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    PRIMARY KEY (source, start_date, end_date)
                )"""
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS training_plans (
                    plan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    prompt TEXT NOT NULL,
                    title TEXT NOT NULL,
                    goal TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )"""
            )

    def upsert(self, activity: Activity) -> Literal["inserted", "updated", "unchanged"]:
        source_json = json.dumps(activity.source_fields, sort_keys=True, separators=(",", ":"))
        row = (
            activity.started_at.isoformat(), activity.activity_type, activity.distance_m,
            activity.duration_s, activity.elevation_gain_m, activity.average_heart_rate_bpm,
            source_json,
        )
        with sqlite3.connect(self.database_path) as connection:
            existing = connection.execute(
                "SELECT started_at, activity_type, distance_m, duration_s, elevation_gain_m, average_heart_rate_bpm, source_json "
                "FROM activities WHERE activity_id = ?",
                (activity.activity_id,),
            ).fetchone()
            if existing == row:
                return "unchanged"
            connection.execute(
                """INSERT INTO activities (
                    activity_id, started_at, activity_type, distance_m, duration_s,
                    elevation_gain_m, average_heart_rate_bpm, source_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(activity_id) DO UPDATE SET
                    started_at=excluded.started_at,
                    activity_type=excluded.activity_type,
                    distance_m=excluded.distance_m,
                    duration_s=excluded.duration_s,
                    elevation_gain_m=excluded.elevation_gain_m,
                    average_heart_rate_bpm=excluded.average_heart_rate_bpm,
                    source_json=excluded.source_json""",
                (activity.activity_id, *row),
            )
        return "inserted" if existing is None else "updated"

    def list_activities(self) -> list[Activity]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """SELECT activity_id, started_at, activity_type, distance_m, duration_s,
                          elevation_gain_m, average_heart_rate_bpm, source_json
                   FROM activities ORDER BY started_at"""
            ).fetchall()
        return [
            Activity(
                activity_id=row[0], started_at=datetime.fromisoformat(row[1]), activity_type=row[2],
                distance_m=row[3], duration_s=row[4], elevation_gain_m=row[5],
                average_heart_rate_bpm=row[6], source_fields=json.loads(row[7]),
            )
            for row in rows
        ]

    def latest_activity_date(self) -> date | None:
        with sqlite3.connect(self.database_path) as connection:
            result = connection.execute("SELECT MAX(started_at) FROM activities").fetchone()[0]
        return datetime.fromisoformat(result).date() if result else None

    def upsert_wellness_snapshot(self, source: str, start_date: date, end_date: date, payload) -> Literal["inserted", "updated", "unchanged"]:
        payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        with sqlite3.connect(self.database_path) as connection:
            existing = connection.execute(
                "SELECT payload_json FROM wellness_snapshots WHERE source = ? AND start_date = ? AND end_date = ?",
                (source, start_date.isoformat(), end_date.isoformat()),
            ).fetchone()
            if existing and existing[0] == payload_json:
                return "unchanged"
            connection.execute(
                """INSERT INTO wellness_snapshots(source, start_date, end_date, payload_json)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(source, start_date, end_date) DO UPDATE SET payload_json=excluded.payload_json""",
                (source, start_date.isoformat(), end_date.isoformat(), payload_json),
            )
        return "inserted" if existing is None else "updated"

    def list_wellness_snapshots(self) -> list[dict]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT source, start_date, end_date, payload_json FROM wellness_snapshots ORDER BY start_date, source"
            ).fetchall()
        return [
            {
                "source": row[0],
                "start_date": date.fromisoformat(row[1]),
                "end_date": date.fromisoformat(row[2]),
                "payload": json.loads(row[3]),
            }
            for row in rows
        ]

    def has_activity_stream(self, activity_id: str) -> bool:
        with sqlite3.connect(self.database_path) as connection:
            return connection.execute(
                "SELECT 1 FROM activity_streams WHERE activity_id = ?", (activity_id,)
            ).fetchone() is not None

    def save_activity_stream(self, activity_id: str, downloaded_zip: bytes, points: list[dict]) -> None:
        with sqlite3.connect(self.database_path) as connection:
            connection.execute(
                """INSERT OR IGNORE INTO activity_streams(activity_id, downloaded_zip, sha256, points_json)
                   VALUES (?, ?, ?, ?)""",
                (
                    activity_id,
                    sqlite3.Binary(downloaded_zip),
                    hashlib.sha256(downloaded_zip).hexdigest(),
                    json.dumps(points, sort_keys=True, separators=(",", ":")),
                ),
            )

    def get_activity_stream(self, activity_id: str) -> list[dict] | None:
        with sqlite3.connect(self.database_path) as connection:
            row = connection.execute(
                "SELECT points_json FROM activity_streams WHERE activity_id = ?", (activity_id,)
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_training_plan(self, prompt: str, plan: dict, created_at: datetime | None = None) -> int:
        created_at = created_at or datetime.now().astimezone()
        plan_json = json.dumps(plan, sort_keys=True, separators=(",", ":"))
        with sqlite3.connect(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO training_plans(prompt, title, goal, plan_json, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (prompt, plan["title"], plan["goal"], plan_json, created_at.isoformat()),
            )
            return int(cursor.lastrowid)

    def list_training_plans(self) -> list[dict]:
        with sqlite3.connect(self.database_path) as connection:
            rows = connection.execute(
                """SELECT plan_id, prompt, title, goal, plan_json, created_at
                   FROM training_plans ORDER BY created_at DESC, plan_id DESC"""
            ).fetchall()
        return [
            {
                "plan_id": row[0],
                "prompt": row[1],
                "title": row[2],
                "goal": row[3],
                "plan": json.loads(row[4]),
                "created_at": datetime.fromisoformat(row[5]),
            }
            for row in rows
        ]
