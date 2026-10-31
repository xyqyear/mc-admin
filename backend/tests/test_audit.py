import json

import pytest
from fastapi import FastAPI, Request, Response
from httpx2 import ASGITransport, AsyncClient

from app.audit import OperationAuditMiddleware
from app.config import AuditSettings, get_settings


@pytest.fixture
def middleware(monkeypatch, tmp_path):
    monkeypatch.setattr(get_settings(), "logs_dir", tmp_path)
    monkeypatch.setattr(get_settings(), "audit", AuditSettings())
    yield OperationAuditMiddleware(FastAPI())


def test_audit_configuration_defaults():
    configuration = AuditSettings()
    assert configuration.enabled
    assert configuration.log_request_body
    assert configuration.max_body_size == 10240
    assert {"password", "token", "secret", "key"} <= set(configuration.sensitive_fields)
    assert {"ak", "sk", "code", "ticket"} <= set(configuration.sensitive_exact_fields)


def test_log_file_creation(middleware, tmp_path):
    assert middleware.logger is not None
    middleware.logger.info("synthetic audit operation")
    for handler in middleware.logger.handlers:
        handler.flush()
    assert "synthetic audit operation" in (tmp_path / get_settings().audit.log_file).read_text()


def test_sensitive_data_masking(middleware):
    original = {
        "username": "testuser", "password": "synthetic-password", "token": "synthetic-token",
        "config": {"secret": "synthetic-nested-secret", "public": "public-value"},
    }
    assert middleware._mask_sensitive_data(original) == {
        "username": "testuser", "password": "***MASKED***", "token": "***MASKED***",
        "config": {"secret": "***MASKED***", "public": "public-value"},
    }
    assert original["password"] == "synthetic-password"


@pytest.mark.parametrize("method,expected", [
    ("POST", True), ("PUT", True), ("PATCH", True), ("DELETE", True),
    ("GET", False), ("HEAD", False), ("OPTIONS", False),
])
@pytest.mark.parametrize("path", ["/api/auth/token", "/api/servers/test/operations", "/api/admin/users/123"])
def test_audit_patterns(middleware, method, expected, path):
    request = Request({"type": "http", "method": method, "path": path, "headers": []})
    assert middleware._should_audit_request(request) is expected


@pytest.mark.parametrize("authorization", [None, "InvalidToken", "Bearer invalid-token"])
async def test_invalid_authentication_has_no_user(middleware, authorization):
    headers = [(b"authorization", authorization.encode())] if authorization else []
    request = Request({"type": "http", "method": "GET", "path": "/api/user/me", "headers": headers})
    assert await middleware._get_user_info(request) is None


async def test_http_audit_preserves_request_body_and_redacts_log(middleware, tmp_path):
    application = FastAPI()
    application.add_middleware(OperationAuditMiddleware)

    @application.post("/api/settings")
    async def save(request: Request):
        body = await request.json()
        assert body == {"name": "visible", "password": "never-log-this"}
        return {"saved": body["name"]}

    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.post("/api/settings", json={"name": "visible", "password": "never-log-this"})
    assert response.status_code == 200
    assert response.json() == {"saved": "visible"}
    for handler in middleware.logger.handlers:
        handler.flush()
    written = (tmp_path / get_settings().audit.log_file).read_text()
    assert "never-log-this" not in written
    entries = [json.loads(line) for line in written.splitlines()]
    assert len(entries) == 1
    assert entries[0]["request_body"] == {"name": "visible", "password": "***MASKED***"}
    assert entries[0]["status_code"] == 200
    assert entries[0]["success"] is True


@pytest.mark.parametrize("field,payload", [
    ("yaml_content", "services:\n  mc:\n    environment:\n      RCON_PASSWORD: synthetic-config-password\n"),
    ("yaml_template", "services:\n  mc:\n    environment:\n      RCON_PASSWORD: synthetic-config-password\n"),
    ("content", "server-port=25565\nrcon.password=synthetic-config-password\n"),
])
async def test_audit_masks_opaque_configuration_but_retains_metadata(middleware, tmp_path, field, payload):
    body = {"path": "/server.properties", "action": "save", field: payload, "nested": {field: payload}}
    encoded = json.dumps(body).encode()

    async def receive():
        return {"type": "http.request", "body": encoded, "more_body": False}

    request = Request({
        "type": "http", "method": "PUT", "path": "/api/servers/synthetic/files/content",
        "headers": [(b"content-type", b"application/json")], "query_string": b"",
        "scheme": "http", "server": ("test", 80), "client": ("127.0.0.1", 1234),
        "path_params": {"server_id": "synthetic"},
    }, receive)
    masked = await middleware._read_request_body(request)
    entry = middleware._create_log_entry(request, Response(status_code=204), None, masked, 0)
    middleware.logger.info(entry)
    for handler in middleware.logger.handlers:
        handler.flush()
    written = (tmp_path / get_settings().audit.log_file).read_text()
    assert "synthetic-config-password" not in written
    assert json.loads(entry)["request_body"] == {
        "path": "/server.properties", "action": "save", field: "***MASKED***", "nested": {field: "***MASKED***"},
    }
    assert json.loads(entry)["path_params"] == {"server_id": "synthetic"}
    assert await request.body() == encoded
