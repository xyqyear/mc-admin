"""Unit tests for the exclude-aware snapshot coverage predicate."""

from pathlib import Path

from app.snapshots.coverage import covers

SERVER = Path("/srv/servers/alpha")
DATA = SERVER / "data"


def test_target_under_recorded_path():
    assert covers(DATA / "world", [SERVER], [])


def test_target_equal_to_recorded_path():
    assert covers(SERVER, [SERVER], [])


def test_target_outside_recorded_paths():
    assert not covers(Path("/srv/servers/beta"), [SERVER], [])


def test_exclude_equal_to_target_disqualifies():
    assert not covers(DATA / ".mcmap", [SERVER], [DATA / ".mcmap"])


def test_exclude_ancestor_of_target_disqualifies():
    assert not covers(
        DATA / ".mcmap" / "tiles" / "r.0.0.png", [SERVER], [DATA / ".mcmap"]
    )


def test_exclude_below_target_still_covers():
    # Restoring the directory is still meaningful; excluded content is
    # protected separately at restore time.
    assert covers(SERVER, [SERVER], [DATA / ".mcmap"])


def test_exclude_on_sibling_irrelevant():
    assert covers(DATA / "world", [SERVER], [DATA / "logs"])


def test_exclude_checked_before_paths():
    # Even an exact recorded-path match is disqualified by an exclude.
    assert not covers(DATA / "logs", [DATA / "logs"], [DATA / "logs"])


def test_no_paths_never_covers():
    assert not covers(DATA, [], [])
