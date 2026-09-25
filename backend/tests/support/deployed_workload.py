"""Measure public HTTP workloads in an owned E2E fixture without latency gates."""

import argparse
import hashlib
import json
import os
import statistics
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen


class Client:
    def __init__(self, fixture: dict[str, Any]) -> None:
        self.base_url: str = fixture["api_url"].rstrip("/")
        if urlparse(self.base_url).hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("Workloads require an owned local fixture")
        self.token: str = fixture["master_token"]
        self.requests: list[dict[str, Any]] = []

    def request(
        self, method: str, path: str, *, expected: int = 200,
        data: dict[str, Any] | None = None, body: bytes | None = None,
        headers: dict[str, str] | None = None, metric: str,
    ) -> tuple[bytes, dict[str, str]]:
        request_headers = {"Authorization": f"Bearer {self.token}"}
        if data is not None:
            body = json.dumps(data).encode()
            request_headers["Content-Type"] = "application/json"
        elif body is not None:
            request_headers["Content-Type"] = "application/octet-stream"
        request_headers.update(headers or {})
        request = Request(self.base_url + path, data=body, headers=request_headers, method=method)
        started = time.perf_counter()
        try:
            response = urlopen(request, timeout=180)
        except HTTPError as error:
            response = error
        with response:
            received = response.read()
            status = response.status
            response_headers = dict(response.headers.items())
        self.requests.append({
            "operation": metric, "method": method, "status": status,
            "request_body_bytes": len(body or b""), "response_body_bytes": len(received),
            "seconds": round(time.perf_counter() - started, 6),
        })
        if status != expected:
            raise AssertionError(f"{metric}: expected HTTP {expected}, got {status}")
        return received, response_headers

    def json(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        body, _ = self.request(method, path, **kwargs)
        return json.loads(body)


def stream_events(body: bytes) -> list[dict[str, Any]]:
    return [json.loads(line[5:].strip()) for line in body.decode().splitlines() if line.startswith("data:")]


def upload(client: Client, index: int) -> dict[str, Any]:
    payload = bytes(range(256)) * (4 * 1024 * 1024 // 256)
    digest = hashlib.sha256(payload).hexdigest()
    filename = f"workload-{index}.zip"
    created = client.json("POST", "/archive/upload/init", data={"filename": filename, "size": len(payload)}, metric="upload.init")
    path = "/archive/upload/" + created["upload_id"]
    chunk_size = 1024 * 1024
    for offset in range(0, len(payload), chunk_size):
        written = client.json("PATCH", path, body=payload[offset:offset + chunk_size], headers={"Upload-Offset": str(offset)}, metric="upload.chunk")
        assert written["offset"] == offset + chunk_size
        if offset == 0:
            conflict = client.json("PATCH", path, body=b"stale", headers={"Upload-Offset": "0"}, expected=409, metric="upload.stale-offset")
            assert conflict["detail"]["offset"] == chunk_size
    duplicate = client.json("PATCH", path, body=b"stale", headers={"Upload-Offset": "0"}, metric="upload.completed-retry")
    assert duplicate["offset"] == len(payload)
    _, headers = client.request("HEAD", path, expected=204, metric="upload.status")
    assert int({key.lower(): value for key, value in headers.items()}["upload-offset"]) == len(payload)
    hashed, _ = client.request("GET", path + "/sha256/stream", metric="upload.hash")
    events = stream_events(hashed)
    assert events[0]["event_type"] == "start"
    assert events[-1]["event_type"] == "complete" and events[-1]["sha256"] == digest
    client.request("POST", path + "/verify", data={"sha256": digest}, metric="upload.publish")
    published, _ = client.request("GET", "/archive/download?" + urlencode({"path": "/" + filename}), metric="upload.verify-download")
    assert published == payload
    return {
        "bytes": len(payload), "chunk_bytes": chunk_size, "sha256": digest,
        "stale_offset_status": 409, "completed_retry_status": 200,
        "sse_event_types": sorted({event["event_type"] for event in events}),
        "protocol_requests": 10, "verification_requests": 1,
    }


def backup_restore(client: Client, server_id: str, index: int) -> dict[str, Any]:
    name = f"workload-{index}"
    scope = "/" + name
    path = scope + "/value.txt"
    files = "/servers/" + server_id + "/files"
    content_path = files + "/content?" + urlencode({"path": path})
    payload = "0123456789abcdef" * (4 * 1024 * 1024 // 16)
    expected_bytes = payload.encode()
    client.request("POST", files + "/create", data={"path": "/", "name": name, "type": "directory"}, metric="restore.prepare-directory")
    client.request("POST", files + "/create", data={"path": scope, "name": "value.txt", "type": "file"}, metric="restore.prepare-file")
    client.request("POST", content_path, data={"content": payload}, metric="restore.prepare-content")
    snapshot = client.json("POST", "/snapshots", data={"server_id": server_id, "paths": [scope]}, metric="restore.backup")["snapshot"]
    assert snapshot["id"]
    client.request("POST", content_path, data={"content": "changed after backup"}, metric="restore.modify")
    streamed, _ = client.request("POST", "/snapshots/restore", data={"server_id": server_id, "snapshot_id": snapshot["id"], "paths": [scope]}, metric="restore.apply")
    events = stream_events(streamed)
    assert events[-1]["event_type"] == "complete"
    assert events[-1].get("safety_snapshot_id")
    restored, _ = client.request("GET", files + "/download?" + urlencode({"path": path}), metric="restore.verify-download")
    assert restored == expected_bytes
    return {
        "bytes": len(restored), "sha256": hashlib.sha256(restored).hexdigest(),
        "safety_snapshot": True, "terminal_event": events[-1]["event_type"],
        "sse_event_types": sorted({event["event_type"] for event in events}),
    }


def measure(client: Client, operation: Callable[[int], dict[str, Any]], samples: int) -> dict[str, Any]:
    durations, outcomes, requests = [], [], []
    for index in range(samples):
        start_index = len(client.requests)
        started = time.perf_counter()
        outcomes.append(operation(index))
        durations.append(round(time.perf_counter() - started, 6))
        requests.append(client.requests[start_index:])
    assert all(outcome == outcomes[0] for outcome in outcomes)
    assert all(len(sample) == len(requests[0]) for sample in requests)
    return {
        "seconds": durations, "median_seconds": statistics.median(durations),
        "behavior": outcomes[0], "requests_per_sample": len(requests[0]), "requests": requests,
        "body_bytes_per_sample": [{
            "sent": sum(request["request_body_bytes"] for request in sample),
            "received": sum(request["response_body_bytes"] for request in sample),
        } for sample in requests],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("--samples must be positive")
    fixture = json.loads(Path(os.environ["MC_ADMIN_BROWSER_FIXTURE"]).read_text())
    if not all(fixture.get(key) for key in ("run_id", "environment_id", "image_id", "server_id")):
        raise ValueError("Workloads require a complete owned server fixture")
    client = Client(fixture)
    result = {
        "application_source": args.label, "image_id": fixture["image_id"],
        "run_id": fixture["run_id"], "environment_id": fixture["environment_id"],
        "samples": args.samples, "authentication": "fixture master token",
        "limits": (
            "Sequential synthetic loopback HTTP in a fresh owned Backup fixture. "
            "Archive measurement includes a public download for byte verification. "
            "Ordinary-file restore includes fixture writes and public byte verification; "
            "per-request timings separate backup and restore. Request/response bytes exclude headers. "
            "No latency thresholds, production-load claim or browser rendering measurement."
        ),
        "workloads": {
            "upload_hash_publish": measure(client, lambda index: upload(client, index), args.samples),
            "ordinary_file_backup_restore": measure(client, lambda index: backup_restore(client, fixture["server_id"], index), args.samples),
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(f"Measured deployed workloads: {args.output}")


if __name__ == "__main__":
    main()
