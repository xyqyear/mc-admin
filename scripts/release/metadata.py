"""Append one deterministic release-data layer to a verified OCI image."""

import copy
import io
import json
import tarfile
from pathlib import Path
from typing import Any

from .candidate import digest, inspect_archive
from .content import release_data

IMAGE_PATH = "app/static/static/release.json"


def encoded(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def add(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    entry = tarfile.TarInfo(name)
    entry.size = len(data)
    entry.mode = 0o644
    archive.addfile(entry, io.BytesIO(data))


def read(archive: tarfile.TarFile, name: str) -> bytes:
    stream = archive.extractfile(name)
    if stream is None:
        raise ValueError("Missing OCI document")
    with stream:
        return stream.read()


def documents(archive: tarfile.TarFile):
    index = json.loads(read(archive, "index.json"))
    manifest = json.loads(read(archive, "blobs/sha256/" + index["manifests"][0]["digest"][7:]))
    config = json.loads(read(archive, "blobs/sha256/" + manifest["config"]["digest"][7:]))
    return index, manifest, config


def layer(data: bytes) -> bytes:
    release_data(data)
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.USTAR_FORMAT) as archive:
        add(archive, IMAGE_PATH, data)
    return buffer.getvalue()


def derive(source: Path, destination: Path, data: bytes) -> None:
    inspect_archive(source)
    payload = layer(data)
    layer_digest = digest(payload)
    with tarfile.open(source) as original, tarfile.open(destination, "w") as output:
        index, manifest, config = documents(original)
        config["rootfs"]["diff_ids"].append(layer_digest)
        config.setdefault("history", []).append({"created_by": "mc-admin release data"})
        config_bytes = encoded(config)
        manifest["config"] = {**manifest["config"], "digest": digest(config_bytes), "size": len(config_bytes)}
        manifest["layers"].append({"mediaType": "application/vnd.oci.image.layer.v1.tar", "digest": layer_digest, "size": len(payload)})
        manifest_bytes = encoded(manifest)
        index["manifests"][0].update(digest=digest(manifest_bytes), size=len(manifest_bytes))
        blobs = {"blobs/sha256/" + digest(value)[7:]: value for value in (payload, config_bytes, manifest_bytes)}
        for entry in original:
            if entry.name == "index.json" or entry.name in blobs:
                continue
            if entry.isfile():
                stream = original.extractfile(entry)
                if stream is None:
                    raise ValueError("Missing OCI member")
                with stream:
                    output.addfile(entry, stream)
            else:
                output.addfile(entry)
        for name, value in blobs.items():
            add(output, name, value)
        add(output, "index.json", encoded(index))
    verify_derivation(source, destination, data)


def verify_derivation(source: Path, destination: Path, data: bytes) -> None:
    inspect_archive(source)
    inspect_archive(destination)
    payload = layer(data)
    with tarfile.open(source) as original, tarfile.open(destination) as derived:
        _, base_manifest, base_config = documents(original)
        _, manifest, config = documents(derived)
        expected_config = copy.deepcopy(base_config)
        expected_config["rootfs"]["diff_ids"].append(digest(payload))
        expected_config.setdefault("history", []).append({"created_by": "mc-admin release data"})
        expected_manifest = copy.deepcopy(base_manifest)
        config_bytes = encoded(expected_config)
        expected_manifest["config"].update(digest=digest(config_bytes), size=len(config_bytes))
        expected_manifest["layers"].append({"mediaType": "application/vnd.oci.image.layer.v1.tar", "digest": digest(payload), "size": len(payload)})
        if config != expected_config or manifest != expected_manifest:
            raise ValueError("Metadata derivation changed tested layers or runtime configuration")
        if read(derived, "blobs/sha256/" + digest(payload)[7:]) != payload:
            raise ValueError("Metadata derivation changed another file")
