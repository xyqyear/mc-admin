import argparse
import hashlib
import io
import json
import os
import re
import subprocess
import sys
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

COMPONENTS = ("backend", "api", "browser")
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_HISTORY_BYTES = 4 * 1024 * 1024
SHA = re.compile(r"[0-9a-f]{40}")
FINGERPRINT = re.compile(r"[0-9a-f]{64}")


def digest(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def fingerprint(files: list[Path], settings: list[str]) -> str:
    return digest({"files": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(files)},
                   "settings": sorted(settings)})


def publish(component: str, profile: str, compatibility: str, costs: dict[str, Any],
            environment: Mapping[str, str] | None = None) -> dict[str, Any]:
    environment = os.environ if environment is None else environment
    source = {"run_id": environment.get("GITHUB_RUN_ID", ""),
              "attempt": environment.get("GITHUB_RUN_ATTEMPT", ""),
              "sha": environment.get("SOURCE_SHA") or environment.get("GITHUB_SHA", ""),
              "branch": environment.get("GITHUB_HEAD_REF") or environment.get("GITHUB_REF_NAME", "")}
    value = {"schema_version": 1, "component": component, "profile": profile,
             "compatibility": compatibility, "audited": True, "source": source, "costs": costs}
    validate(value, component, profile, compatibility)
    return value


def validate(value: Any, component: str, profile: str, compatibility: str) -> None:
    if not isinstance(value, dict) or type(value.get("schema_version")) is not int or value.get("schema_version") != 1 or value.get("audited") is not True:
        raise ValueError("History must represent a complete audited execution")
    if (value.get("component"), value.get("profile"), value.get("compatibility")) != (component, profile, compatibility):
        raise ValueError("History execution context differs")
    if component not in COMPONENTS or not profile or not FINGERPRINT.fullmatch(compatibility):
        raise ValueError("Invalid history execution context")
    source = value.get("source")
    if not isinstance(source, dict) or not all(isinstance(source.get(key), str) for key in ("run_id", "attempt", "sha", "branch")):
        raise ValueError("History source identity is incomplete")
    if not source["run_id"].isdigit() or int(source["run_id"]) < 1 or not source["attempt"].isdigit() or int(source["attempt"]) < 1:
        raise ValueError("History run identity is invalid")
    if not SHA.fullmatch(source["sha"]) or not source["branch"]:
        raise ValueError("History source revision or branch is invalid")
    if not isinstance(value.get("costs"), dict) or not value["costs"]:
        raise ValueError("History costs are empty")
    digest(value)


class GitHubHistory:
    def __init__(self, repository: str):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repository):
            raise ValueError("Invalid history repository")
        self.repository = repository

    def api(self, endpoint: str) -> bytes:
        result = subprocess.run(["gh", "api", endpoint], capture_output=True, check=False, timeout=30)
        if result.returncode != 0:
            raise OSError("GitHub timing history request was unavailable")
        return result.stdout

    def artifacts(self, component: str) -> list[dict[str, Any]]:
        values = []
        for page in range(1, 4):
            query = urlencode({"name": f"timing-history-{component}", "per_page": 100, "page": page})
            response = json.loads(self.api(f"repos/{self.repository}/actions/artifacts?{query}"))
            batch = response["artifacts"]
            if not isinstance(batch, list):
                raise TypeError("Invalid timing artifact inventory")
            values.extend(batch)
            if len(batch) < 100:
                break
        return values

    def download(self, artifact: dict[str, Any]) -> dict[str, Any]:
        identity = artifact["id"]
        if type(identity) is not int or identity < 1:
            raise ValueError("Invalid timing artifact identity")
        archive = self.api(f"repos/{self.repository}/actions/artifacts/{identity}/zip")
        if len(archive) > MAX_ARCHIVE_BYTES:
            raise ValueError("Timing artifact exceeds its size limit")
        expected_digest = artifact.get("digest")
        if expected_digest and expected_digest != "sha256:" + hashlib.sha256(archive).hexdigest():
            raise ValueError("Timing artifact digest differs")
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            entries = [entry for entry in zipped.infolist() if Path(entry.filename).name == "history.json" and not entry.is_dir()]
            if len(entries) != 1 or entries[0].file_size > MAX_HISTORY_BYTES:
                raise ValueError("Timing artifact must contain one bounded history.json")
            return json.loads(zipped.read(entries[0]))


def restore(client: GitHubHistory, component: str, profile: str, compatibility: str,
            branch: str, current_run: str = "") -> dict[str, Any]:
    artifacts = client.artifacts(component)
    for candidate_branch in dict.fromkeys((branch, "main")):
        candidates = []
        for artifact in artifacts:
            if not isinstance(artifact, dict):
                continue
            run = artifact.get("workflow_run") or {}
            if not isinstance(run, dict):
                continue
            if (artifact.get("name") == f"timing-history-{component}" and artifact.get("expired") is False
                    and run.get("head_branch") == candidate_branch and str(run.get("id")) != current_run
                    and run.get("repository_id") == run.get("head_repository_id") and run.get("repository_id") is not None):
                candidates.append(artifact)
        candidates.sort(key=lambda item: (item.get("created_at", ""), item.get("id", 0)), reverse=True)
        for artifact in candidates[:10]:
            try:
                value = client.download(artifact)
                validate(value, component, profile, compatibility)
                run = artifact["workflow_run"]
                source = value["source"]
                if (source["run_id"], source["sha"], source["branch"]) != (str(run["id"]), run["head_sha"], candidate_branch):
                    raise ValueError("Timing source differs from its artifact")
            except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile, subprocess.TimeoutExpired):
                print(f"Timing history: ignore unavailable or incompatible artifact {artifact.get('id')}", file=sys.stderr)
                continue
            value["artifact"] = {"id": artifact["id"], "digest": artifact.get("digest"), "repository": client.repository}
            print(f"Timing history: restored {component}/{profile} from run {source['run_id']} on {candidate_branch}", file=sys.stderr)
            return value
    print(f"Timing history: no comparable {component}/{profile} sample; use fallback estimates", file=sys.stderr)
    return {}


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    context = subcommands.add_parser("fingerprint")
    context.add_argument("--file", type=Path, action="append", default=[])
    context.add_argument("--setting", action="append", default=[])
    for command in ("restore", "publish"):
        options = subcommands.add_parser(command)
        options.add_argument("--component", choices=COMPONENTS, required=True)
        options.add_argument("--profile", required=True)
        options.add_argument("--compatibility", required=True)
        options.add_argument("--output", type=Path, required=True)
        if command == "restore":
            options.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY", ""))
            options.add_argument("--branch", default=os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME", ""))
        else:
            options.add_argument("--costs", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.command == "fingerprint":
        print(fingerprint(arguments.file, arguments.setting))
    elif arguments.command == "publish":
        write(arguments.output, publish(arguments.component, arguments.profile, arguments.compatibility,
                                        json.loads(arguments.costs.read_text())))
    else:
        try:
            value = restore(GitHubHistory(arguments.repository), arguments.component, arguments.profile,
                            arguments.compatibility, arguments.branch, os.environ.get("GITHUB_RUN_ID", ""))
        except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
            print("Timing history: restore unavailable; use fallback estimates", file=sys.stderr)
            value = {}
        write(arguments.output, value)


if __name__ == "__main__":
    main()
