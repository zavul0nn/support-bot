from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone, tzinfo


MOSCOW_TZ = timezone(timedelta(hours=3), name="MSK")


@dataclass(frozen=True)
class BusinessHours:
    enabled: bool = True
    start: time = time(hour=9)
    end: time = time(hour=0)


def parse_hhmm(value: str) -> time:
    """Parse HH:MM into time."""
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("expected HH:MM")

    hour = int(parts[0])
    minute = int(parts[1])
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("time is out of range")

    return time(hour=hour, minute=minute)


def format_hhmm(value: time) -> str:
    """Format time as HH:MM."""
    return value.strftime("%H:%M")


def parse_hours_range(value: str) -> tuple[time, time]:
    """Parse a business-hours range like 09:00-00:00."""
    normalized = value.strip().replace(" ", "")
    separator = "-" if "-" in normalized else "–"
    parts = normalized.split(separator)
    if len(parts) != 2:
        raise ValueError("expected HH:MM-HH:MM")
    return parse_hhmm(parts[0]), parse_hhmm(parts[1])


def is_within_business_hours(
    current: datetime,
    *,
    start: time,
    end: time,
    tz: tzinfo = MOSCOW_TZ,
) -> bool:
    """Return True when current datetime falls inside the configured interval."""
    local_time = current.astimezone(tz).time().replace(second=0, microsecond=0)
    if start == end:
        return True
    if start < end:
        return start <= local_time < end
    return local_time >= start or local_time < end
