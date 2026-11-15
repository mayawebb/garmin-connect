"""Core activity model used by the dashboard and future import pipeline."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class Activity:
    activity_id: str
    started_at: datetime
    activity_type: str
    distance_m: float | None = None
    duration_s: float | None = None
    elevation_gain_m: float | None = None
    average_heart_rate_bpm: float | None = None
    source_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.activity_id.strip():
            raise ValueError("activity_id must not be empty")
        if not self.activity_type.strip():
            raise ValueError("activity_type must not be empty")
        if not isinstance(self.started_at, datetime):
            raise ValueError("started_at must be a datetime")
        for name in ("distance_m", "duration_s", "elevation_gain_m"):
            value = getattr(self, name)
            if value is not None and value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.average_heart_rate_bpm is not None and self.average_heart_rate_bpm <= 0:
            raise ValueError("average_heart_rate_bpm must be positive")

    @property
    def distance_km(self) -> float | None:
        return self.distance_m / 1000 if self.distance_m is not None else None
