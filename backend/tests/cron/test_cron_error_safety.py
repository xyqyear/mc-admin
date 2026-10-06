from unittest.mock import AsyncMock

import httpx2
import pytest
from fastapi import FastAPI
from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from app.cron.errors import cron_value_error
from app.cron.jobs.backup import BackupJobParams, backup_cronjob
from app.cron.manager import CronManager
from app.cron.registry import CronRegistry
from app.cron.types import ExecutionContext
from app.dependencies import get_current_user
from app.dynamic_config.schemas import BaseConfigSchema
from app.errors import INTERNAL_ERROR_MESSAGE
from app.routers.cron import router
from tests.support.runtime import replace_runtime_resource


class SafetyParams(BaseConfigSchema):
    limit: int = Field(default=1, gt=0)
    values: dict[str, int] = Field(default_factory=dict)
    message: str = "valid"

    @field_validator("message")
    @classmethod
    def reject_private_message(cls, value: str) -> str:
        if value == "private-bound-secret":
            raise PydanticCustomError("greater_than", "private-bound-secret {gt}", {"gt": 987654321})
        if value != "valid":
            raise ValueError(f"adapter credential={value}")
        return value


@pytest.fixture
async def cron_api(isolated_runtime, setup_test_db):
    manager = CronManager()
    registry = CronRegistry()

    async def scheduled_job(context: ExecutionContext) -> None:
        context.log("完成测试任务")

    registry.register_func(scheduled_job, SafetyParams, identifier="safety")
    registry.register_func(backup_cronjob, BackupJobParams, identifier="backup")
    replace_runtime_resource(isolated_runtime, "cron_manager", manager)
    replace_runtime_resource(isolated_runtime, "cron_registry", registry)
    app = FastAPI()
    app.include_router(router, prefix="/api")
    app.dependency_overrides[get_current_user] = lambda: None
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
        yield client, manager
    await manager.shutdown()


@pytest.mark.parametrize("method,url", [("POST", "/api/cron/"), ("PUT", "/api/cron/existing")])
@pytest.mark.parametrize(
    "params,diagnostic",
    [
        ({"message": "private-validator-secret"}, "message: 字段值无效"),
        ({"limit": 0}, "limit: 必须大于 0"),
        ({"limit": "private-input-secret"}, "limit: 应为整数"),
        ({"values": {"private-location-secret": "private-input-secret"}}, "values: 应为整数"),
        ({"message": "private-bound-secret"}, "message: 字段值无效"),
    ],
)
async def test_parameter_errors_keep_safe_field_diagnostics(cron_api, method, url, params, diagnostic, caplog):
    client, _manager = cron_api
    response = await client.request(method, url, json={"identifier": "safety", "cron": "0 0 * * *", "params": params})
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert isinstance(detail, str) and diagnostic in detail
    assert "private-" not in detail
    assert "987654321" not in detail
    assert "private-" not in caplog.text


@pytest.mark.parametrize("message,status", [("credential-secret not found", 404), ("credential-secret cannot pause", 409)])
async def test_unknown_value_error_keeps_original_status_without_adapter_text(cron_api, monkeypatch, message, status, caplog):
    client, manager = cron_api
    original = ValueError(message)
    monkeypatch.setattr(manager, "pause_cronjob", AsyncMock(side_effect=original))
    response = await client.post("/api/cron/private-job-id/pause")
    assert response.status_code == status
    assert response.json() == {"detail": INTERNAL_ERROR_MESSAGE}
    assert type(original) is ValueError and str(original) == message
    assert "credential-secret" not in caplog.text


@pytest.mark.parametrize("method,url,operation", [("POST", "/api/cron/", "create_cronjob"), ("PUT", "/api/cron/existing", "update_cronjob")])
async def test_unexpected_manager_errors_keep_safe_http_500(cron_api, monkeypatch, method, url, operation, caplog):
    client, manager = cron_api
    monkeypatch.setattr(manager, operation, AsyncMock(side_effect=RuntimeError("credential-secret")))
    response = await client.request(method, url, json={"identifier": "safety", "cron": "0 0 * * *", "params": {}})
    assert response.status_code == 500
    assert INTERNAL_ERROR_MESSAGE in response.json()["detail"]
    assert "credential-secret" not in response.text + caplog.text


async def test_authored_manager_errors_keep_clear_status_and_plain_value_error(cron_api):
    client, manager = cron_api
    original = cron_value_error("internal identity private-job-id", public_message="定时任务不存在")
    assert type(original) is ValueError and original.args == ("internal identity private-job-id",)
    with pytest.raises(ValueError, match="不存在") as missing:
        await manager.pause_cronjob("private-job-id")
    assert type(missing.value) is ValueError
    response = await client.post("/api/cron/private-job-id/pause")
    assert response.status_code == 404
    assert response.json() == {"detail": "定时任务不存在"}
    response = await client.post("/api/cron/", json={"identifier": "private-unknown-type", "cron": "0 0 * * *", "params": {}})
    assert response.status_code == 400 and response.json() == {"detail": "定时任务类型未注册"}


@pytest.mark.parametrize(
    "payload,diagnostic",
    [
        ({"identifier": "backup", "cron": "0 0 * * *", "params": {}}, "至少需要指定一个保留策略参数"),
        ({"identifier": "backup", "cron": "0 0 * * *", "params": {"enable_forget": False, "path": "private-path-secret"}}, "不能在未指定server_id的情况下指定路径"),
        ({"identifier": "safety", "cron": "0 0 * * private-weekday-secret", "params": {}}, "Cron 星期字段无效"),
    ],
)
async def test_authored_constraints_remain_readable_without_input_values(cron_api, payload, diagnostic, caplog):
    client, _manager = cron_api
    response = await client.post("/api/cron/", json=payload)
    assert response.status_code == 400 and diagnostic in response.json()["detail"]
    assert "private-" not in response.text + caplog.text
