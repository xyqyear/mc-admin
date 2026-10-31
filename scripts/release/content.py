"""Identify committed qualification inputs and validate local release data."""

import hashlib
import json
import subprocess
from datetime import date
from functools import cmp_to_key
from pathlib import Path
from typing import Any

from .tags import release_version

RELEASE_PATH = "frontend-react/public/static/release.json"
POLICY = "content-qualification-v1"


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()


def documentation(path: str) -> bool:
    name = Path(path).name
    return path.endswith(".md") and (
        path.startswith(("docs/", "backend/docs/", "frontend-react/docs/", "e2e/docs/", "openspec/", ".agents/skills/"))
        or path in {"README.md", "AGENTS.md", "CLAUDE.md", "backend/README.md", "backend/AGENTS.md",
                    "frontend-react/README.md", "frontend-react/AGENTS.md", "e2e/README.md", "e2e/AGENTS.md"}
        or name == "README.md" and path.startswith("e2e/suites/")
    )


def git(root: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", *args], cwd=root)


def identity(root: Path, revision: str = "HEAD") -> dict[str, str]:
    sha = git(root, "rev-parse", "--verify", revision + "^{commit}").decode().strip()
    entries = []
    release = None
    for row in git(root, "ls-tree", "-r", "-z", "--full-tree", sha).split(b"\0"):
        if not row:
            continue
        header, raw_path = row.split(b"\t", 1)
        mode, kind, object_id = header.decode().split()
        path = raw_path.decode()
        if path == RELEASE_PATH:
            if mode != "100644" or kind != "blob":
                raise ValueError("Release data must be a regular non-executable file")
            release = object_id
        elif not (mode == "100644" and documentation(path)):
            entries.append([path, mode, kind, object_id])
    if release is None:
        raise ValueError("Release data is missing")
    verification = digest({"policy": POLICY, "entries": sorted(entries)})
    return {"verification": verification, "release": digest([verification, release])}


def compare_versions(left: str, right: str) -> int:
    def parts(value: str):
        core, _, pre = value.partition("-")
        return tuple(map(int, core.split("."))), pre.split(".") if pre else []

    core_a, pre_a = parts(left)
    core_b, pre_b = parts(right)
    if core_a != core_b:
        return (core_a > core_b) - (core_a < core_b)
    if not pre_a or not pre_b:
        return bool(pre_b) - bool(pre_a)
    for a, b in zip(pre_a, pre_b):
        if a == b:
            continue
        if a.isdigit() and b.isdigit():
            return (int(a) > int(b)) - (int(a) < int(b))
        if a.isdigit() != b.isdigit():
            return -1 if a.isdigit() else 1
        return (a > b) - (a < b)
    return (len(pre_a) > len(pre_b)) - (len(pre_a) < len(pre_b))


def release_data(data: bytes, tag: str | None = None) -> str:
    entries = json.loads(data)
    if not isinstance(entries, list) or not entries:
        raise ValueError("Release data must be a nonempty list")
    versions = []
    required = {"version", "date", "title", "description"}
    optional = {"features", "fixes", "improvements"}
    for entry in entries:
        if not isinstance(entry, dict) or not required <= entry.keys() or entry.keys() - required - optional:
            raise ValueError("Invalid release fields")
        if any(not isinstance(entry[key], str) for key in required) or not entry["title"]:
            raise ValueError("Invalid release text")
        version = release_version("v" + entry["version"])
        if version in versions:
            raise ValueError("Duplicate release version")
        if date.fromisoformat(entry["date"]).isoformat() != entry["date"]:
            raise ValueError("Invalid release date")
        for key in optional & entry.keys():
            if not isinstance(entry[key], list) or any(not isinstance(item, str) for item in entry[key]):
                raise ValueError("Invalid release notes")
        versions.append(version)
    current = max(versions, key=cmp_to_key(compare_versions))
    if tag is not None and current != release_version(tag):
        raise ValueError("Release tag differs from the displayed version")
    return current
