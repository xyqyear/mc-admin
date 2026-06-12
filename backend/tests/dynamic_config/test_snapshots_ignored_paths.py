"""Validation tests for ``SnapshotsConfig.ignored_paths``."""

import pytest
from pydantic import ValidationError

from app.dynamic_config.configs.snapshots import LEVEL_NAME_TOKEN, SnapshotsConfig


def test_default_ignores_mcmap():
    assert SnapshotsConfig().ignored_paths == [".mcmap"]


def test_defaults_fill_for_stored_rows_without_the_field():
    # Simulates migration of a config row persisted before the field existed.
    migrated = SnapshotsConfig.model_validate(
        {"time_restriction": {"enabled": False}}
    )
    assert migrated.ignored_paths == [".mcmap"]
    assert migrated.time_restriction.enabled is False


@pytest.mark.parametrize(
    "value",
    [
        ["logs"],
        ["logs/latest"],
        [".mcmap", "cache/luckperms"],
        [LEVEL_NAME_TOKEN],
        [f"{LEVEL_NAME_TOKEN}/datapacks"],
        [f"backups/{LEVEL_NAME_TOKEN}/cache"],
        ["a/./b"],  # inner "." segments normalize away in PurePosixPath
        [],
    ],
)
def test_accepts_valid_paths(value):
    assert SnapshotsConfig(ignored_paths=value).ignored_paths == value


@pytest.mark.parametrize(
    "value",
    [
        ["/absolute/path"],
        [""],
        ["a/../b"],
        [".."],
        ["."],
        ["logs/*.log"],
        ["wor?d"],
        ["data[0]"],
        [f"prefix{LEVEL_NAME_TOKEN}/x"],
        [f"{LEVEL_NAME_TOKEN}suffix"],
    ],
)
def test_rejects_invalid_paths(value):
    with pytest.raises(ValidationError):
        SnapshotsConfig(ignored_paths=value)
