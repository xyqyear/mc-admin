"""Exercise publication gates against a disposable loopback registry, never GHCR."""

import argparse
import io
import json
import os
import subprocess
import tarfile
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from .candidate import (
    REQUIRED_GATES,
    capture,
    digest,
    file_digest,
    load,
    promote,
    qualify,
    verify,
)


def fixture(directory: Path) -> dict:
    config = json.dumps({"architecture": "amd64", "os": "linux", "rootfs": {"type": "layers", "diff_ids": []}, "config": {}, "history": []}).encode()
    config_digest = digest(config)
    manifest = json.dumps({"schemaVersion": 2, "mediaType": "application/vnd.oci.image.manifest.v1+json",
                           "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": config_digest, "size": len(config)}, "layers": []}).encode()
    manifest_digest = digest(manifest)
    index = json.dumps({"schemaVersion": 2, "manifests": [{"mediaType": "application/vnd.oci.image.manifest.v1+json", "digest": manifest_digest, "size": len(manifest)}]}).encode()
    with tarfile.open(directory / "application.oci.tar", "w") as archive:
        for name, data in {"oci-layout": b'{"imageLayoutVersion":"1.0.0"}', "index.json": index,
                           "blobs/sha256/" + config_digest[7:]: config, "blobs/sha256/" + manifest_digest[7:]: manifest}.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            archive.addfile(entry, io.BytesIO(data))
    return capture(directory, {"revision": "0" * 40, "dirty": True, "fingerprint": "synthetic publication protocol fixture"})


def docker(*args: str) -> str:
    return subprocess.check_output(["docker", *args], text=True).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if (args.candidate is None) != (args.receipt is None):
        parser.error("--candidate and --receipt must be supplied together")
    supplied = None
    if args.candidate is not None:
        metadata = verify(args.candidate)
        supplied = json.loads(args.receipt.read_text())
        if supplied.get("candidate") != metadata:
            raise ValueError("Actual qualification receipt belongs to a different candidate")
        qualify(metadata, {name: {"result": status} for name, status in supplied.get("gates", {}).items()})
    owner = uuid.uuid4().hex
    name = "mc-admin-release-check-" + owner[:12]
    label = "io.mc-admin.release-qualification"
    report: dict = {"owner": owner, "registry_container": name,
                    "fixture": "qualified application candidate; loopback transfer only" if supplied else "synthetic OCI protocol fixture; no application qualification claimed"}
    if supplied:
        report["qualification_receipt_sha256"] = file_digest(args.receipt)
    with tempfile.TemporaryDirectory(prefix="mc-admin-release-check-") as temporary:
        directory = Path(temporary)
        candidate_directory = args.candidate or directory
        metadata = verify(candidate_directory) if supplied else fixture(directory)
        needs = {gate: {"result": "success"} for gate in REQUIRED_GATES}
        receipt = directory / "qualification.json"
        registry_data = directory / "registry-data"
        registry_data.mkdir()
        container = None
        image_tag = "mc-admin-release-fixture:" + owner
        try:
            docker("pull", "registry:2.8.3")
            container = docker("run", "-d", "--name", name, "--label", label + "=" + owner,
                               "--user", f"{os.getuid()}:{os.getgid()}",
                               "-p", "127.0.0.1::5000", "--mount", "type=bind,src=" + str(registry_data) + ",dst=/var/lib/registry", "registry:2.8.3")
            inspected = json.loads(docker("inspect", container))[0]
            assert inspected["Config"]["Labels"][label] == owner
            port = inspected["NetworkSettings"]["Ports"]["5000/tcp"][0]["HostPort"]
            base = "http://127.0.0.1:" + port
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            for attempt in range(40):
                try:
                    with opener.open(base + "/v2/", timeout=1) as response:
                        assert response.status == 200
                    break
                except (urllib.error.URLError, TimeoutError, ConnectionError):
                    if attempt == 39:
                        raise
                    time.sleep(0.25)
            destination = "127.0.0.1:" + port + "/owned/application:qualified"
            rejected = []
            for gate in sorted(REQUIRED_GATES):
                for status in ("failure", "cancelled", "skipped", None):
                    data = json.loads(json.dumps(supplied)) if supplied else qualify(metadata, needs)
                    if status is None:
                        del data["gates"][gate]
                    else:
                        data["gates"][gate] = status
                    receipt.write_text(json.dumps(data))
                    try:
                        promote(candidate_directory, receipt, [destination], insecure=True)
                    except ValueError:
                        rejected.append({"gate": gate, "status": status})
                    else:
                        raise AssertionError("Failed gate reached promotion")
                    with opener.open(base + "/v2/_catalog", timeout=5) as response:
                        assert json.load(response)["repositories"] == []
            receipt.write_text(json.dumps(supplied or qualify(metadata, needs)))
            loaded = load(candidate_directory, image_tag)
            result = promote(candidate_directory, receipt, [destination], insecure=True)
            report.update({"candidate": metadata, "loaded_config_digest": loaded["local_image_id"], "promotion": result,
                           "rejected_without_registry_writes": rejected, "registry_image": inspected["Image"]})
        finally:
            if container is not None:
                inspected = json.loads(docker("inspect", container))[0]
                if inspected["Config"]["Labels"].get(label) != owner:
                    raise RuntimeError("Refusing to remove registry with different owner")
                docker("rm", "-f", container)
                assert not docker("ps", "-aq", "--filter", "label=" + label + "=" + owner)
                report["registry_removed"] = True
            if docker("image", "ls", "-q", image_tag):
                docker("image", "rm", image_tag)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2) + "\n")
    report["temporary_data_removed"] = not directory.exists()
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
