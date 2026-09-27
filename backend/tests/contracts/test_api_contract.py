import json
from pathlib import Path

from tests.support.api_contract import capture


def test_routes_permissions_and_wire_schemas_match_reviewed_contract() -> None:
    fixture = Path(__file__).parent / "fixtures" / "api-contract.json"
    expected = json.loads(fixture.read_text())
    assert capture() == expected
