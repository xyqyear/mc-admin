import json
import os
import runpy
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_huawei_credentials_are_available_only_to_the_environment_cloud_job():
    workflow = yaml.safe_load((ROOT / ".github/workflows/dns-tests.yml").read_text())
    events = workflow[True]
    assert "pull_request" not in events and "pull_request_target" not in events
    assert events["push"]["branches"] == ["main"]
    job = workflow["jobs"]["huawei"]
    assert job["environment"] == "dns-e2e"
    credential_steps = [step for step in job["steps"] if "HUAWEICLOUD_SK" in step.get("env", {})]
    assert len(credential_steps) == 2
    run = credential_steps[0]["run"]
    assert 'trap recover EXIT' in run and 'scripts/ci/recover_dns.sh' in run
    assert job["env"]["HUAWEICLOUD_DNS_ZONE"] == "${{ vars.HUAWEICLOUD_DNS_ZONE }}"
    assert "always()" in credential_steps[1]["if"]
    assert 'scripts/ci/recover_dns.sh' in credential_steps[1]["run"]
    assert '--tag dns --case' in run
    for step in job["steps"]:
        if "upload-artifact" in step.get("uses", ""):
            assert "/runtime" not in step["with"]["path"]
            assert "/cloud/" in step["with"]["path"]
    ordinary = yaml.safe_load((ROOT / ".github/workflows/e2e-tests.yml").read_text())
    step = next(step for step in ordinary["jobs"]["regression"]["steps"] if "E2E_EXTERNAL_CONFIG" in step.get("env", {}))
    assert "github.event_name == 'workflow_dispatch'" in step["env"]["E2E_EXTERNAL_CONFIG"]
    assert "inputs.selection == 'dnspod'" in step["env"]["E2E_EXTERNAL_CONFIG"]


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
