"""Run reproducible, owned workloads; timings are observations, never CI thresholds."""

import argparse
import asyncio
import hashlib
import importlib
import io
import json
import os
import platform
import resource
import statistics
import subprocess
import sys
import tarfile
import tempfile
import time
from collections.abc import Awaitable, Callable
from contextlib import nullcontext
from pathlib import Path
from typing import Any

from tests.support.environment import configure_test_environment


def application_settings() -> Any:
    configuration = importlib.import_module("app.config")
    if hasattr(configuration, "get_settings"):
        return configuration.get_settings()
    return configuration.settings


async def workloads(root: Path, samples: int) -> dict[str, Any]:
    from httpx2 import ASGITransport, AsyncClient, Request

    from app.archive import uploads
    from app.files.search import search_files
    from app.files.types import FileSearchRequest
    from app.mcmap.events import MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER
    from app.mcmap.runner import remove_chunks
    from app.snapshots.restic import ResticClient
    from app.utils.exec import exec_command

    main_module = importlib.import_module("app.main")
    if hasattr(main_module, "create_api_app"):
        runtime_resources = importlib.import_module("app.runtime_resources")
        api_app = main_module.create_api_app(runtime_resources.current_runtime())
    else:
        api_app = main_module.api_app
    settings = application_settings()
    uploads.ARCHIVE_UPLOAD_TMP_DIR = root / "upload-scratch"
    payload = bytes(range(256)) * (4 * 1024 * 1024 // 256)
    digest = hashlib.sha256(payload).hexdigest()
    results: dict[str, Any] = {}

    async def measure(name: str, operation: Callable[[int], Awaitable[dict[str, Any]]]) -> None:
        durations, outcomes = [], []
        for index in range(samples):
            started = time.perf_counter()
            outcomes.append(await operation(index))
            durations.append(round(time.perf_counter() - started, 6))
        assert all(outcome == outcomes[0] for outcome in outcomes), name
        results[name] = {"seconds": durations, "median_seconds": statistics.median(durations), "behavior": outcomes[0]}

    async def upload(index: int) -> dict[str, Any]:
        requests = 0

        async def count_request(request: Request) -> None:
            nonlocal requests
            requests += 1

        async with AsyncClient(
            transport=ASGITransport(app=api_app), base_url="http://baseline",
            headers={"Authorization": f"Bearer {settings.master_token}"},
            event_hooks={"request": [count_request]},
        ) as client:
            filename = f"baseline-{index}.zip"
            response = await client.post("/archive/upload/init", json={"filename": filename, "size": len(payload)})
            assert response.status_code == 200, response.text
            upload_id = response.json()["upload_id"]
            path = f"/archive/upload/{upload_id}"
            chunk_size = 1024 * 1024
            conflict_status = None
            for offset in range(0, len(payload), chunk_size):
                response = await client.patch(path, content=payload[offset:offset + chunk_size], headers={"Upload-Offset": str(offset)})
                assert response.status_code == 200, response.text
                assert response.json()["offset"] == offset + chunk_size
                if offset == 0:
                    conflict = await client.patch(path, content=b"stale", headers={"Upload-Offset": "0"})
                    conflict_status = conflict.status_code
                    assert conflict_status == 409
                    assert conflict.json()["detail"]["offset"] == chunk_size
            duplicate = await client.patch(path, content=b"stale", headers={"Upload-Offset": "0"})
            assert duplicate.status_code == 200
            assert duplicate.json()["offset"] == len(payload)
            status = await client.head(path)
            assert status.status_code == 204
            assert int(status.headers["Upload-Offset"]) == len(payload)
            assert not (settings.archive_path / filename).exists()
            hashed = await client.get(path + "/sha256/stream")
            assert hashed.status_code == 200
            assert hashed.headers["content-type"].startswith("text/event-stream")
            events = [json.loads(line.removeprefix("data: ")) for line in hashed.text.splitlines() if line.startswith("data: ")]
            assert events[0]["event_type"] == "start"
            assert events[-1]["event_type"] == "complete"
            assert events[-1]["sha256"] == digest
            verified = await client.post(path + "/verify", json={"sha256": digest})
            assert verified.status_code == 200, verified.text
            assert (settings.archive_path / filename).read_bytes() == payload
            return {"bytes": len(payload), "chunk_bytes": chunk_size, "requests": requests,
                    "sha256": digest, "stale_offset_status": conflict_status,
                    "completed_retry_status": duplicate.status_code,
                    "sse_event_types": sorted({event["event_type"] for event in events})}

    tree = root / "search"
    tree.mkdir()
    for index in range(256):
        directory = tree / str(index % 16)
        directory.mkdir(exist_ok=True)
        (directory / f"region-{index:03d}.mca").write_bytes(payload[:4096])

    async def search(index: int) -> dict[str, Any]:
        found = await search_files(tree, FileSearchRequest(regex=r"\.mca$"))
        assert len(found) == 256
        assert sum(item.size for item in found) == 256 * 4096
        return {"files": len(found), "bytes": sum(item.size for item in found)}

    async def restore(index: int) -> dict[str, Any]:
        repository = root / f"restic-{index}"
        source = root / f"source-{index}"
        target = root / f"restored-{index}"
        source.mkdir()
        (source / "region.mca").write_bytes(payload)
        client = ResticClient(str(repository), password=None)
        await exec_command(str(client.binary_path), "init", "--insecure-no-password", env=client.env)
        snapshot = await client.backup([source])
        events = [event async for event in client.restore(snapshot.id, source_dir=source, target_dir=target)]
        recovered = (target / "region.mca").read_bytes()
        assert recovered == payload
        assert events
        return {"bytes": len(recovered), "sha256": hashlib.sha256(recovered).hexdigest(), "events": len(events)}

    async def chunks(index: int) -> dict[str, Any]:
        region = root / f"r.{index}.0.mca"
        region.write_bytes(b"\0" * 8192)
        async with remove_chunks(target_mca=region, chunks=[(0, 0)], owned_by=region) as process:
            events = [event async for event in process.events(MCMAP_REMOVE_CHUNKS_EVENT_ADAPTER)]
            stderr = await process.stderr()
            assert process.returncode in (0, None), stderr
        assert events[-1].type == "result"
        assert region.read_bytes() == b"\0" * 8192
        return {"region_bytes": region.stat().st_size, "event_types": [event.type for event in events]}

    await measure("upload_hash_publish", upload)
    await measure("file_search", search)
    await measure("restic_backup_restore", restore)
    await measure("mcmap_remove_empty_chunk", chunks)
    return results


async def run_owned_workloads(root: Path, samples: int) -> tuple[dict[str, str], dict[str, Any]]:
    from app.utils.exec import exec_command

    configuration = importlib.import_module("app.config")
    runtime = importlib.import_module("app.runtime").Runtime() if hasattr(configuration, "get_settings") else None
    with runtime.bind() if runtime is not None else nullcontext():
        try:
            settings = application_settings()
            versions = {}
            for name, command in {
                "fd": [str(settings.fd_binary_path), "--version"],
                "restic": [str(settings.restic_binary_path), "version"],
                "mcmap": [str(settings.mcmap_binary_path), "--version"],
            }.items():
                versions[name] = (await exec_command(*command, env=dict(os.environ))).strip()
            return versions, await workloads(root, samples)
        finally:
            if runtime is not None:
                await runtime.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=3)
    parser.add_argument("--label", default="working-tree")
    parser.add_argument("--app-ref", help="Run the app from a local Git revision in an isolated archive")
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    if args.app_ref:
        backend = Path(__file__).resolve().parents[2]
        revision = subprocess.check_output(
            ["git", "rev-parse", "--verify", args.app_ref + "^{commit}"], cwd=backend, text=True,
        ).strip()
        archive = subprocess.check_output(["git", "archive", revision, "backend/app"], cwd=backend.parent)
        with tempfile.TemporaryDirectory(prefix="mc-admin-baseline-source-") as directory:
            root = Path(directory)
            with tarfile.open(fileobj=io.BytesIO(archive)) as source:
                source.extractall(root, filter="data")
            subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--output", str(args.output.resolve()),
                 "--samples", str(args.samples), "--label", revision],
                cwd=root, env=dict(os.environ, PYTHONPATH=os.pathsep.join([str(root / "backend"), str(backend)])), check=True,
            )
        return
    environment = configure_test_environment()
    try:
        versions, results = asyncio.run(run_owned_workloads(Path(environment.name), args.samples))
        report = {
            "application_source": args.label, "python": platform.python_version(),
            "platform": platform.platform(), "binaries": versions,
            "samples": args.samples,
            "workloads": results,
            "process_peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            "limits": "Synthetic local workloads, warm process, ASGI in-process HTTP; RSS is process-wide. Empty-region mcmap protocol only, not rendering performance. No Docker or network services.",
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
        print(f"Wrote {args.output}")
    finally:
        environment.cleanup()


if __name__ == "__main__":
    main()
