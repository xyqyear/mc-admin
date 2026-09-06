import json
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from starlette.types import Scope

from app.audit import OperationAuditMiddleware
from app.config import AuditSettings, JWTSettings, Settings, settings


@pytest.fixture
def middleware(monkeypatch):
    monkeypatch.setattr(settings.audit, "log_request_body", True)
    monkeypatch.setattr(settings.audit, "sensitive_fields", ["password", "token", "secret", "key"])
    monkeypatch.setattr(settings.audit, "sensitive_exact_fields", ["ak", "sk", "code", "ticket"])
    return OperationAuditMiddleware(FastAPI())


def request(body: bytes, content_type: str) -> Request:
    scope: Scope = {
        "type": "http",
        "method": "POST",
        "path": "/auth/token",
        "headers": [(b"content-type", content_type.encode())],
    }

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(scope, receive)


def test_sensitive_substrings_are_masked_through_nested_lists(middleware):
    value = {
        "username": "public-name",
        "providers": [{"Access_Token": "private-token", "nested": [{"api_key": "private-key"}]}],
        "normal": ["public", {"value": 3}],
    }
    result = middleware._mask_sensitive_data(value)
    assert result["username"] == "public-name"
    assert result["normal"] == value["normal"]
    assert result["providers"] == [{"Access_Token": "***MASKED***", "nested": [{"api_key": "***MASKED***"}]}]
    assert value["providers"][0]["Access_Token"] == "private-token"


@pytest.mark.parametrize("field", ["ak", "AK", "sk", "SK", "code", "Code", "ticket", "Ticket"])
def test_project_credential_names_are_masked_without_overmasking(middleware, monkeypatch, field):
    monkeypatch.setattr(settings.audit, "sensitive_fields", ["password"])
    value = {"nested": [{field: "private", "task_id": "task-123", "status_code": 200}]}
    assert middleware._mask_sensitive_data(value) == {
        "nested": [{field: "***MASKED***", "task_id": "task-123", "status_code": 200}]
    }
    assert value["nested"][0][field] == "private"


def test_exact_fields_are_configurable_and_independent_of_substrings(middleware, monkeypatch):
    monkeypatch.setattr(settings.audit, "sensitive_exact_fields", ["PiN"])
    value = {"pin": "private", "shipping": "public", "code": "public-code", "api_key": "private-key"}
    assert middleware._mask_sensitive_data(value) == {
        "pin": "***MASKED***", "shipping": "public", "code": "public-code", "api_key": "***MASKED***",
    }
    monkeypatch.setattr(settings.audit, "sensitive_exact_fields", [])
    assert middleware._mask_sensitive_data({"pin": "public", "ticket": "public", "password": "private"}) == {
        "pin": "public", "ticket": "public", "password": "***MASKED***",
    }


def test_legacy_audit_configuration_receives_exact_field_defaults():
    configured = AuditSettings.model_validate({"sensitive_fields": ["password"]})
    assert configured.sensitive_exact_fields == ["ak", "sk", "code", "ticket"]
    assert configured.sensitive_fields == ["password"]


def test_exact_field_environment_configuration(monkeypatch):
    monkeypatch.setenv("AUDIT__SENSITIVE_EXACT_FIELDS", '["pin","ticket"]')
    configured = Settings(
        master_token="test-master", jwt=JWTSettings(secret_key="test-key"), server_path=Path("/tmp/e2e-audit-config"),
    )
    assert configured.audit.sensitive_exact_fields == ["pin", "ticket"]
    assert configured.audit.sensitive_fields == ["password", "token", "secret", "key"]


async def test_password_form_is_decoded_before_auditing(middleware):
    result = await middleware._read_request_body(request(
        b"username=public-name&password=private%2Bpassword&password=second&client_secret=secret",
        "application/x-www-form-urlencoded; charset=utf-8",
    ))
    assert result == {
        "username": ["public-name"],
        "password": "***MASKED***",
        "client_secret": "***MASKED***",
    }


async def test_project_credentials_in_form_are_masked(middleware):
    result = await middleware._read_request_body(request(
        b"ak=private-access&sk=private-secret&code=private%2Bcode&ticket=private%2Bticket&ticket=second&task_id=task-123&status_code=200",
        "application/x-www-form-urlencoded",
    ))
    assert result == {
        "ak": "***MASKED***", "sk": "***MASKED***", "code": "***MASKED***", "ticket": "***MASKED***",
        "task_id": ["task-123"], "status_code": ["200"],
    }


async def test_top_level_json_array_is_masked(middleware):
    result = await middleware._read_request_body(request(
        json.dumps([{"nested": [{"refresh_token": "private", "ticket": "private-ticket"}]}]).encode(), "application/json"
    ))
    assert result == [{"nested": [{"refresh_token": "***MASKED***", "ticket": "***MASKED***"}]}]


@pytest.mark.parametrize("content_type,body", [
    ("application/json", b'{"password":"private"'),
    ("text/plain", b"password=private"),
    ("multipart/form-data; boundary=e2e", b"--e2e\r\nprivate\r\n--e2e--"),
    ("application/octet-stream", b"private\xff"),
])
async def test_unstructured_bodies_record_only_metadata(middleware, content_type, body):
    result = await middleware._read_request_body(request(body, content_type))
    assert result == {"content_type": content_type.split(";", 1)[0], "bytes": len(body)}
    assert "private" not in json.dumps(result)


async def test_body_size_limit_precedes_decoding(middleware, monkeypatch):
    monkeypatch.setattr(settings.audit, "max_body_size", 5)
    result = await middleware._read_request_body(request(b"password=private", "application/x-www-form-urlencoded"))
    assert result == {"error": "Request body too large for logging"}
