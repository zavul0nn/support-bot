from datetime import datetime

import pytest

from app.bot.utils.business_hours import (
    MOSCOW_TZ,
    is_within_business_hours,
    parse_hhmm,
    parse_hours_range,
)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 7, 16, hour, minute, tzinfo=MOSCOW_TZ)


def test_parse_hours_range() -> None:
    start, end = parse_hours_range("09:00-00:00")

    assert start == parse_hhmm("09:00")
    assert end == parse_hhmm("00:00")


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (_dt(8, 59), False),
        (_dt(9, 0), True),
        (_dt(23, 59), True),
        (_dt(0, 0), False),
    ],
)
def test_same_day_business_hours(current: datetime, expected: bool) -> None:
    assert is_within_business_hours(
        current,
        start=parse_hhmm("09:00"),
        end=parse_hhmm("00:00"),
        tz=MOSCOW_TZ,
    ) is expected


@pytest.mark.parametrize(
    ("current", "expected"),
    [
        (_dt(21, 59), False),
        (_dt(22, 0), True),
        (_dt(2, 59), True),
        (_dt(3, 0), False),
    ],
)
def test_overnight_business_hours(current: datetime, expected: bool) -> None:
    assert is_within_business_hours(
        current,
        start=parse_hhmm("22:00"),
        end=parse_hhmm("03:00"),
        tz=MOSCOW_TZ,
    ) is expected
