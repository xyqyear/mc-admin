import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_api_cases_share_one_matrix_with_dependency_scoped_credentials():
    workflow = yaml.safe_load((ROOT / ".github/workflows/e2e-tests.yml").read_text())
    events = workflow["on"]
    assert "pull_request" in events and "pull_request_target" not in events
    assert events["workflow_call"]["inputs"]["qualification"]["default"] is False
    assert not (ROOT / ".github/workflows/dns-tests.yml").exists()
    jobs = workflow["jobs"]
    assert [name for name, job in jobs.items() if "strategy" in job] == ["api"]
    job = jobs["api"]
    assert job["environment"]["name"] == "dns-e2e"
    assert "matrix.environment" not in json.dumps(job)
    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["max-parallel"] == 16
    assert "fromJSON(needs.plan.outputs.matrix)" in job["strategy"]["matrix"]
    assert job["env"]["E2E_PROVIDERS"] == "${{ toJSON(matrix.providers) }}"
    credential_steps = [step for step in job["steps"] if "HUAWEICLOUD_SK" in step.get("env", {})]
    assert len(credential_steps) == 2
    assert credential_steps[0]["run"] == "bash scripts/ci/api_shard.sh run"
    assert "always()" in credential_steps[1]["if"]
    assert credential_steps[1]["run"] == "bash scripts/ci/api_shard.sh recover"
    for step in credential_steps:
        for key in ("HUAWEICLOUD_AK", "HUAWEICLOUD_SK", "HUAWEICLOUD_DNS_ZONE"):
            assert "contains(matrix.providers, 'huawei')" in step["env"][key]
        external = step["env"]["E2E_EXTERNAL_CONFIG"]
        assert "github.event_name == 'workflow_dispatch'" in external
        assert "inputs.selection == 'dnspod'" in external
        assert "contains(matrix.providers, 'dnspod')" in external
    script = (ROOT / "scripts/ci/api_shard.sh").read_text()
    assert "trap recover EXIT" in script and "scripts/ci/recover_dns.sh" in script
    assert "--execution-plan api-planning/plan.json" in script
    for name, other in jobs.items():
        if name != "api":
            assert "environment" not in other
            assert not any("HUAWEICLOUD_AK" in step.get("env", {}) or "HUAWEICLOUD_SK" in step.get("env", {}) for step in other.get("steps", []))
    for step in job["steps"]:
        if "upload-artifact" in step.get("uses", ""):
            assert "/runtime" not in step["with"]["path"]
            assert "/cloud/" in step["with"]["path"]
    assert set(jobs["coverage"]["needs"]) == {"build", "plan", "api"}
    audit = next(step["run"] for step in jobs["coverage"]["steps"] if "ci-audit" in step.get("run", ""))
    assert 'profile="$REQUESTED_PROFILE"' in audit
    assert 'test "$EXECUTION_RESULT" = success' in audit
    assert '--profile "$profile"' in audit


def test_external_configuration_uses_private_environment_values(tmp_path, monkeypatch):
    values = {"HUAWEICLOUD_AK": "private-ak", "HUAWEICLOUD_SK": "private-sk", "HUAWEICLOUD_DNS_ZONE": "e2e.example.com", "HUAWEICLOUD_DNS_PARENT": ""}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    write_config = runpy.run_path(str(ROOT / "scripts/ci/dns_config.py"))["write_config"]
    path = tmp_path / "external.json"
    write_config(path, ["huawei"])
    config = json.loads(path.read_text())["dns"]["huawei"]
    assert config["domain"] == "e2e.example.com"
    assert config["ak"] == "private-ak" and config["sk"] == "private-sk"
    assert "prefix" not in config
    assert path.stat().st_mode & 0o777 == 0o600
    for key in values.keys() - {"HUAWEICLOUD_DNS_PARENT"}:
        monkeypatch.delenv(key)
        with pytest.raises(ValueError, match=key):
            write_config(tmp_path / "missing.json", ["huawei"])
        assert not (tmp_path / "missing.json").exists()
        monkeypatch.setenv(key, values[key])


def test_private_configuration_contains_only_required_providers(tmp_path, monkeypatch):
    write_config = runpy.run_path(str(ROOT / "scripts/ci/dns_config.py"))["write_config"]
    dnspod = {"domain": "e2e.example.com", "id": "private-id", "key": "private-key"}
    monkeypatch.setenv("E2E_EXTERNAL_CONFIG", json.dumps({"dns": {"dnspod": dnspod, "huawei": {"ak": "unused"}}}))
    path = tmp_path / "external.json"
    write_config(path, ["dnspod"])
    assert json.loads(path.read_text()) == {"dns": {"dnspod": dnspod}}
    assert path.stat().st_mode & 0o777 == 0o600
    monkeypatch.setenv("HUAWEICLOUD_AK", "private-ak")
    monkeypatch.setenv("HUAWEICLOUD_SK", "private-sk")
    monkeypatch.setenv("HUAWEICLOUD_DNS_ZONE", "e2e.example.com")
    write_config(path, ["huawei", "dnspod"])
    assert set(json.loads(path.read_text())["dns"]) == {"huawei", "dnspod"}
    assert json.loads(path.read_text())["dns"]["dnspod"] == dnspod
    monkeypatch.setenv("E2E_EXTERNAL_CONFIG", "invalid unused credentials")
    write_config(path, [])
    assert path.read_text() == ""


@pytest.mark.parametrize("providers", [None, "huawei", ["unknown"], ["huawei", "huawei"], [{}]])
def test_configuration_rejects_invalid_provider_requirements(tmp_path, providers):
    write_config = runpy.run_path(str(ROOT / "scripts/ci/dns_config.py"))["write_config"]
    path = tmp_path / "external.json"
    with pytest.raises(ValueError, match="distinct supported providers"):
        write_config(path, providers)
    assert not path.exists()


@pytest.mark.parametrize("config", ["", "private-invalid-json", "[]", '{"dns": {"dnspod": {"key": "private-key"}}}'])
def test_missing_dnspod_configuration_fails_without_disclosing_secrets(tmp_path, monkeypatch, config):
    monkeypatch.setenv("E2E_EXTERNAL_CONFIG", config)
    write_config = runpy.run_path(str(ROOT / "scripts/ci/dns_config.py"))["write_config"]
    path = tmp_path / "external.json"
    with pytest.raises(ValueError) as failure:
        write_config(path, ["dnspod"])
    assert "private" not in str(failure.value)
    assert not path.exists()


@pytest.mark.parametrize("failure", ["local_cleanup", "timing_write"])
def test_api_recovery_continues_cloud_scopes_after_local_cleanup_failure(tmp_path, failure):
    run_directory = tmp_path / "runs" / "api-test-run"
    (run_directory / "cloud").mkdir(parents=True)
    (run_directory / "manifest.json").write_text("{}")
    for name in ("first", "second"):
        (run_directory / "cloud" / (name + ".json")).write_text("{}")
    (tmp_path / "e2e-artifacts").mkdir()
    runner = tmp_path / "e2e-artifacts" / "mc-admin-e2e"
    marker = tmp_path / "attempts"
    runner_script = '#!/bin/sh\necho "$*" >> "$RECOVERY_ATTEMPTS"\n'
    if failure == "local_cleanup":
        runner_script += 'if [ "$1" = cleanup ]; then exit 1; fi\n'
    runner.write_text(runner_script + "exit 0\n")
    runner.chmod(0o700)
    scripts = tmp_path / "scripts" / "ci"
    scripts.mkdir(parents=True)
    (scripts / "recover_dns.sh").write_text((ROOT / "scripts/ci/recover_dns.sh").read_text())
    (scripts / "dns_config.py").write_text((ROOT / "scripts/ci/dns_config.py").read_text())
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    fake_uv = bin_directory / "uv"
    fake_uv_script = "#!/bin/sh\n"
    if failure == "timing_write":
        fake_uv_script += 'if [ "$4" = - ]; then exit 1; fi\n'
    fake_uv.write_text(fake_uv_script + f'shift 3\nexec "{sys.executable}" "$@"\n')
    fake_uv.chmod(0o700)
    result = subprocess.run(["bash", str(ROOT / "scripts/ci/api_shard.sh"), "recover"], cwd=tmp_path,
                            env={**os.environ, "PATH": str(bin_directory) + os.pathsep + os.environ["PATH"],
                                 "RUNNER_TEMP": str(tmp_path), "E2E_DIRECTORY": str(tmp_path / "runs"),
                                 "E2E_RUN_ID": "api-test-run", "E2E_PROVIDERS": "[]",
                                 "E2E_IMAGE": "sha256:owned", "RECOVERY_ATTEMPTS": str(marker)},
                            capture_output=True, check=False)
    assert result.returncode == 1
    attempts = marker.read_text().splitlines()
    assert len(attempts) == 3
    assert attempts[0].startswith("cleanup --run-dir ")
    assert "first.json" in attempts[1] and "second.json" in attempts[2]
    timing_path = run_directory / "recovery.json"
    if failure == "timing_write":
        assert not timing_path.exists()
    else:
        assert json.loads(timing_path.read_text())["seconds"] > 0


def test_recovery_attempts_every_manifest_after_a_failure(tmp_path):
    run_directory = tmp_path / "run"
    cloud = run_directory / "cloud"
    cloud.mkdir(parents=True)
    (run_directory / "manifest.json").write_text("{}")
    for name in ("first", "second"):
        (cloud / (name + ".json")).write_text("{}")
    runner = tmp_path / "runner"
    marker = tmp_path / "attempts"
    runner.write_text('#!/bin/sh\necho "$*" >> "$RECOVERY_ATTEMPTS"\ncase "$*" in *first.json*) exit 1;; esac\n')
    runner.chmod(0o700)
    result = subprocess.run(["bash", str(ROOT / "scripts/ci/recover_dns.sh"), str(runner), str(run_directory), "config.json", "image"], env={**os.environ, "RECOVERY_ATTEMPTS": str(marker)}, capture_output=True, check=False)
    assert result.returncode == 1
    attempts = marker.read_text().splitlines()
    assert len(attempts) == 3
    assert attempts[0].startswith("cleanup --run-dir ")
    assert "first.json" in attempts[1] and "second.json" in attempts[2]
