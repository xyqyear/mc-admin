import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("candidate", ROOT / "scripts/release/candidate.py")
assert spec is not None and spec.loader is not None
candidate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(candidate)


def make_candidate(directory: Path):
    config = json.dumps({"architecture": "amd64", "os": "linux", "rootfs": {"type": "layers", "diff_ids": []}, "config": {}}).encode()
    config_digest = candidate.digest(config)
    manifest = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                           "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": config_digest, "size": len(config)}, "layers": []}).encode()
    manifest_digest = candidate.digest(manifest)
    index = json.dumps({"schemaVersion": 2, "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": manifest_digest, "size": len(manifest)}]}).encode()
    with tarfile.open(directory / "application.oci.tar", "w") as archive:
        for name, data in {"oci-layout": b'{"imageLayoutVersion":"1.0.0"}', "index.json": index,
                           "blobs/sha256/" + config_digest[7:]: config, "blobs/sha256/" + manifest_digest[7:]: manifest}.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    return candidate.capture(directory, {"revision": "a" * 40, "dirty": False, "fingerprint": "sha256:" + "b" * 64})


@pytest.mark.parametrize("gate", sorted(candidate.REQUIRED_GATES))
@pytest.mark.parametrize("status", ["failure", "cancelled", "skipped", "", None])
def test_any_unsuccessful_required_gate_prevents_registry_execution(tmp_path, monkeypatch, gate, status):
    metadata = make_candidate(tmp_path)
    receipt = {"candidate": metadata, "gates": dict.fromkeys(candidate.REQUIRED_GATES, "success")}
    receipt["gates"][gate] = status
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt))
    calls = []
    monkeypatch.setattr(candidate.subprocess, "run", lambda *args, **kwargs: calls.append(args))
    for insecure, destination in [(True, "127.0.0.1:5000/owned:test"), (False, "registry.example.invalid/owned:test")]:
        with pytest.raises(ValueError, match="did not succeed"):
            candidate.promote(tmp_path, path, [destination], revision=metadata["source"]["revision"], insecure=insecure)
    assert calls == []


def test_missing_gate_or_different_source_artifact_cannot_be_qualified(tmp_path):
    metadata = make_candidate(tmp_path)
    needs = {name: {"result": "success"} for name in candidate.REQUIRED_GATES}
    candidate.qualify(metadata, needs, revision="a" * 40)
    with pytest.raises(ValueError, match="source"):
        candidate.qualify(metadata, needs, revision="c" * 40)
    del needs["browser"]
    with pytest.raises(ValueError, match="incomplete"):
        candidate.qualify(metadata, needs)

    binary_directory = tmp_path / "bin"
    binary_directory.mkdir()
    registry_calls = tmp_path / "registry-calls.txt"
    external_command = binary_directory / "skopeo"
    external_command.write_text('#!/bin/sh\nprintf "%s\\n" "$@" >> "$REGISTRY_CALL_LOG"\nexit 97\n')
    external_command.chmod(0o700)
    environment = {**os.environ, "PATH": str(binary_directory) + os.pathsep + os.environ["PATH"], "REGISTRY_CALL_LOG": str(registry_calls)}
    receipt_path = tmp_path / "receipt.json"
    for insecure, revision, dirty, reaches_registry in [
        (False, None, False, False),
        (False, "a" * 7, False, False),
        (False, "c" * 40, False, False),
        (False, "a" * 40, True, False),
        (False, None, True, False),
        (True, "c" * 40, False, False),
        (True, "a" * 7, False, False),
        (True, "a" * 40, True, False),
        (False, "a" * 40, False, True),
        (True, "a" * 40, False, True),
        (True, None, True, True),
    ]:
        source = {**metadata, "source": {**metadata["source"], "dirty": dirty}}
        (tmp_path / "candidate.json").write_text(json.dumps(source))
        receipt_path.write_text(json.dumps({"candidate": source, "gates": dict.fromkeys(candidate.REQUIRED_GATES, "success")}))
        registry_calls.unlink(missing_ok=True)
        destination = "127.0.0.1:5000/owned:test" if insecure else "registry.example.invalid/owned:test"
        arguments = [sys.executable, str(ROOT / "scripts/release/candidate.py"), "promote", "--directory", str(tmp_path), "--receipt", str(receipt_path), "--destination", destination]
        if revision is not None:
            arguments.extend(["--revision", revision])
        if insecure:
            arguments.append("--insecure-loopback")
        result = subprocess.run(arguments, env=environment, capture_output=True, text=True, check=False)
        assert result.returncode != 0
        if reaches_registry:
            assert registry_calls.read_text().splitlines()[:2] == ["copy", "--preserve-digests"]
            assert "exit status 97" in result.stderr
        else:
            assert not registry_calls.exists(), (insecure, revision, dirty)
            assert "source" in result.stderr and "revision" in result.stderr

    metadata["config_digest"] = "sha256:" + "d" * 64
    (tmp_path / "candidate.json").write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="differs"):
        candidate.verify(tmp_path)


def test_release_workflow_cannot_bypass_jobs_or_rebuild_the_published_image():
    workflow = yaml.safe_load((ROOT / ".github/workflows/docker-image.yml").read_text())
    jobs = workflow["jobs"]
    assert set(jobs["qualification"]["needs"]) == candidate.REQUIRED_GATES
    assert set(jobs["promote"]["needs"]) == {"candidate", "qualification"}
    assert "success()" in jobs["promote"]["if"]
    for job in ("candidate", "static", "backend", "api", "browser"):
        assert jobs[job]["with"]["source_sha"] == "${{ github.sha }}"
    for job in ("api", "browser"):
        assert jobs[job]["with"]["candidate_artifact"] == "${{ needs.candidate.outputs.artifact }}"
    steps = jobs["promote"]["steps"]
    assert not any("build-push-action" in step.get("uses", "") for step in steps)
    promotion = next(step["run"] for step in steps if "candidate.py promote" in step.get("run", ""))
    command = promotion.split("candidate.py promote", 1)[1].split('cat promotion.json', 1)[0]
    assert '--revision "${{ github.sha }}"' in command
    assert all("docker build" not in step.get("run", "") for step in steps)
    assert workflow["permissions"] == {"contents": "read"}
    assert jobs["promote"]["permissions"]["packages"] == "write"
    assert workflow[True]["push"]["tags"] == ["v[0-9]+.[0-9]+.[0-9]+", "v[0-9]+.[0-9]+.[0-9]+-*"]
    metadata = next(step for step in steps if step.get("id") == "meta")
    assert metadata["env"]["DOCKER_METADATA_SHORT_SHA_LENGTH"] == 7
    assert metadata["with"]["flavor"].strip() == "latest=${{ steps.release-tag.outputs.stable }}"
    assert metadata["with"]["tags"].splitlines() == [
        "type=semver,pattern={{version}}",
        "type=semver,pattern={{major}}.{{minor}},enable=${{ steps.release-tag.outputs.stable }}",
        "type=semver,pattern={{major}},enable=${{ steps.release-tag.outputs.stable }}",
        "type=sha",
    ]
    assert promotion.index("tags.py check") < promotion.index("candidate.py promote")


@pytest.mark.parametrize("test_exit", [0, 29])
def test_candidate_test_report_pipeline_preserves_failure(tmp_path, test_exit):
    workflow = yaml.safe_load((ROOT / ".github/workflows/candidate.yml").read_text())
    step = next(step for step in workflow["jobs"]["build"]["steps"] if step.get("name") == "Verify and build the API executable")
    assert step["shell"] == "bash"
    tools = tmp_path / "tools"
    tools.mkdir()
    adapter = tools / "make"
    adapter.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "if 'test' in sys.argv:\n"
        "    print(json.dumps({'Action': 'pass' if os.environ['TEST_EXIT'] == '0' else 'fail', 'Test': 'TestGate'}))\n"
        "    sys.exit(int(os.environ['TEST_EXIT']))\n"
        "Path('bin').mkdir()\n"
        "Path('bin/mc-admin-e2e').write_text('verified executable')\n"
    )
    adapter.chmod(0o700)
    (tmp_path / "candidate").mkdir()
    result = subprocess.run(
        ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", step["run"]],
        cwd=tmp_path,
        env={**os.environ, "PATH": str(tools) + os.pathsep + os.environ["PATH"],
             "RUNNER_TEMP": str(tmp_path), "TEST_EXIT": str(test_exit)},
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == test_exit
    assert json.loads((tmp_path / "go-test-results.jsonl").read_text())["Action"] == ("pass" if test_exit == 0 else "fail")
    assert (tmp_path / "candidate/mc-admin-e2e").exists() == (test_exit == 0)


def test_release_tag_and_destination_policy_runs_before_promotion(tmp_path):
    workflow = yaml.safe_load((ROOT / ".github/workflows/docker-image.yml").read_text())
    steps = workflow["jobs"]["promote"]["steps"]
    validation = next(step["run"] for step in steps if step.get("id") == "release-tag")
    promotion = next(step["run"] for step in steps if "candidate.py promote" in step.get("run", ""))
    revision = "a" * 40
    promotion = promotion.replace("${{ github.sha }}", revision)
    calls = tmp_path / "promotion-call.json"
    github_output = tmp_path / "github-output"
    adapter = tmp_path / "uv"
    adapter.write_text(
        f"#!{sys.executable}\n"
        "import json, os, sys\n"
        "from pathlib import Path\n"
        "if sys.argv[4].endswith('/tags.py'):\n"
        "    os.execv(sys.executable, [sys.executable, *sys.argv[4:]])\n"
        "assert sys.argv[4:6] == ['scripts/release/candidate.py', 'promote']\n"
        "Path(os.environ['PROMOTION_CALL']).write_text(json.dumps(sys.argv[4:]))\n"
        "Path(sys.argv[sys.argv.index('--output') + 1]).write_text('{}')\n"
    )
    adapter.chmod(0o700)
    environment = {
        **os.environ, "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "GITHUB_OUTPUT": str(github_output), "GITHUB_STEP_SUMMARY": str(tmp_path / "summary"),
        "GITHUB_REPOSITORY": "Owned/MC-Admin", "GITHUB_SHA": revision, "PROMOTION_CALL": str(calls),
    }
    for tag, stable in [
        ("v6.0.0-beta.1", False), ("v6.0.0-rc.0", False), ("v6.0.0-0.alpha-01", False),
        ("v0.0.0", True), ("v6.0.0", True), ("v10.22.333", True),
    ]:
        github_output.unlink(missing_ok=True)
        result = subprocess.run(["bash", "-e", "-c", validation], cwd=ROOT, env={**environment, "GITHUB_REF_NAME": tag}, capture_output=True, text=True, check=False)
        assert result.returncode == 0, result.stderr
        assert github_output.read_text() == f"stable={str(stable).lower()}\n"
    for tag in [
        "6.0.0-beta.1", "v06.0.0", "v6.00.0", "v6.0.00", "v6.0.0-", "v6.0.0-beta.01",
        "v6.0.0-01", "v6.0.0-beta..1", "v6.0.0-beta_1", "v6.0.0-beta/1", "v6.0.0-beta.1\n",
        "v6.0.0-beta.1+build", "v6.0.0-" + "a" * 128,
    ]:
        github_output.unlink(missing_ok=True)
        result = subprocess.run(["bash", "-e", "-c", validation], cwd=ROOT, env={**environment, "GITHUB_REF_NAME": tag}, capture_output=True, text=True, check=False)
        assert result.returncode != 0, tag
        assert not github_output.exists()
    image = "ghcr.io/owned/mc-admin"
    for tag, names in [
        ("v6.0.0-beta.1", ["6.0.0-beta.1", "sha-aaaaaaa"]),
        ("v6.0.0", ["6.0.0", "6.0", "6", "latest", "sha-aaaaaaa"]),
    ]:
        expected = [f"{image}:{name}" for name in names]
        combinations = [expected, expected[:-1], [*expected, expected[0]],
                        [value.replace(image, "ghcr.io/other/mc-admin") for value in expected]]
        combinations.extend([*expected, f"{image}:{name}"] for name in ("latest", "6", "6.0", "6.0.0", "sha-bbbbbbb"))
        for destinations in combinations:
            calls.unlink(missing_ok=True)
            command = promotion.replace("--output promotion.json", f"--output {tmp_path / 'promotion.json'}").replace("cat promotion.json", f"cat {tmp_path / 'promotion.json'}")
            result = subprocess.run(["bash", "-e", "-c", command], cwd=ROOT, env={**environment, "GITHUB_REF_NAME": tag, "IMAGE_TAGS": "\n".join(destinations)}, capture_output=True, text=True, check=False)
            if destinations == expected:
                assert result.returncode == 0, result.stderr
                arguments = json.loads(calls.read_text())
                assert arguments[arguments.index("--revision") + 1] == revision
                assert [arguments[index + 1] for index, value in enumerate(arguments) if value == "--destination"] == expected
            else:
                assert result.returncode != 0
                assert "release tag policy" in result.stderr
                assert not calls.exists()
