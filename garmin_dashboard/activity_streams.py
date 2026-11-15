"""One-time activity-file downloads and FIT stream extraction."""

from dataclasses import asdict, dataclass
from datetime import datetime
from io import BytesIO
import zipfile

from garmin_fit_sdk import Decoder, Stream


class ActivityStreamError(ValueError):
    """An activity file could not be decoded into useful stream records."""


@dataclass(frozen=True)
class ActivityStreamPoint:
    timestamp: datetime | None
    heart_rate_bpm: int | None
    distance_m: float | None
    speed_mps: float | None
    cadence_spm: float | None
    altitude_m: float | None

    def as_dict(self) -> dict:
        values = asdict(self)
        values["timestamp"] = self.timestamp.isoformat() if self.timestamp else None
        return values


def read_fit_messages(fit_data: bytes) -> dict:
    stream = Stream.from_byte_array(bytearray(fit_data))
    messages, errors = Decoder(stream).read()
    if errors:
        raise ActivityStreamError("Garmin FIT file could not be decoded") from errors[0]
    return messages


def parse_activity_zip(content: bytes) -> list[ActivityStreamPoint]:
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            fit_names = [name for name in archive.namelist() if name.lower().endswith(".fit")]
            if not fit_names:
                raise ActivityStreamError("Garmin activity ZIP contains no FIT file")
            fit_data = archive.read(fit_names[0])
    except zipfile.BadZipFile as exc:
        raise ActivityStreamError("Garmin activity response is not a valid ZIP file") from exc
    return parse_record_messages(read_fit_messages(fit_data))


def parse_record_messages(messages: dict) -> list[ActivityStreamPoint]:
    records = messages.get("record_mesgs", [])
    if not isinstance(records, list):
        raise ActivityStreamError("FIT decoder returned an unexpected record collection")
    points = []
    for record in records:
        if not isinstance(record, dict):
            continue
        points.append(ActivityStreamPoint(
            timestamp=_field_value(record, "timestamp"),
            heart_rate_bpm=_field_value(record, "heart_rate"),
            distance_m=_field_value(record, "distance"),
            speed_mps=_first_present(
                _field_value(record, "enhanced_speed"), _field_value(record, "speed")
            ),
            cadence_spm=_field_value(record, "cadence"),
            altitude_m=_first_present(
                _field_value(record, "enhanced_altitude"), _field_value(record, "altitude")
            ),
        ))
    return points


def sync_activity_streams(client, repository):
    from dataclasses import dataclass, field

    @dataclass
    class StreamSyncReport:
        imported: int = 0
        skipped: int = 0
        failed: int = 0
        errors: list[str] = field(default_factory=list)

    report = StreamSyncReport()
    repository.initialize()
    for activity in repository.list_activities():
        if repository.has_activity_stream(activity.activity_id):
            report.skipped += 1
            continue
        try:
            content = client.download_activity(activity.activity_id)
            points = parse_activity_zip(content)
            repository.save_activity_stream(
                activity.activity_id,
                content,
                [point.as_dict() for point in points],
            )
            report.imported += 1
        except Exception as exc:
            report.failed += 1
            report.errors.append(f"Activity {activity.activity_id}: {type(exc).__name__}")
    return report


def _field_value(record: dict, name: str):
    field = record.get(name)
    if isinstance(field, dict):
        return field.get("field_value")
    return field


def _first_present(*values):
    return next((value for value in values if value is not None), None)
