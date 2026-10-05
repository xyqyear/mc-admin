import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_huawei_credentials_are_available_only_to_the_environment_cloud_job():
    workflow = yaml.safe_load((ROOT / ".github/workflows/e2e-tests.yml").read_text())
    events = workflow["on"]
    assert "pull_request" in events and "pull_request_target" not in events
    assert events["workflow_call"]["inputs"]["qualification"]["default"] is False
    assert not (ROOT / ".github/workflows/dns-tests.yml").exists()
    jobs = workflow["jobs"]
    job = jobs["huawei"]
    assert job["environment"] == "dns-e2e"
    assert "needs.plan.outputs.cloud == 'true'" in job["if"]
    assert job["strategy"]["fail-fast"] is False
    assert job["strategy"]["max-parallel"] == 1
    assert "fromJSON(needs.plan.outputs.huawei)" in job["strategy"]["matrix"]
    credential_steps = [step for step in job["steps"] if "HUAWEICLOUD_SK" in step.get("env", {})]
    assert len(credential_steps) == 2
    assert credential_steps[0]["run"] == "bash scripts/ci/api_shard.sh run"
    assert "always()" in credential_steps[1]["if"]
    assert credential_steps[1]["run"] == "bash scripts/ci/api_shard.sh recover"
    assert job["env"]["HUAWEICLOUD_DNS_ZONE"] == "${{ vars.HUAWEICLOUD_DNS_ZONE }}"
    script = (ROOT / "scripts/ci/api_shard.sh").read_text()
    assert "trap recover EXIT" in script and "scripts/ci/recover_dns.sh" in script
    assert "--execution-plan api-planning/plan.json" in script
    for name, other in jobs.items():
        if name != "huawei":
            assert "environment" not in other
            assert not any("HUAWEICLOUD_AK" in step.get("env", {}) or "HUAWEICLOUD_SK" in step.get("env", {}) for step in other.get("steps", []))
    for step in job["steps"]:
        if "upload-artifact" in step.get("uses", ""):
            assert "/runtime" not in step["with"]["path"]
            assert "/cloud/" in step["with"]["path"]
    ordinary = jobs["regression"]
    step = next(step for step in ordinary["steps"] if "E2E_EXTERNAL_CONFIG" in step.get("env", {}))
    assert "github.event_name == 'workflow_dispatch'" in step["env"]["E2E_EXTERNAL_CONFIG"]
    assert "inputs.selection == 'dnspod'" in step["env"]["E2E_EXTERNAL_CONFIG"]
    assert set(jobs["coverage"]["needs"]) == {"build", "plan", "regression", "huawei"}
    audit = next(step["run"] for step in jobs["coverage"]["steps"] if "ci-audit" in step.get("run", ""))
    assert 'profile="$REQUESTED_PROFILE"' in audit
    assert 'test "$CLOUD_RESULT" = success' in audit
    assert '--profile "$profile"' in audit


def test_external_configuration_uses_private_environment_values(tmp_path, monkeypatch):
    values = {"HUAWEICLOUD_AK": "private-ak", "HUAWEICLOUD_SK": "private-sk", "HUAWEICLOUD_DNS_ZONE": "e2e.example.com", "HUAWEICLOUD_DNS_PARENT": ""}
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    write_config = runpy.run_path(str(ROOT / "scripts/ci/dns_config.py"))["write_config"]
    path = tmp_path / "external.json"
    write_config(path)
    config = json.loads(path.read_text())["dns"]["huawei"]
    assert config["domain"] == "e2e.example.com"
    assert config["ak"] == "private-ak" and config["sk"] == "private-sk"
    assert path.stat().st_mode & 0o777 == 0o600
    for key in values.keys() - {"HUAWEICLOUD_DNS_PARENT"}:
        monkeypatch.delenv(key)
        with pytest.raises(ValueError, match=key):
            write_config(tmp_path / "missing.json")
        assert not (tmp_path / "missing.json").exists()
        monkeypatch.setenv(key, values[key])


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
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    fake_uv = bin_directory / "uv"
    fake_uv.write_text("#!/bin/sh\nexit 1\n" if failure == "timing_write" else f'#!/bin/sh\nshift 3\nexec "{sys.executable}" "$@"\n')
    fake_uv.chmod(0o700)
    result = subprocess.run(["bash", str(ROOT / "scripts/ci/api_shard.sh"), "recover"], cwd=tmp_path,
                            env={**os.environ, "PATH": str(bin_directory) + os.pathsep + os.environ["PATH"],
                                 "RUNNER_TEMP": str(tmp_path), "E2E_DIRECTORY": str(tmp_path / "runs"),
                                 "E2E_RUN_ID": "api-test-run", "E2E_CAPABILITY": "ordinary",
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
