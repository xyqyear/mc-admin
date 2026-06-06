"""Minecraft jar metadata extraction for self-checks."""

import json
import re
import tomllib
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


_JSON_ID_PATTERN = re.compile(r'"id"\s*:\s*"([^"]+)"')


@dataclass(frozen=True)
class JarMetadata:
    ids: tuple[str, ...]
    sources: tuple[str, ...]


def normalize_jar_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    return normalized or None


def extract_jar_metadata(path: Path) -> JarMetadata:
    ids: list[str] = []
    sources: list[str] = []

    try:
        with zipfile.ZipFile(path) as jar:
            names = set(jar.namelist())
            for metadata_path in (
                "fabric.mod.json",
                "quilt.mod.json",
            ):
                if metadata_path in names:
                    _extend_ids(
                        ids,
                        _extract_json_mod_ids(jar.read(metadata_path)),
                    )
                    sources.append(metadata_path)

            for metadata_path in (
                "META-INF/neoforge.mods.toml",
                "META-INF/mods.toml",
            ):
                if metadata_path in names:
                    _extend_ids(
                        ids,
                        _extract_toml_mod_ids(jar.read(metadata_path)),
                    )
                    sources.append(metadata_path)

            if "mcmod.info" in names:
                _extend_ids(ids, _extract_mcmod_info_ids(jar.read("mcmod.info")))
                sources.append("mcmod.info")

            for metadata_path in (
                "paper-plugin.yml",
                "plugin.yml",
            ):
                if metadata_path in names:
                    _extend_ids(
                        ids,
                        _extract_plugin_yml_ids(jar.read(metadata_path)),
                    )
                    sources.append(metadata_path)
    except (OSError, zipfile.BadZipFile):
        return JarMetadata(ids=(), sources=())

    return JarMetadata(ids=tuple(ids), sources=tuple(sources))


def _extend_ids(target: list[str], values: list[str]) -> None:
    for value in values:
        normalized = normalize_jar_id(value)
        if normalized is not None and normalized not in target:
            target.append(normalized)


def _extract_json_mod_ids(raw: bytes) -> list[str]:
    text = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = _JSON_ID_PATTERN.search(text)
        return [match.group(1)] if match else []

    if not isinstance(data, dict):
        return []
    return [data["id"]] if isinstance(data.get("id"), str) else []


def _extract_toml_mod_ids(raw: bytes) -> list[str]:
    try:
        data = tomllib.loads(raw.decode("utf-8", errors="replace"))
    except tomllib.TOMLDecodeError:
        return []

    mods = data.get("mods")
    if not isinstance(mods, list):
        return []
    return [
        mod["modId"]
        for mod in mods
        if isinstance(mod, dict) and isinstance(mod.get("modId"), str)
    ]


def _extract_mcmod_info_ids(raw: bytes) -> list[str]:
    text = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []

    mods = data if isinstance(data, list) else [data]
    return [
        mod["modid"]
        for mod in mods
        if isinstance(mod, dict) and isinstance(mod.get("modid"), str)
    ]


def _extract_plugin_yml_ids(raw: bytes) -> list[str]:
    try:
        data: Any = yaml.safe_load(raw.decode("utf-8", errors="replace"))
    except yaml.YAMLError:
        return []

    if not isinstance(data, dict):
        return []
    name = data.get("name")
    return [name] if isinstance(name, str) else []
