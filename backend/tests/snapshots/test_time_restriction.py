from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from app.routers import snapshots


@pytest.mark.parametrize("before,after", [(30, 60), (10, 20)])
@pytest.mark.parametrize("minute", [0, 15, 30, 45])
@pytest.mark.parametrize("boundary,restricted", [
    ("before_outside", False), ("before", True), ("exact", True),
    ("after", True), ("after_outside", False),
])
async def test_time_restriction_boundaries(monkeypatch, before, after, minute, boundary, restricted, runtime_config):
    offsets = {"before_outside": -before - 1, "before": -before, "exact": 0,
               "after": after, "after_outside": after + 1}
    seconds = (minute * 60 + offsets[boundary]) % 3600
    now = datetime(2024, 1, 1, 12, seconds // 60, seconds % 60).astimezone()
    monkeypatch.setattr(snapshots, "datetime", SimpleNamespace(now=lambda _: now))
    config = runtime_config.snapshots.time_restriction
    config.enabled = True
    config.before_seconds = before
    config.after_seconds = after
    monkeypatch.setattr(snapshots.get_restart_scheduler(), "get_backup_minutes", AsyncMock(return_value={0, 15, 30, 45}))

    if restricted:
        with pytest.raises(HTTPException) as raised:
            await snapshots._check_backup_time_restriction()
        assert raised.value.status_code == 400
        assert "备份时间" in raised.value.detail
    else:
        await snapshots._check_backup_time_restriction()


@pytest.mark.parametrize("enabled,minutes", [(False, {0, 15, 30, 45}), (True, set())])
async def test_disabled_or_unscheduled_restriction_allows_snapshot(monkeypatch, enabled, minutes, runtime_config):
    now = datetime(2024, 1, 1, 12, 0, 0).astimezone()
    monkeypatch.setattr(snapshots, "datetime", SimpleNamespace(now=lambda _: now))
    runtime_config.snapshots.time_restriction.enabled = enabled
    monkeypatch.setattr(snapshots.get_restart_scheduler(), "get_backup_minutes", AsyncMock(return_value=minutes))
    await snapshots._check_backup_time_restriction()
