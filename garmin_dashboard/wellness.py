"""Wellness payload sync and conservative extraction for dashboard trends."""

from dataclasses import dataclass, field
from calendar import monthrange
from datetime import date, datetime, timedelta
from typing import Any


@dataclass
class WellnessSyncReport:
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WellnessMetricPoint:
    day: date
    metric: str
    value: float


def sync_wellness(client, repository, start_date: date, end_date: date) -> WellnessSyncReport:
    report = WellnessSyncReport()
    if end_date < start_date:
        report.failed = 1
        report.errors.append("End date must be on or after start date")
        return report
    repository.initialize()
    chunk_start = start_date
    while chunk_start <= end_date:
        month_end = date(
            chunk_start.year, chunk_start.month,
            monthrange(chunk_start.year, chunk_start.month)[1],
        )
        chunk_end = min(month_end, end_date)
        try:
            payloads = client.fetch_wellness(chunk_start, chunk_end)
            for source, payload in payloads.items():
                result = repository.upsert_wellness_snapshot(source, chunk_start, chunk_end, payload)
                if result == "unchanged":
                    report.skipped += 1
                else:
                    report.imported += 1
        except Exception as exc:
            report.failed += 1
            report.errors.append(
                f"Wellness sync failed for {chunk_start} through {chunk_end} ({type(exc).__name__})"
            )
        chunk_start = chunk_end + timedelta(days=1)
    return report


def wellness_metric_points(snapshots: list[dict[str, Any]]) -> list[WellnessMetricPoint]:
    """Flatten numeric daily fields without filling absent values or arrays."""
    unique_points: dict[tuple[date, str], WellnessMetricPoint] = {}
    for snapshot in snapshots:
        source = str(snapshot["source"])
        payload = snapshot["payload"]
        if isinstance(payload, dict) and isinstance(payload.get("data"), list):
            records = payload["data"]
        elif isinstance(payload, dict) and isinstance(payload.get("hrvSummaries"), list):
            records = payload["hrvSummaries"]
        elif isinstance(payload, list):
            records = payload
        else:
            records = [payload]
        for record in records:
            if not isinstance(record, dict):
                continue
            day = _record_date(record)
            if day is None:
                continue
            for path, value in _numeric_leaves(record):
                metric = f"{source}.{path}"
                unique_points.setdefault((day, metric), WellnessMetricPoint(day, metric, value))
    return sorted(unique_points.values(), key=lambda point: (point.day, point.metric))


def _record_date(record: dict[str, Any]) -> date | None:
    for key in ("calendarDate", "date"):
        value = record.get(key)
        if isinstance(value, str):
            try:
                return date.fromisoformat(value[:10])
            except ValueError:
                continue
    return None


def _numeric_leaves(value: Any, path: str = ""):
    if isinstance(value, dict):
        for key, nested in value.items():
            nested_path = f"{path}.{key}" if path else str(key)
            yield from _numeric_leaves(nested, nested_path)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        yield path, float(value)
