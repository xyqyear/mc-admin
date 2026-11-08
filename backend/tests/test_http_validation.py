import pytest
from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import INTERNAL_ERROR_MESSAGE, SafeErrorMiddleware
from app.http_validation import default_validation_handler
from app.routers.settings import SettingsRoute


class EditorValues(BaseModel):
    count: int


@pytest.fixture
def validation_client():
    application = FastAPI()
    application.add_middleware(SafeErrorMiddleware)
    application.exception_handler(RequestValidationError)(default_validation_handler)
    editor = APIRouter(route_class=SettingsRoute)
    writes = []

    @editor.post("/values")
    async def save(values: EditorValues):
        writes.append(values.count)
        return {"count": values.count}

    @editor.get("/conflict")
    async def conflict():
        raise HTTPException(status_code=409, detail="配置已被修改", headers={"Retry-After": "1"})

    @editor.get("/unexpected")
    async def unexpected():
        raise RuntimeError("private-adapter-secret")

    @application.post("/settings/plain")
    async def plain(values: EditorValues):
        return {"count": values.count}

    application.include_router(editor, prefix="/tools")
    root = FastAPI()
    root.mount("/api", application)
    with TestClient(root) as client:
        yield client, writes


def test_selected_router_validation_preserves_field_and_prevents_write(validation_client, caplog):
    client, writes = validation_client
    response = client.post("/api/tools/values", json={"count": "private-input-secret"})
    assert response.status_code == 422
    assert response.json() == {"detail": "配置参数无效: count: 请输入整数"}
    assert writes == []
    assert "private-" not in response.text + caplog.text
    assert client.post("/api/tools/values", json={"count": 0}).json() == {"count": 0}
    assert writes == [0]


def test_unselected_router_uses_default_validation_even_with_settings_prefix(validation_client):
    client, _writes = validation_client
    response = client.post("/api/settings/plain", json={"count": "invalid"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, str) and detail.startswith("count:")
    assert "配置参数无效" not in detail


def test_invalid_json_keeps_safe_validation_response_without_write(validation_client, caplog):
    client, writes = validation_client
    response = client.post("/api/tools/values", content='{"count": private-json-secret}', headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    assert response.json()["detail"].startswith("配置参数无效:")
    assert writes == []
    assert "private-" not in response.text + caplog.text


def test_route_validation_preserves_business_error_status_and_headers(validation_client):
    client, _writes = validation_client
    response = client.get("/api/tools/conflict")
    assert response.status_code == 409
    assert response.json() == {"detail": "配置已被修改"}
    assert response.headers["Retry-After"] == "1"


def test_route_validation_preserves_safe_unexpected_failure(validation_client, caplog):
    client, _writes = validation_client
    response = client.get("/api/tools/unexpected")
    assert response.status_code == 500
    assert response.json() == {"detail": INTERNAL_ERROR_MESSAGE}
    assert "private-" not in response.text + caplog.text
