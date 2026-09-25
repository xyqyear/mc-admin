import asyncio
import json
import uuid

import httpx2
import pytest

pytestmark = pytest.mark.docker

from app.dns.router import MCRouterClient

ROUTER_IMAGE = "itzg/mc-router@sha256:e06735ea74877a7de649bcaec4cb917bf952564d32cbe258670fb7753192a1e9"


async def docker(*args: str, required: bool = True) -> str:
    process = await asyncio.create_subprocess_exec(
        "docker", "--host", "unix:///var/run/docker.sock", *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=180)
    except TimeoutError:
        process.kill()
        await process.communicate()
        raise
    if process.returncode:
        message = stderr.decode()
        missing = "No such object" in message or "No such container" in message
        if required or not missing:
            raise RuntimeError(f"docker {args[0]} failed: {message}")
    return stdout.decode().strip()


async def test_router_api_contract_with_docker(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    environment_id = uuid.uuid4().hex[:12]
    name = f"mca-router-pytest-{environment_id}"
    client = None
    try:
        await docker(
            "create", "--name", name,
            "--label", f"io.mc-admin.e2e.environment={environment_id}",
            "--label", "io.mc-admin.e2e.run=e2e-router-pytest",
            "--publish", "127.0.0.1::26666", ROUTER_IMAGE,
            "--api-binding", "0.0.0.0:26666",
        )
        await docker("start", name)
        info = json.loads(await docker("inspect", name))[0]
        port = info["NetworkSettings"]["Ports"]["26666/tcp"][0]["HostPort"]
        client = MCRouterClient(f"http://127.0.0.1:{port}")

        async with asyncio.timeout(30):
            while True:
                try:
                    assert await client.get_routes() == {}
                    break
                except httpx2.HTTPError:
                    await asyncio.sleep(0.2)

        original = {"one.e2e.invalid": "localhost:25565", "two.e2e.invalid": "localhost:25566", "stable.e2e.invalid": "localhost:25569"}
        await client.override_routes(original)
        assert await client.get_routes() == original
        assert await client.get_routes_diff(original) == {
            "routes_to_add": {}, "routes_to_remove": {}, "routes_to_update": {},
        }

        request = client._send_request
        mutations = []

        async def observe_route_availability(method, path, headers=None, json=None):
            if method != "GET":
                mutations.append((method, path, json))
                current = await request("GET", "routes")
                assert current is not None
                assert current["stable.e2e.invalid"]["backend"] == "localhost:25569"
            result = await request(method, path, headers=headers, json=json)
            if method != "GET":
                current = await request("GET", "routes")
                assert current is not None
                assert current["stable.e2e.invalid"]["backend"] == "localhost:25569"
            return result

        monkeypatch.setattr(client, "_send_request", observe_route_availability)
        await client.override_routes(original)
        assert mutations == []

        desired = {"one.e2e.invalid": "localhost:25567", "three.e2e.invalid": "localhost:25568", "stable.e2e.invalid": "localhost:25569"}
        assert await client.get_routes_diff(desired) == {
            "routes_to_add": {"three.e2e.invalid": "localhost:25568"},
            "routes_to_remove": {"two.e2e.invalid": "localhost:25566"},
            "routes_to_update": {"one.e2e.invalid": {"current": "localhost:25565", "target": "localhost:25567"}},
        }
        await client.override_routes(desired)
        assert await client.get_routes() == desired
        assert len(mutations) == 3
        assert [(method, path) for method, path, _ in mutations if method == "DELETE"] == [("DELETE", "routes/two.e2e.invalid")]
        assert {body["serverAddress"] for method, _, body in mutations if method == "POST"} == {"one.e2e.invalid", "three.e2e.invalid"}
        monkeypatch.setattr(client, "_send_request", request)
        await client._remove_route("three.e2e.invalid")
        assert await client.get_routes() == {"one.e2e.invalid": "localhost:25567", "stable.e2e.invalid": "localhost:25569"}
        missing = await client._client.request(
            "DELETE", client._base_url + "routes/three.e2e.invalid"
        )
        assert missing.status_code == 404
        await client._remove_route("three.e2e.invalid")
        await client._remove_route("never-created.e2e.invalid")
        assert await client.get_routes() == {"one.e2e.invalid": "localhost:25567", "stable.e2e.invalid": "localhost:25569"}
        await client.override_routes({})
        assert await client.get_routes() == {}
        await client.override_routes({})
        assert await client.get_routes() == {}
    finally:
        try:
            if client is not None:
                await client.close()
        finally:
            ownership = await docker(
                "inspect", "--format", '{{index .Config.Labels "io.mc-admin.e2e.environment"}}', name,
                required=False,
            )
            if ownership:
                assert ownership == environment_id, "refusing to delete a container with different ownership"
                await docker("rm", "-f", name)
