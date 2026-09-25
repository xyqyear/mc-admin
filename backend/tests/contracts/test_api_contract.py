import json
from pathlib import Path

from tests.support.api_contract import capture


def test_routes_permissions_and_wire_schemas_match_reviewed_contract() -> None:
    fixture = Path(__file__).parent / "fixtures" / "api-contract.json"
    expected = json.loads(fixture.read_text())
    expected["inventory"].extend([
        {"method": "GET", "path": "/api/operations", "declared_authorization": ["session_or_master"], "cookie_csrf": False},
        {"method": "GET", "path": "/api/operations/{operation_id}", "declared_authorization": ["session_or_master"], "cookie_csrf": False},
        {"method": "POST", "path": "/api/operations/{operation_id}/resolve", "declared_authorization": ["roles:owner", "session_or_master"], "cookie_csrf": True},
    ])
    expected["inventory"].sort(key=lambda entry: (entry["path"], entry["method"]))
    schemas = expected["representative_openapi"]["components"]["schemas"]
    for schema, name, title in (
        ("ComposeConfig", "expected_version", "Expected Version"),
        ("BackgroundTaskResponse", "error_code", "Error Code"),
        ("BackgroundTaskSummaryResponse", "error_code", "Error Code"),
        ("RestorationResponse", "binding_issue", "Binding Issue"),
    ):
        schemas[schema]["properties"][name] = {"anyOf": [{"type": "string"}, {"type": "null"}], "title": title}
    schemas["RestorationResponse"]["properties"]["server_generation"] = {
        "anyOf": [{"type": "integer"}, {"type": "null"}], "title": "Server Generation",
    }
    assert capture() == expected
