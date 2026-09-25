import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx2 import ASGITransport, AsyncClient

from app.background_tasks import (
    BackgroundTaskManager,
    TaskProgress,
    TaskStatus,
    TaskType,
)
from app.dependencies import get_current_user
from app.errors import PublicOperationError, SafeErrorMiddleware
from app.routers import snapshots


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
async def test_unexpected_task_failures_hide_credentials(error_type, caplog):
    secret = "synthetic-task-provider-password"

    async def operation():
        yield TaskProgress(progress=40, message="处理中")
        raise error_type(secret)

    manager = BackgroundTaskManager()
    with caplog.at_level(logging.DEBUG):
        submitted = manager.submit(TaskType.SERVER_REBUILD, "安全错误回归", operation())
        result = await submitted.awaitable
    assert result.error == "服务器内部错误，请稍后重试"
    assert submitted.task.status == TaskStatus.FAILED
    assert submitted.task.progress == 40
    assert submitted.task.error == result.error
    assert secret not in result.model_dump_json() + submitted.task.model_dump_json() + caplog.text
    assert error_type.__name__ in caplog.text


@pytest.mark.parametrize("error_type", [ValueError, RuntimeError])
async def test_unexpected_snapshot_sse_failures_hide_credentials(error_type, monkeypatch, caplog, tmp_path):
    secret = "synthetic-snapshot-provider-password"

    async def operation(*args):
        yield {"event_type": "start", "message": "开始恢复"}
        raise error_type(secret)

    service = SimpleNamespace(
        maintenance_servers=AsyncMock(return_value=[]),
        check_available=AsyncMock(),
        restore=operation,
    )
    monkeypatch.setattr(snapshots, "_resolve_backup_paths", AsyncMock(return_value=[tmp_path]))
    monkeypatch.setattr(snapshots, "_get_snapshot_service", lambda: object())
    monkeypatch.setattr(snapshots, "SnapshotRestoreService", lambda *args: service)
    app = FastAPI()
    app.add_middleware(SafeErrorMiddleware)
    app.include_router(snapshots.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=1)
    with caplog.at_level(logging.DEBUG):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/snapshots/restore", json={"snapshot_id": "synthetic", "server_id": "synthetic", "paths": ["/"]})
    assert response.status_code == 200
    events = [json.loads(line.removeprefix("data: ")) for line in response.text.splitlines() if line.startswith("data: ")]
    assert events[-1] == {"event_type": "error", "message": "服务器内部错误，请稍后重试"}
    assert secret not in response.text + caplog.text
    assert error_type.__name__ in caplog.text


@pytest.mark.parametrize("detail", ["服务器正在维护", {"message": "上传位置不匹配", "offset": 42}])
async def test_expected_http_errors_remain_readable_in_task_errors(detail):
    async def operation():
        yield TaskProgress(message="准备操作")
        raise HTTPException(status_code=409, detail=detail)

    manager = BackgroundTaskManager()
    result = await manager.submit(TaskType.ARCHIVE_CREATE, "契约回归", operation()).awaitable
    assert result.error is not None
    if isinstance(detail, str):
        assert result.error == detail
    else:
        assert json.loads(result.error) == detail


async def test_public_task_failure_does_not_log_its_private_cause(caplog):
    secret = "synthetic-private-task-cause"

    async def operation():
        yield TaskProgress(message="准备操作")
        try:
            raise RuntimeError(secret)
        except RuntimeError as exc:
            raise PublicOperationError("磁盘空间不足，请清理空间后重试") from exc

    with caplog.at_level(logging.DEBUG):
        result = await BackgroundTaskManager().submit(TaskType.ARCHIVE_EXTRACT, "受控错误", operation()).awaitable
    assert result.error == "磁盘空间不足，请清理空间后重试"
    assert secret not in result.model_dump_json() + caplog.text


async def test_archive_adapter_failure_keeps_useful_message_without_logging_stderr(monkeypatch, caplog, tmp_path):
    from app.utils import decompression

    secret = "synthetic-archive-command-password"
    archive = tmp_path / "synthetic.zip"
    archive.touch()
    monkeypatch.setattr(decompression, "exec_command", AsyncMock(side_effect=RuntimeError(f"Permission denied: {secret}")))
    with caplog.at_level(logging.DEBUG):
        submitted = BackgroundTaskManager().submit(
            TaskType.ARCHIVE_EXTRACT, "解压错误",
            decompression.extract_minecraft_server(str(archive), str(tmp_path / "output")),
        )
        result = await submitted.awaitable
    assert result.error == "无权限访问压缩包文件"
    assert secret not in result.model_dump_json() + submitted.task.model_dump_json() + caplog.text
