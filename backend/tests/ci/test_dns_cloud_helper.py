import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "e2e/suites/dns/cloud_helper.py"
SCOPE = "012345abcdef.e2e-test-mc"


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
    config = {"provider": "huawei", "scope": SCOPE, "config": {"domain": "example.com", "ak": "test-ak", "sk": "test-sk", "region": "cn-north-4", "ttl": 600}}
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


def test_preservation_fixture_can_be_created_beside_unmanaged_records(cloud_helper):
    client, invoke = cloud_helper
    client.list_record_sets_by_zone.return_value = page(record("manual." + SCOPE, "TXT"))
    invoke("protect")
    created = client.create_record_set.call_args.args[0].body
    assert created.name == "_e2e-preserve." + SCOPE + ".example.com."
    assert created.records == ['"mc-admin-e2e:' + SCOPE + '"']
    client.delete_record_sets.assert_not_called()


@pytest.mark.parametrize("scope", ["custom-parent", "another.environment", "manual.custom_parent"])
def test_cleanup_uses_recorded_names_without_namespace_authorization(cloud_helper, scope):
    client, invoke = cloud_helper
    owned = record("*.primary." + scope)
    client.list_record_sets_by_zone.side_effect = [page(owned), page()]
    invoke("cleanup", scope)
    assert client.delete_record_sets.call_args.args[0].recordset_id == owned.id


def test_cleanup_deletes_only_owned_records_and_is_repeatable(cloud_helper):
    client, invoke = cloud_helper
    owned = record("*.primary." + SCOPE)
    guard = record("_e2e-preserve." + SCOPE, "TXT", '"mc-admin-e2e:' + SCOPE + '"')
    unrelated = record("manual." + SCOPE, "TXT", '"independent"')
    neighbor = record("*.primary." + SCOPE + "-other")
    client.list_record_sets_by_zone.side_effect = [page(owned, guard, unrelated, neighbor), page(unrelated, neighbor), page(unrelated, neighbor), page(unrelated, neighbor)]
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


def test_cleanup_preserves_unowned_residual_records_without_failing(cloud_helper, capsys):
    client, invoke = cloud_helper
    client.list_record_sets_by_zone.return_value = page(record("manual." + SCOPE, "TXT"))
    invoke("cleanup")
    output = json.loads(capsys.readouterr().out)
    assert output["remaining"] == 0
    assert output["scope"] == SCOPE
    client.delete_record_sets.assert_not_called()


def test_cleanup_fails_when_owned_records_remain(cloud_helper):
    client, invoke = cloud_helper
    client.list_record_sets_by_zone.return_value = page(record("*.primary." + SCOPE))
    with pytest.raises(SystemExit) as error:
        invoke("cleanup")
    assert error.value.code == 1
    client.delete_record_sets.assert_called_once()


@pytest.mark.parametrize("guard_value", [None, '"changed"'])
def test_inspection_requires_unmanaged_preservation_fixture(cloud_helper, guard_value):
    client, invoke = cloud_helper
    guard = () if guard_value is None else (record("_e2e-preserve." + SCOPE, "TXT", guard_value),)
    client.list_record_sets_by_zone.return_value = page(record("*.primary." + SCOPE), *guard)
    with pytest.raises(SystemExit) as error:
        invoke("inspect")
    assert error.value.code == 1
    client.delete_record_sets.assert_not_called()


def test_later_page_failure_cannot_delete_partial_inventory(cloud_helper):
    client, invoke = cloud_helper
    client.list_record_sets_by_zone.side_effect = [page(*(record(f"*.n{i}." + SCOPE) for i in range(500))), RuntimeError("page unavailable")]
    with pytest.raises(SystemExit):
        invoke("cleanup")
    client.delete_record_sets.assert_not_called()
