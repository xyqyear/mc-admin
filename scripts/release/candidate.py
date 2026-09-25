"""Inspect, qualify, load and promote one immutable single-platform OCI candidate."""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path
from typing import Any

REQUIRED_GATES = frozenset({"candidate", "static", "backend", "api", "browser"})
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
REVISION = re.compile(r"[0-9a-f]{40}")


def digest(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()


def source_identity(root: Path, *, allow_dirty: bool = False, snapshot: Path | None = None) -> dict[str, Any]:
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    dirty = bool(subprocess.check_output(["git", "status", "--porcelain", "--untracked-files=all"], cwd=root))
    if dirty and not allow_dirty:
        raise ValueError("Release candidates require a clean source checkout")
    if snapshot is not None:
        if snapshot.resolve().is_relative_to(root.resolve()):
            raise ValueError("Source snapshot must be outside the working tree")
        snapshot.mkdir(parents=True, exist_ok=False)
    names = subprocess.check_output(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=root).split(b"\0")
    hasher = hashlib.sha256()
    for raw in sorted({name for name in names if name}):
        path = root / os.fsdecode(raw)
        if not path.exists() and not path.is_symlink():
            continue
        if snapshot is not None:
            copied = snapshot / os.fsdecode(raw)
            copied.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, copied, follow_symlinks=False)
            path = copied
        hasher.update(raw + b"\0")
        hasher.update(str(path.lstat().st_mode).encode() + b"\0")
        hasher.update(os.fsencode(os.readlink(path)) if path.is_symlink() else path.read_bytes())
        hasher.update(b"\0")
    return {"revision": revision, "dirty": dirty, "fingerprint": "sha256:" + hasher.hexdigest()}


def inspect_archive(path: Path) -> dict[str, str]:
    with tarfile.open(path, "r:*") as archive:
        members = {member.name.removeprefix("./"): member for member in archive.getmembers()}

        def read(name: str) -> bytes:
            member = members[name]
            if not member.isfile():
                raise ValueError(f"OCI member is not a regular file: {name}")
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError(f"Missing OCI member: {name}")
            return stream.read()

        def blob(descriptor: dict[str, Any]) -> bytes:
            value = descriptor["digest"]
            if not DIGEST.fullmatch(value):
                raise ValueError("Unsupported OCI digest")
            data = read("blobs/sha256/" + value.removeprefix("sha256:"))
            if digest(data) != value or len(data) != descriptor["size"]:
                raise ValueError("OCI blob digest or size mismatch")
            return data

        index = json.loads(read("index.json"))
        if len(index["manifests"]) != 1:
            raise ValueError("Candidate must contain exactly one tested platform manifest")
        descriptor = index["manifests"][0]
        manifest = json.loads(blob(descriptor))
        if "manifests" in manifest or manifest.get("mediaType") != "application/vnd.oci.image.manifest.v1+json":
            raise ValueError("Candidate must be a single OCI image, without untested platform or attestation manifests")
        config = json.loads(blob(manifest["config"]))
        if config.get("os") != "linux" or config.get("architecture") != "amd64":
            raise ValueError("Only the qualified linux/amd64 deployment is supported")
        for layer in manifest["layers"]:
            blob(layer)
        return {"oci_manifest_digest": descriptor["digest"], "config_digest": manifest["config"]["digest"], "archive_sha256": file_digest(path)}


def capture(directory: Path, source: dict[str, Any]) -> dict[str, Any]:
    metadata = {"version": 1, "source": source, **inspect_archive(directory / "application.oci.tar")}
    runner = directory / "mc-admin-e2e"
    if runner.exists():
        metadata["runner_sha256"] = file_digest(runner)
    (directory / "candidate.json").write_text(json.dumps(metadata, indent=2) + "\n")
    return metadata


def verify(directory: Path, *, revision: str | None = None) -> dict[str, Any]:
    metadata = json.loads((directory / "candidate.json").read_text())
    actual = inspect_archive(directory / "application.oci.tar")
    if any(metadata.get(key) != value for key, value in actual.items()):
        raise ValueError("Candidate archive differs from its immutable metadata")
    if "runner_sha256" in metadata and file_digest(directory / "mc-admin-e2e") != metadata["runner_sha256"]:
        raise ValueError("E2E executable differs from its immutable metadata")
    if revision is not None and (not REVISION.fullmatch(revision) or metadata["source"]["revision"] != revision or metadata["source"]["dirty"]):
        raise ValueError("Candidate source does not match the clean checked-out revision")
    return metadata


def qualify(metadata: dict[str, Any], needs: dict[str, Any], *, revision: str | None = None) -> dict[str, Any]:
    if set(needs) != REQUIRED_GATES:
        raise ValueError("Required release gate set is incomplete or unexpected")
    failed = sorted(name for name in REQUIRED_GATES if needs[name].get("result") != "success")
    if failed:
        raise ValueError("Required release gates did not succeed: " + ", ".join(failed))
    if revision is not None and (metadata["source"]["revision"] != revision or metadata["source"]["dirty"]):
        raise ValueError("Release gate source differs from candidate")
    return {"candidate": metadata, "gates": {name: needs[name]["result"] for name in sorted(REQUIRED_GATES)}}


def load(directory: Path, tag: str) -> dict[str, Any]:
    metadata = verify(directory)
    with tempfile.TemporaryDirectory(prefix="mc-admin-candidate-load-") as temporary:
        archive = Path(temporary) / "image.tar"
        subprocess.run(["skopeo", "copy", "oci-archive:" + str(directory / "application.oci.tar"), "docker-archive:" + str(archive) + ":" + tag], check=True)
        subprocess.run(["docker", "load", "--input", str(archive)], check=True)
    image = subprocess.check_output(["docker", "image", "inspect", tag, "--format", "{{.Id}}"], text=True).strip()
    if image != metadata["config_digest"]:
        raise ValueError("Loaded Docker config digest differs from OCI candidate")
    return {**metadata, "local_image_id": image, "archive_path": str((directory / "application.oci.tar").resolve())}


def runtime_evidence(metadata: dict[str, Any], run_directory: Path, kind: str, browser_report: Path | None = None) -> dict[str, Any]:
    manifest = json.loads((run_directory / "manifest.json").read_text())
    if manifest.get("image") != metadata["config_digest"] or not all(row.get("cleaned") is True for row in manifest["environments"]):
        raise ValueError("Runtime used a different image or did not finish owned cleanup")
    report_path = run_directory / ("results.json" if kind == "api" else "fixture-result.json")
    report = json.loads(report_path.read_text())
    image = report.get("image") if kind == "api" else report.get("image_id")
    if image != metadata["config_digest"] or report.get("run_id") != manifest["run_id"]:
        raise ValueError("Runtime report identity differs from candidate or manifest")
    if kind == "api":
        if any(row.get("status") != "passed" for row in report["results"]):
            raise ValueError("API runtime report contains an unsuccessful case")
    else:
        if report.get("success") is not True or browser_report is None:
            raise ValueError("Browser fixture did not complete successfully")
        stats = json.loads(browser_report.read_text())["stats"]
        if stats.get("expected", 0) <= 0 or any(stats.get(key, 0) != 0 for key in ("unexpected", "flaky", "skipped")):
            raise ValueError("Browser report is empty or has unsuccessful or skipped journeys")
    return {"source": metadata["source"], "oci_manifest_digest": metadata["oci_manifest_digest"],
            "config_digest": metadata["config_digest"], "run_id": manifest["run_id"], "kind": kind,
            "report_sha256": file_digest(report_path), "owned_cleanup_complete": True}


def promote(directory: Path, receipt: Path, destinations: list[str], *, revision: str | None = None, insecure: bool = False) -> dict[str, Any]:
    if not insecure and revision is None:
        raise ValueError("Formal promotion requires an explicit full source revision")
    metadata = verify(directory, revision=revision)
    evidence = json.loads(receipt.read_text())
    if evidence.get("candidate") != metadata:
        raise ValueError("Qualification belongs to a different candidate")
    qualify(metadata, {name: {"result": value} for name, value in evidence.get("gates", {}).items()})
    if not destinations or any(not re.fullmatch(r"[a-z0-9][a-z0-9.:-]*/[a-z0-9_./-]+:[A-Za-z0-9_.-]+", value) for value in destinations):
        raise ValueError("Promotion requires explicit registry/repository:tag destinations")
    if insecure and any(not re.match(r"(?:localhost|127\.0\.0\.1):[0-9]+/", value) for value in destinations):
        raise ValueError("Insecure registry transport is restricted to loopback qualification")
    for destination in destinations:
        subprocess.run(["skopeo", "copy", "--preserve-digests", "--dest-tls-verify=" + str(not insecure).lower(),
                        "oci-archive:" + str(directory / "application.oci.tar"), "docker://" + destination], check=True)
        raw = subprocess.check_output(["skopeo", "inspect", "--raw", "--tls-verify=" + str(not insecure).lower(), "docker://" + destination])
        if digest(raw) != metadata["oci_manifest_digest"]:
            raise ValueError("Published manifest digest differs from tested OCI candidate")
    return {"oci_manifest_digest": metadata["oci_manifest_digest"], "destinations": destinations, "source": metadata["source"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("source", "capture", "verify", "load", "evidence", "qualify", "promote"))
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--allow-dirty", action="store_true")
    parser.add_argument("--revision")
    parser.add_argument("--source", type=Path)
    parser.add_argument("--snapshot", type=Path)
    parser.add_argument("--run-directory", type=Path)
    parser.add_argument("--runtime-kind", choices=("api", "browser"))
    parser.add_argument("--browser-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--needs", type=Path)
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--tag", default="mc-admin:qualified-candidate")
    parser.add_argument("--destination", action="append", default=[])
    parser.add_argument("--insecure-loopback", action="store_true")
    args = parser.parse_args()
    if args.command == "source":
        result = source_identity(args.root, allow_dirty=args.allow_dirty, snapshot=args.snapshot)
    elif args.directory is None:
        parser.error("--directory is required")
    elif args.command == "capture":
        if args.source is None:
            parser.error("--source is required")
        result = capture(args.directory, json.loads(args.source.read_text()))
    elif args.command == "verify":
        result = verify(args.directory, revision=args.revision)
    elif args.command == "load":
        result = load(args.directory, args.tag)
    elif args.command == "evidence":
        if args.run_directory is None or args.runtime_kind is None:
            parser.error("--run-directory and --runtime-kind are required")
        result = runtime_evidence(verify(args.directory, revision=args.revision), args.run_directory, args.runtime_kind, args.browser_report)
    elif args.command == "qualify":
        if args.needs is None:
            parser.error("--needs is required")
        result = qualify(verify(args.directory, revision=args.revision), json.loads(args.needs.read_text()), revision=args.revision)
    else:
        if args.receipt is None:
            parser.error("--receipt is required")
        result = promote(args.directory, args.receipt, args.destination, revision=args.revision, insecure=args.insecure_loopback)
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.write_text(rendered)
    print(rendered, end="")


if __name__ == "__main__":
    main()
