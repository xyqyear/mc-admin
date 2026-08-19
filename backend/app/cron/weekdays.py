WEEKDAY_NAMES = {
    "sun": 0,
    "mon": 1,
    "tue": 2,
    "wed": 3,
    "thu": 4,
    "fri": 5,
    "sat": 6,
}


def normalize_crontab_weekday(field: str) -> str:
    normalized = field.strip().lower()
    if normalized == "*":
        return "*"
    if not normalized:
        raise _invalid_weekday(field)

    cron_days: set[int] = set()
    for term in normalized.split(","):
        cron_days.update(_expand_term(term.strip(), field))

    if not cron_days:
        raise _invalid_weekday(field)

    apscheduler_days = sorted((day - 1) % 7 for day in cron_days)
    return ",".join(str(day) for day in apscheduler_days)


def _expand_term(term: str, field: str) -> set[int]:
    if not term:
        raise _invalid_weekday(field)

    parts = term.split("/")
    if len(parts) > 2:
        raise _invalid_weekday(field)

    base = parts[0]
    if len(parts) == 1:
        values = _expand_base(base, field)
    else:
        step = _parse_step(parts[1], field)
        values = _expand_step_base(base, field)[::step]

    return {value % 7 for value in values}


def _expand_base(base: str, field: str) -> list[int]:
    if base == "*":
        return list(range(8))
    if "-" in base:
        return _expand_range(base, field)
    return [_parse_day(base, field)]


def _expand_step_base(base: str, field: str) -> list[int]:
    if base == "*":
        return list(range(8))
    if "-" in base:
        return _expand_range(base, field)

    start = _parse_day(base, field)
    return list(range(start, 8))


def _expand_range(value: str, field: str) -> list[int]:
    parts = value.split("-")
    if len(parts) != 2 or not all(parts):
        raise _invalid_weekday(field)

    start = _parse_day(parts[0], field)
    end = _parse_day(parts[1], field)
    if parts[1] == "sun" and start > 0:
        end = 7
    if start > end:
        raise _invalid_weekday(field)

    return list(range(start, end + 1))


def _parse_day(value: str, field: str) -> int:
    if value in WEEKDAY_NAMES:
        return WEEKDAY_NAMES[value]
    if not value.isdigit():
        raise _invalid_weekday(field)

    day = int(value)
    if day > 7:
        raise _invalid_weekday(field)
    return day


def _parse_step(value: str, field: str) -> int:
    if not value.isdigit():
        raise _invalid_weekday(field)

    step = int(value)
    if step <= 0:
        raise _invalid_weekday(field)
    return step


def _invalid_weekday(field: str) -> ValueError:
    return ValueError(f"Cron 星期字段 '{field}' 无效")
