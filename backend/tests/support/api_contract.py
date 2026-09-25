"""Capture route declarations and representative wire schemas without starting services."""

import argparse
import json
from pathlib import Path
from typing import Any

REPRESENTATIVE_PATHS = {
    "/auth/token", "/auth/code/complete", "/user/me", "/tasks", "/tasks/{task_id}",
    "/archive/upload/init", "/archive/upload/{upload_id}", "/archive/upload/{upload_id}/verify",
    "/servers/{server_id}/compose", "/servers/{server_id}/operations",
    "/servers/{server_id}/files/content", "/servers/{server_id}/world-restore/restore",
    "/servers/{server_id}/world-restore/restorations", "/servers/{server_id}/maintenance",
}


def capture() -> dict[str, Any]:
    from fastapi.routing import APIRoute, APIWebSocketRoute
    from pydantic import TypeAdapter

    from app.auth.session import (
        AUTH_COOKIE_NAME,
        CSRF_COOKIE_NAME,
        CSRF_EXEMPT_PATHS,
        CSRF_HEADER_NAME,
        SAFE_METHODS,
    )
    from app.background_tasks.types import (
        TaskProgress,
        TaskResult,
        TaskStatus,
        TaskType,
    )
    from app.dependencies import (
        RequireRole,
        get_current_user,
        get_websocket_user,
        verify_master_token,
    )
    from app.events.models import PublicEventFrame
    from app.main import api_app

    def requirements(dependency: Any) -> set[str]:
        call = dependency.call
        values: set[str] = set()
        if isinstance(call, RequireRole):
            values.add("roles:" + ",".join(sorted(role.value for role in call.roles)))
        elif call in (get_current_user, get_websocket_user):
            values.add("session_or_master")
        elif call is verify_master_token:
            values.add("master_only")
        for nested in dependency.dependencies:
            values.update(requirements(nested))
        return values

    inventory = []
    for route in api_app.routes:
        if not isinstance(route, (APIRoute, APIWebSocketRoute)):
            continue
        methods = route.methods if isinstance(route, APIRoute) else {"WS"}
        for method in sorted(methods):
            inventory.append({
                "method": method, "path": "/api" + route.path,
                "declared_authorization": sorted(requirements(route.dependant)),
                "cookie_csrf": method != "WS" and method not in SAFE_METHODS and route.path not in CSRF_EXEMPT_PATHS,
            })
    schema = api_app.openapi()
    paths = {}
    missing = REPRESENTATIVE_PATHS - schema["paths"].keys()
    if missing:
        raise RuntimeError(f"Representative API routes disappeared: {sorted(missing)}")
    for path in sorted(REPRESENTATIVE_PATHS):
        paths[path] = {
            method: {key: value for key, value in operation.items()
                     if key in {"parameters", "requestBody", "responses", "security"}}
            for method, operation in schema["paths"][path].items()
        }
    components: dict[str, Any] = {}

    def collect_references(value: Any) -> None:
        if isinstance(value, dict):
            reference = value.get("$ref", "")
            if reference.startswith("#/components/schemas/"):
                name = reference.rsplit("/", 1)[1]
                if name not in components:
                    components[name] = schema["components"]["schemas"][name]
                    collect_references(components[name])
            for child in value.values():
                collect_references(child)
        elif isinstance(value, list):
            for child in value:
                collect_references(child)

    collect_references(paths)
    return {
        "inventory": sorted(inventory, key=lambda entry: (entry["path"], entry["method"])),
        "authentication": {"session_cookie": AUTH_COOKIE_NAME, "csrf_cookie": CSRF_COOKIE_NAME,
                           "csrf_header": CSRF_HEADER_NAME, "csrf_exempt_paths": sorted(CSRF_EXEMPT_PATHS)},
        "representative_openapi": {"paths": paths, "components": {"schemas": components}},
        "protocols": {"public_event": TypeAdapter(PublicEventFrame).json_schema(),
                      "task_progress": TaskProgress.model_json_schema(), "task_result": TaskResult.model_json_schema(),
                      "task_status": [status.value for status in TaskStatus], "task_type": [kind.value for kind in TaskType]},
    }


def main() -> None:
    from tests.support.environment import configure_test_environment

    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    environment = configure_test_environment()
    try:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(capture(), ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    finally:
        environment.cleanup()


if __name__ == "__main__":
    main()
