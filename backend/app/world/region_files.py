import re

REGION_FILE_RE = re.compile(r"^r\.(-?\d+)\.(-?\d+)\.mca$")


def parse_region_filename(name: str) -> tuple[int, int] | None:
    match = REGION_FILE_RE.match(name)
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))
