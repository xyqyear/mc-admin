from unittest.mock import AsyncMock

import httpx2
import pytest
from fastapi import APIRouter
from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from app.cron.errors import cron_value_error
from app.cron.manager import CronManager
from app.cron.registry import create_cron_registry
from app.dependencies import get_current_user
from app.dynamic_config.schemas import BaseConfigSchema
from app.errors import INTERNAL_ERROR_MESSAGE
from app.main import create_api_app
from app.routers.cron import CronRoute, router
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
    registry = create_cron_registry()
    replace_runtime_resource(isolated_runtime, "cron_registry", registry)
    manager = CronManager()
    replace_runtime_resource(isolated_runtime, "cron_manager", manager)
    app = create_api_app(isolated_runtime)
    app.dependency_overrides[get_current_user] = lambda: None
    app.include_router(router, prefix="/relocated")
    probes = APIRouter(route_class=CronRoute)

    @probes.post("/validation-probe/params")
    @probes.put("/validation-probe/params")
    async def validate_params(params: SafetyParams):
        return params.model_dump()

    app.include_router(probes)
    async with httpx2.AsyncClient(transport=httpx2.ASGITransport(app=app), base_url="http://test") as client:
        yield client, manager
    await manager.shutdown()


@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize(
    "params,diagnostic",
    [
        ({"message": "private-validator-secret"}, "message: 字段值无效"),
        ({"limit": 0}, "limit: 数值过小"),
        ({"limit": "private-input-secret"}, "limit: 请输入整数"),
        ({"values": {"private-location-secret": "private-input-secret"}}, "values: 请输入整数"),
        ({"message": "private-bound-secret"}, "message: 数值过小"),
    ],
)
async def test_parameter_errors_keep_safe_field_diagnostics(cron_api, method, params, diagnostic, caplog):
    client, _manager = cron_api
    response = await client.request(method, "/api/validation-probe/params", json=params)
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str) and diagnostic in detail
    assert "private-" not in detail
    assert "987654321" not in detail
    assert "private-" not in caplog.text


@pytest.mark.parametrize("method,url", [("POST", "/api/cron/"), ("PUT", "/api/cron/existing")])
async def test_backup_parameter_errors_keep_declared_field_without_input_values(cron_api, method, url, caplog):
    client, _manager = cron_api
    response = await client.request(method, url, json={
        "identifier": "backup", "cron": "0 0 * * *",
        "params": {"enable_forget": False, "keep_tag": [{"private-key-secret": "private-input-secret"}]},
    })
    assert response.status_code == 422
    assert response.json() == {"detail": "任务参数无效: backup.params.keep_tag: 请输入字符串"}
    assert "private-" not in response.text + caplog.text
    assert (await client.get("/api/cron/")).json() == []


@pytest.mark.parametrize("identifier,params,diagnostic", [
    ("backup", {"enable_forget": "private-input-secret"}, "backup.params.enable_forget: 请输入布尔值"),
    ("restart_server", {"server_id": ["private-input-secret"]}, "restart_server.params.server_id: 请输入字符串"),
    ("self_check", {"scope": ["private-input-secret"]}, "self_check.params.scope: 请输入字符串"),
])
async def test_cron_validation_follows_router_under_another_prefix(cron_api, identifier, params, diagnostic, caplog):
    client, _manager = cron_api
    response = await client.post("/api/relocated/cron/", json={
        "identifier": identifier, "cron": "0 0 * * *", "params": params,
    })
    assert response.status_code == 422
    assert response.json() == {"detail": "任务参数无效: " + diagnostic}
    assert "private-" not in response.text + caplog.text
    assert (await client.get("/api/cron/")).json() == []


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
    response = await client.request(method, url, json={"identifier": "backup", "cron": "0 0 * * *", "params": {"enable_forget": False}})
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
    assert response.status_code == 422 and response.json() == {"detail": "任务参数无效: identifier: 类型无效"}
    assert "private-unknown-type" not in response.text


@pytest.mark.parametrize(
    "payload,status,diagnostic",
    [
        ({"identifier": "backup", "cron": "0 0 * * *", "params": {}}, 422, "至少需要指定一个保留策略参数"),
        ({"identifier": "backup", "cron": "0 0 * * *", "params": {"enable_forget": False, "path": "private-path-secret"}}, 422, "不能在未指定server_id的情况下指定路径"),
        ({"identifier": "backup", "cron": "0 0 * * private-weekday-secret", "params": {"enable_forget": False}}, 400, "Cron 星期字段无效"),
    ],
)
async def test_authored_constraints_remain_readable_without_input_values(cron_api, payload, status, diagnostic, caplog):
    client, _manager = cron_api
    response = await client.post("/api/cron/", json=payload)
    assert response.status_code == status and diagnostic in response.json()["detail"]
    assert "private-" not in response.text + caplog.text
