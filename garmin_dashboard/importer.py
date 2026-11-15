"""Map documented activity summaries and synchronize them idempotently."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from .models import Activity


@dataclass
class SyncReport:
    imported: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def activity_from_api(record: dict[str, Any]) -> Activity:
    """Map available Garmin fields; retain the full original record unchanged."""
    activity_id = record.get("activityId")
    started_at = record.get("startTimeLocal") or record.get("startTimeGMT")
    activity_type = record.get("activityTypeDTO") or record.get("activityType")
    if isinstance(activity_type, dict):
        activity_type = activity_type.get("typeKey")
    activity_type = activity_type or record.get("activityTypeKey")
    if activity_id is None or not started_at or not activity_type:
        raise ValueError("Required activity ID, start time, or activity type is missing")

    try:
        parsed_date = datetime.fromisoformat(str(started_at).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Activity start time is invalid") from exc

    summary = record.get("summaryDTO")
    if not isinstance(summary, dict):
        summary = record

    def optional_number(field_name: str) -> float | None:
        value = summary.get(field_name)
        return float(value) if value is not None else None

    return Activity(
        activity_id=str(activity_id),
        started_at=parsed_date,
        activity_type=str(activity_type),
        distance_m=optional_number("distance"),
        duration_s=optional_number("duration"),
        elevation_gain_m=optional_number("elevationGain"),
        average_heart_rate_bpm=optional_number("averageHR"),
        source_fields=record,
    )


def sync_activities(client, repository) -> SyncReport:
    report = SyncReport()
    repository.initialize()
    try:
        latest_date = repository.latest_activity_date()
        # One-day overlap catches late-arriving or changed records at the sync boundary.
        start_date = latest_date - timedelta(days=1) if latest_date else None
        for record_number, record in enumerate(client.iter_activities(start_date=start_date), start=1):
            try:
                activity = activity_from_api(record)
                result = repository.upsert(activity)
            except (TypeError, ValueError, OverflowError) as exc:
                report.failed += 1
                report.errors.append(f"Record {record_number}: {exc}")
                continue
            if result == "unchanged":
                report.skipped += 1
            else:
                report.imported += 1
    except Exception as exc:
        report.failed += 1
        report.errors.append(f"Activity sync stopped ({type(exc).__name__})")
    return report
