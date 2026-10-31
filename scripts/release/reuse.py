"""Restore and issue content qualification receipts for immutable candidates."""

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from . import candidate, metadata
from .content import RELEASE_PATH, git, identity, release_data

WORKFLOW = ".github/workflows/docker-image.yml"
MAX_AGE = timedelta(days=30)
SCHEMA = 2


def write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")


def producer() -> dict[str, str]:
    return {"repository": os.environ["GITHUB_REPOSITORY"], "run_id": os.environ["GITHUB_RUN_ID"],
            "attempt": os.environ["GITHUB_RUN_ATTEMPT"], "sha": os.environ["GITHUB_SHA"]}


def receipt_name(content: dict[str, str]) -> str:
    return "application-qualification-" + content["verification"]


def ensure_source(root: Path, sha: str) -> bool:
    if not candidate.REVISION.fullmatch(sha):
        raise ValueError("Historical source requires a full commit revision")
    probe = subprocess.run(["git", "cat-file", "-e", sha + "^{commit}"], cwd=root,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    if probe.returncode == 0:
        return True
    try:
        fetched = subprocess.run(["git", "fetch", "--no-tags", "origin", sha], cwd=root,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False, timeout=60)
    except subprocess.TimeoutExpired:
        return False
    return fetched.returncode == 0


def validate_receipt(value: dict[str, Any], root: Path, *, now: datetime | None = None) -> None:
    if value.get("schema_version") != SCHEMA or value.get("mode") not in {"full", "reuse", "metadata"}:
        raise ValueError("Unsupported qualification receipt")
    current = value["producer"]
    sources = {current["sha"], value["original"]["producer"]["sha"]}
    if value.get("data_evidence"):
        sources.add(value["data_evidence"]["producer"]["sha"])
    if not all(ensure_source(root, sha) for sha in sources):
        raise OSError("Historical qualification source is unavailable")
    if identity(root, current["sha"]) != value["identity"]:
        raise ValueError("Qualification content differs from its committed source")
    item = value["candidate"]
    if item["source"]["revision"] != current["sha"] or item["source"]["dirty"] is not False:
        raise ValueError("Qualification candidate source differs")
    original = value["original"]
    if original["producer"]["repository"] != current["repository"]:
        raise ValueError("Qualification repository differs")
    if identity(root, original["producer"]["sha"])["verification"] != value["identity"]["verification"]:
        raise ValueError("Original qualification inputs differ")
    candidate.qualify(original["candidate"], {key: {"result": result} for key, result in original["gates"].items()},
                      revision=original["producer"]["sha"])
    if value.get("gates") != original["gates"]:
        raise ValueError("Inherited gate evidence differs")
    expected_execution = sorted(candidate.REQUIRED_GATES) if value["mode"] == "full" else ["metadata"] if value["mode"] == "metadata" else []
    if value.get("executed") != expected_execution or item.get("build_source", item["source"]) != original["candidate"]["source"]:
        raise ValueError("Qualification execution or build provenance differs")
    verified_at = datetime.fromisoformat(original["verified_at"])
    age = (now or datetime.now(UTC)) - verified_at
    if age < timedelta(0) or age >= MAX_AGE:
        raise TimeoutError("Original qualification has expired")
    if value["mode"] == "full" and (original["candidate"] != item or original["producer"] != current):
        raise ValueError("Full qualification origin differs")
    if item["oci_manifest_digest"] != original["candidate"]["oci_manifest_digest"]:
        evidence = value.get("data_evidence") or {}
        smoke = evidence.get("smoke", {})
        if evidence.get("release") != value["identity"]["release"] or smoke.get("config_digest") != item["config_digest"] or smoke.get("oci_manifest_digest") != item["oci_manifest_digest"] or smoke.get("owned_cleanup_complete") is not True or smoke.get("kind") != "browser":
            raise ValueError("Metadata qualification lacks final-image smoke evidence")
        if evidence["producer"]["repository"] != current["repository"] or identity(root, evidence["producer"]["sha"]) != value["identity"] or smoke["source"]["revision"] != evidence["producer"]["sha"]:
            raise ValueError("Metadata smoke provenance differs")


class GitHub:
    def __init__(self, repository: str):
        self.repository = repository

    def api(self, path: str) -> Any:
        result = subprocess.run(["gh", "api", f"repos/{self.repository}/{path}"], capture_output=True, check=False, timeout=60)
        if result.returncode:
            raise OSError("Qualification history is unavailable")
        return json.loads(result.stdout)

    def artifacts(self, name: str, run_id: str | None = None) -> list[dict[str, Any]]:
        path = f"actions/runs/{run_id}/artifacts" if run_id else "actions/artifacts"
        values = []
        for page in range(1, 4):
            query = urlencode({"name": name, "per_page": 100, "page": page})
            rows = self.api(f"{path}?{query}")["artifacts"]
            values.extend(row for row in rows if row["name"] == name and not row["expired"])
            if len(rows) < 100:
                break
        return values

    def trusted_run(self, source: dict[str, str]) -> bool:
        run = self.api(f"actions/runs/{source['run_id']}")
        return (source["repository"] == self.repository and run["path"] == WORKFLOW
                and run["event"] in {"push", "workflow_dispatch"} and run["conclusion"] == "success"
                and run["status"] == "completed" and run["head_sha"] == source["sha"]
                and str(run["run_attempt"]) == source["attempt"]
                and run["repository"]["id"] == run["head_repository"]["id"])

    def download(self, artifact: dict[str, Any], directory: Path, names: set[str]) -> None:
        directory.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "artifact.zip"
            with path.open("wb") as output:
                result = subprocess.run(["gh", "api", f"repos/{self.repository}/actions/artifacts/{artifact['id']}/zip"],
                                        stdout=output, stderr=subprocess.PIPE, check=False, timeout=300)
            if result.returncode:
                raise OSError("Qualification artifact is unavailable")
            if not artifact.get("digest") or candidate.file_digest(path) != artifact["digest"]:
                raise ValueError("Qualification artifact checksum differs")
            with zipfile.ZipFile(path) as archive:
                files = [entry for entry in archive.infolist() if not entry.is_dir()]
                if {entry.filename for entry in files} != names or len(files) != len(names):
                    raise ValueError("Qualification artifact contains unexpected files")
                for entry in files:
                    if entry.filename.endswith(".json") and entry.file_size > 8 * 1024 * 1024:
                        raise ValueError("Qualification document exceeds its size limit")
                    with archive.open(entry) as source, (directory / entry.filename).open("wb") as output:
                        shutil.copyfileobj(source, output)


def restore(client: GitHub, root: Path, content: dict[str, str], directory: Path) -> dict[str, Any] | None:
    try:
        artifacts = client.artifacts(receipt_name(content))
    except OSError:
        return None
    records = []
    for artifact in sorted(artifacts, key=lambda row: row["id"], reverse=True):
        run = artifact.get("workflow_run", {})
        if str(run.get("id")) == os.environ.get("GITHUB_RUN_ID") or run.get("repository_id") != run.get("head_repository_id"):
            continue
        try:
            with tempfile.TemporaryDirectory() as temporary:
                client.download(artifact, Path(temporary), {"qualification.json"})
                value = json.loads((Path(temporary) / "qualification.json").read_text())
            source = value["producer"]
            if str(run.get("id")) != source["run_id"] or run.get("head_sha") != source["sha"]:
                raise ValueError("Receipt differs from its artifact run")
            if not client.trusted_run(source) or not client.trusted_run(value["original"]["producer"]):
                continue
            if value.get("data_evidence") and not client.trusted_run(value["data_evidence"]["producer"]):
                continue
            validate_receipt(value, root)
            if value["identity"]["verification"] != content["verification"]:
                raise ValueError("Receipt verification identity differs")
            records.append(value)
        except (OSError, TimeoutError):
            continue
    records.sort(key=lambda value: value["identity"] == content, reverse=True)
    for value in records:
        try:
            artifacts = client.artifacts(value["candidate_artifact"], value["producer"]["run_id"])
            if len(artifacts) != 1:
                continue
            client.download(artifacts[0], directory, {"application.oci.tar", "candidate.json", "mc-admin-e2e"})
        except OSError:
            continue
        if candidate.verify(directory, revision=value["producer"]["sha"]) != value["candidate"]:
            raise ValueError("Restored candidate differs from qualification")
        return value
    return None


def resolve(root: Path, directory: Path, *, force_full: bool = False, client: GitHub | None = None) -> dict[str, Any]:
    source = candidate.source_identity(root)
    content = identity(root)
    data = git(root, "show", f"HEAD:{RELEASE_PATH}")
    ref = os.environ.get("GITHUB_REF", "")
    release_data(data, ref.removeprefix("refs/tags/") if ref.startswith("refs/tags/") else None)
    plan: dict[str, Any] = {"mode": "full", "identity": content, "source": source}
    if force_full:
        return plan
    previous = restore(client or GitHub(os.environ["GITHUB_REPOSITORY"]), root, content, directory)
    if previous is None:
        return plan
    plan.update(mode="reuse" if previous["identity"] == content else "metadata", previous=previous)
    build_source = previous["candidate"].get("build_source", previous["candidate"]["source"])
    if plan["mode"] == "metadata":
        original = directory / "base.oci.tar"
        (directory / "application.oci.tar").rename(original)
        metadata.derive(original, directory / "application.oci.tar", data)
        original.unlink()
    item = candidate.capture(directory, source)
    item["build_source"] = build_source
    write(directory / "candidate.json", item)
    plan["prepared_candidate"] = item
    return plan


def finalize(root: Path, directory: Path, plan: dict[str, Any], needs: dict[str, Any], artifact: str,
             smoke: dict[str, Any] | None = None) -> dict[str, Any]:
    mode = plan["mode"]
    expected = {"resolve", "candidate", "static", "backend", "api", "browser", "metadata"}
    if set(needs) != expected or needs["resolve"].get("result") != "success":
        raise ValueError("Qualification workflow evidence is incomplete")
    required = candidate.REQUIRED_GATES if mode == "full" else {"metadata"} if mode == "metadata" else set()
    if any(needs[name].get("result") != ("success" if name in required else "skipped") for name in expected - {"resolve"}):
        raise ValueError("Qualification route did not finish successfully")
    item = candidate.verify(directory, revision=plan["source"]["revision"])
    current = producer()
    if current["sha"] != plan["source"]["revision"] or identity(root) != plan["identity"]:
        raise ValueError("Qualification target changed")
    if mode == "full":
        qualified = candidate.qualify(item, {name: needs[name] for name in candidate.REQUIRED_GATES}, revision=current["sha"])
        original = {"producer": current, "candidate": item, "gates": qualified["gates"], "verified_at": datetime.now(UTC).isoformat()}
    else:
        previous = plan["previous"]
        validate_receipt(previous, root)
        if item != plan["prepared_candidate"]:
            raise ValueError("Prepared candidate changed before qualification")
        original = previous["original"]
    if mode == "metadata" and (smoke is None or smoke.get("source") != item["source"]):
        raise ValueError("Metadata smoke source differs from the target")
    data_evidence = ({"release": plan["identity"]["release"], "producer": current, "smoke": smoke}
                     if mode == "metadata" else plan.get("previous", {}).get("data_evidence"))
    value = {"schema_version": SCHEMA, "mode": mode, "identity": plan["identity"], "producer": current,
             "candidate": item, "candidate_artifact": artifact, "original": original, "gates": original["gates"],
             "executed": sorted(required), "data_evidence": data_evidence}
    if mode != "full":
        value["reused_from"] = plan["previous"]["producer"]
        value["base_manifest_digest"] = plan["previous"]["candidate"]["oci_manifest_digest"]
    validate_receipt(value, root)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("identity", "resolve", "finalize", "verify"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--github-output", type=Path)
    parser.add_argument("--force-full", action="store_true")
    parser.add_argument("--resolution", type=Path)
    parser.add_argument("--needs", type=Path)
    parser.add_argument("--smoke", type=Path)
    parser.add_argument("--artifact")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    value: dict[str, Any]
    if args.command == "identity":
        value = identity(args.root)
    elif args.command == "resolve":
        if args.directory is None:
            parser.error("resolve requires --directory")
        value = resolve(args.root, args.directory, force_full=args.force_full)
    elif args.command == "finalize":
        if args.directory is None or args.resolution is None or args.needs is None or args.artifact is None:
            parser.error("finalize requires candidate, resolution, needs and artifact")
        value = finalize(args.root, args.directory, json.loads(args.resolution.read_text()), json.loads(args.needs.read_text()),
                         args.artifact, json.loads(args.smoke.read_text()) if args.smoke else None)
    else:
        if args.receipt is None or args.directory is None:
            parser.error("verify requires --receipt and --directory")
        value = json.loads(args.receipt.read_text())
        validate_receipt(value, args.root)
        sha = git(args.root, "rev-parse", "HEAD").decode().strip()
        if candidate.verify(args.directory, revision=sha) != value["candidate"] or identity(args.root) != value["identity"]:
            raise ValueError("Publication differs from qualified content")
        ref = os.environ.get("GITHUB_REF", "")
        if ref.startswith("refs/tags/"):
            release_data(git(args.root, "show", f"HEAD:{RELEASE_PATH}"), ref.removeprefix("refs/tags/"))
    if args.output:
        write(args.output, value)
    if args.github_output:
        with args.github_output.open("a") as output:
            content = value.get("identity", value)
            output.write(f"verification={content['verification']}\nrelease={content['release']}\n")
            output.write(f"receipt={receipt_name(content)}\n")
            if "mode" in value:
                output.write(f"mode={value['mode']}\n")
    print(json.dumps({key: value[key] for key in ("mode", "identity", "producer", "original", "verification", "release") if key in value}))


if __name__ == "__main__":
    main()
