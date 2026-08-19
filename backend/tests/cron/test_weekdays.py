from datetime import datetime

import pytest

from app.cron.manager import CronManager
from app.cron.weekdays import normalize_crontab_weekday


@pytest.mark.parametrize(
    ("field", "expected"),
    [
        ("*", "*"),
        ("0", "6"),
        ("7", "6"),
        ("1", "0"),
        ("6", "5"),
        ("MON", "0"),
        ("mon-fri", "0,1,2,3,4"),
        ("FRI-SUN", "4,5,6"),
        ("1-5", "0,1,2,3,4"),
        ("0-2", "0,1,6"),
        ("*/2", "1,3,5,6"),
        ("1/2", "0,2,4,6"),
        ("1-7/2", "0,2,4,6"),
        ("0,6,7", "5,6"),
        ("mon,3-4,7", "0,2,3,6"),
    ],
)
def test_normalize_crontab_weekday(field: str, expected: str) -> None:
    assert normalize_crontab_weekday(field) == expected


@pytest.mark.parametrize(
    "field",
    [
        "",
        "8",
        "monkey",
        "5-1",
        "*/0",
        "*/-1",
        "1-5/0",
        "1-5/2/3",
        "1,,2",
        "1--3",
    ],
)
def test_normalize_crontab_weekday_rejects_invalid_fields(field: str) -> None:
    with pytest.raises(ValueError, match="星期字段"):
        normalize_crontab_weekday(field)


@pytest.mark.parametrize(
    ("field", "expected_weekday"),
    [
        ("1", 0),
        ("0", 6),
        ("7", 6),
        ("0-2", 6),
        ("*/2", 6),
    ],
)
def test_trigger_uses_conventional_calendar_days(
    field: str, expected_weekday: int
) -> None:
    trigger = CronManager()._build_cron_trigger(f"0 1 * * {field}")
    current = datetime(2026, 8, 15, 2, tzinfo=trigger.timezone)

    next_run = trigger.get_next_fire_time(None, current)

    assert next_run is not None
    assert next_run.weekday() == expected_weekday
    assert next_run.hour == 1
    assert next_run.minute == 0


@pytest.mark.parametrize(
    ("field", "expected_weekdays"),
    [
        ("1-5", {0, 1, 2, 3, 4}),
        ("0-2", {0, 1, 6}),
        ("*/2", {1, 3, 5, 6}),
    ],
)
def test_compound_trigger_selects_complete_calendar_day_set(
    field: str, expected_weekdays: set[int]
) -> None:
    trigger = CronManager()._build_cron_trigger(f"0 1 * * {field}")
    current = datetime(2026, 8, 15, 2, tzinfo=trigger.timezone)
    previous = None
    actual_weekdays: set[int] = set()

    for _ in expected_weekdays:
        next_run = trigger.get_next_fire_time(previous, current)
        assert next_run is not None
        actual_weekdays.add(next_run.weekday())
        previous = next_run
        current = next_run

    assert actual_weekdays == expected_weekdays
