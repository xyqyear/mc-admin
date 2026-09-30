import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "e2e/suites/dns/cloud_helper.py"
SCOPE = "run-012345abcdef.e2e-test-mc"


@pytest.fixture
def cloud_helper(tmp_path, monkeypatch):
    import huaweicloudsdkdns.v2 as sdk

    client = Mock()
    client.list_public_zones.return_value = SimpleNamespace(zones=[SimpleNamespace(name="example.com.", id="zone")])
    builder = Mock()
    builder.with_credentials.return_value = builder
    builder.with_region.return_value = builder
    builder.with_http_config.return_value = builder
    builder.build.return_value = client
    monkeypatch.setattr(sdk.DnsClient, "new_builder", lambda: builder)
    monkeypatch.setattr("time.sleep", lambda _: None)
    config = {"provider": "huawei", "scope": SCOPE, "config": {"domain": "example.com", "prefix": "run", "managed_sub_domain": "e2e-test-mc", "ak": "test-ak", "sk": "test-sk", "region": "cn-north-4", "ttl": 600}}
    path = tmp_path / "config.json"

    def invoke(operation, scope=SCOPE):
        config["scope"] = scope
        path.write_text(json.dumps(config))
        monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(path), operation])
        runpy.run_path(str(SCRIPT), run_name="__main__")

    return client, invoke


def record(name, kind="A", value="192.0.2.1"):
    return SimpleNamespace(name=name + ".example.com.", type=kind, id=name, records=[value], ttl=600)


def page(*records):
    return SimpleNamespace(recordsets=list(records))


def test_collision_refuses_unmanaged_records_without_writes(cloud_helper):
    client, invoke = cloud_helper
    client.list_record_sets_by_zone.return_value = page(record("manual." + SCOPE, "TXT"))
    with pytest.raises(SystemExit) as error:
        invoke("check")
    assert error.value.code == 1
    client.create_record_set.assert_not_called()
    client.delete_record_sets.assert_not_called()


@pytest.mark.parametrize("scope", ["e2e-test-mc", SCOPE + ".attacker", "run-012345abcdef.e2e-test-mc-other"])
def test_invalid_scope_cannot_reach_provider(cloud_helper, scope):
    client, invoke = cloud_helper
    with pytest.raises(ValueError, match="namespace"):
        invoke("cleanup", scope)
    client.list_public_zones.assert_not_called()


def test_cleanup_deletes_only_owned_records_and_is_repeatable(cloud_helper):
    client, invoke = cloud_helper
    owned = record("*.primary." + SCOPE)
    guard = record("_e2e-preserve." + SCOPE, "TXT", '"mc-admin-e2e:' + SCOPE + '"')
    neighbor = record("*.primary." + SCOPE + "-other")
    client.list_record_sets_by_zone.side_effect = [page(owned, guard, neighbor), page(neighbor), page(neighbor), page(neighbor)]
    invoke("cleanup")
    invoke("cleanup")
    assert {call.args[0].recordset_id for call in client.delete_record_sets.call_args_list} == {owned.id, guard.id}
    assert client.delete_record_sets.call_count == 2


def test_failed_cleanup_is_not_reported_as_success_and_masks_provider_error(cloud_helper, capsys):
    client, invoke = cloud_helper
    client.list_record_sets_by_zone.return_value = page(record("*.primary." + SCOPE))
    client.delete_record_sets.side_effect = RuntimeError("private-provider-secret")
    with pytest.raises(SystemExit) as error:
        invoke("cleanup")
    assert error.value.code == 1
    output = capsys.readouterr().out
    assert "private-provider-secret" not in output
    assert "RuntimeError" in output


def test_provider_failure_retains_status_without_exposing_message(cloud_helper, capsys):
    class ProviderFailure(RuntimeError):
        status_code = 403
        error_code = "DNS.1802"

    client, invoke = cloud_helper
    client.list_record_sets_by_zone.return_value = page()
    client.create_record_set.side_effect = ProviderFailure("private-provider-secret")
    with pytest.raises(SystemExit):
        invoke("protect")
    output = json.loads(capsys.readouterr().out)
    assert output["status"] == 403 and output["error_code"] == "DNS.1802"
    assert "private-provider-secret" not in str(output)


def test_cleanup_preserves_and_reports_unowned_residual_records(cloud_helper):
    client, invoke = cloud_helper
    client.list_record_sets_by_zone.return_value = page(record("manual." + SCOPE, "TXT"))
    with pytest.raises(SystemExit) as error:
        invoke("cleanup")
    assert error.value.code == 1
    client.delete_record_sets.assert_not_called()


def test_later_page_failure_cannot_delete_partial_inventory(cloud_helper):
    client, invoke = cloud_helper
    client.list_record_sets_by_zone.side_effect = [page(*(record(f"*.n{i}." + SCOPE) for i in range(500))), RuntimeError("page unavailable")]
    with pytest.raises(SystemExit):
        invoke("cleanup")
    client.delete_record_sets.assert_not_called()
