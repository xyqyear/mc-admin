"""MC Router client tests."""

from unittest.mock import AsyncMock, patch

import pytest

from app.dns.router import MCRouterClient


class MockAsyncContext:
    def __init__(self, response):
        self._response = response

    async def __aenter__(self):
        return self._response

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return None


@pytest.fixture
def mock_client():
    client = AsyncMock()
    return client


@pytest.fixture
def router_client():
    with patch("app.dns.router.httpx.AsyncClient"):
        client = MCRouterClient("http://localhost:26666")
        client._client = AsyncMock()
        return client


@pytest.mark.asyncio
async def test_get_routes(router_client):
    expected_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
    }

    router_client._send_request = AsyncMock(return_value=expected_routes)

    routes = await router_client.get_routes()

    assert routes == expected_routes
    router_client._send_request.assert_called_once_with(
        "GET", "routes", headers={"Accept": "application/json"}
    )


@pytest.mark.asyncio
async def test_get_routes_empty_response(router_client):
    router_client._send_request = AsyncMock(return_value=None)

    routes = await router_client.get_routes()

    assert routes is None


@pytest.mark.asyncio
async def test_add_route(router_client):
    router_client._send_request = AsyncMock(return_value=None)

    await router_client._add_route("vanilla.mc.example.com", "localhost:25565")

    router_client._send_request.assert_called_once_with(
        "POST",
        "routes",
        headers={"Content-Type": "application/json"},
        json={"serverAddress": "vanilla.mc.example.com", "backend": "localhost:25565"},
    )


@pytest.mark.asyncio
async def test_remove_route(router_client):
    router_client._send_request = AsyncMock(return_value=None)

    await router_client._remove_route("vanilla.mc.example.com")

    router_client._send_request.assert_called_once_with(
        "DELETE", "routes/vanilla.mc.example.com"
    )


@pytest.mark.asyncio
async def test_remove_all_routes(router_client):
    existing_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
    }

    router_client.get_routes = AsyncMock(return_value=existing_routes)

    router_client._remove_route = AsyncMock()

    await router_client._remove_all_routes()

    assert router_client._remove_route.call_count == 2
    router_client._remove_route.assert_any_call("vanilla.mc.example.com")
    router_client._remove_route.assert_any_call("modded.mc.example.com")


@pytest.mark.asyncio
async def test_add_routes(router_client):
    routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
    }

    router_client._add_route = AsyncMock()

    await router_client._add_routes(routes)

    assert router_client._add_route.call_count == 2
    router_client._add_route.assert_any_call(
        "vanilla.mc.example.com", "localhost:25565"
    )
    router_client._add_route.assert_any_call("modded.mc.example.com", "localhost:25566")


@pytest.mark.asyncio
async def test_override_routes(router_client):
    new_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
    }

    router_client._remove_all_routes = AsyncMock()
    router_client._add_routes = AsyncMock()

    await router_client.override_routes(new_routes)

    router_client._remove_all_routes.assert_called_once()
    router_client._add_routes.assert_called_once_with(new_routes)


@pytest.mark.asyncio
async def test_override_routes_empty(router_client):
    router_client._remove_all_routes = AsyncMock()
    router_client._add_routes = AsyncMock()

    await router_client.override_routes({})

    router_client._remove_all_routes.assert_called_once()
    router_client._add_routes.assert_not_called()


@pytest.mark.asyncio
async def test_get_routes_diff_no_changes(router_client):
    current_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
    }
    target_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
    }

    router_client.get_routes = AsyncMock(return_value=current_routes)

    diff = await router_client.get_routes_diff(target_routes)

    assert diff == {"routes_to_add": {}, "routes_to_remove": {}, "routes_to_update": {}}


@pytest.mark.asyncio
async def test_get_routes_diff_add_routes(router_client):
    current_routes = {
        "vanilla.mc.example.com": "localhost:25565",
    }
    target_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
        "creative.mc.example.com": "localhost:25567",
    }

    router_client.get_routes = AsyncMock(return_value=current_routes)

    diff = await router_client.get_routes_diff(target_routes)

    assert diff == {
        "routes_to_add": {
            "modded.mc.example.com": "localhost:25566",
            "creative.mc.example.com": "localhost:25567",
        },
        "routes_to_remove": {},
        "routes_to_update": {},
    }


@pytest.mark.asyncio
async def test_get_routes_diff_remove_routes(router_client):
    current_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
        "old_server.mc.example.com": "localhost:25567",
    }
    target_routes = {
        "vanilla.mc.example.com": "localhost:25565",
    }

    router_client.get_routes = AsyncMock(return_value=current_routes)

    diff = await router_client.get_routes_diff(target_routes)

    assert diff == {
        "routes_to_add": {},
        "routes_to_remove": {
            "modded.mc.example.com": "localhost:25566",
            "old_server.mc.example.com": "localhost:25567",
        },
        "routes_to_update": {},
    }


@pytest.mark.asyncio
async def test_get_routes_diff_update_routes(router_client):
    current_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
    }
    target_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25567",
    }

    router_client.get_routes = AsyncMock(return_value=current_routes)

    diff = await router_client.get_routes_diff(target_routes)

    assert diff == {
        "routes_to_add": {},
        "routes_to_remove": {},
        "routes_to_update": {
            "modded.mc.example.com": {
                "current": "localhost:25566",
                "target": "localhost:25567",
            }
        },
    }


@pytest.mark.asyncio
async def test_get_routes_diff_mixed_operations(router_client):
    current_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
        "old_server.mc.example.com": "localhost:25567",
    }
    target_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25568",
        "new_server.mc.example.com": "localhost:25569",
    }

    router_client.get_routes = AsyncMock(return_value=current_routes)

    diff = await router_client.get_routes_diff(target_routes)

    assert diff == {
        "routes_to_add": {
            "new_server.mc.example.com": "localhost:25569",
        },
        "routes_to_remove": {
            "old_server.mc.example.com": "localhost:25567",
        },
        "routes_to_update": {
            "modded.mc.example.com": {
                "current": "localhost:25566",
                "target": "localhost:25568",
            }
        },
    }


@pytest.mark.asyncio
async def test_get_routes_diff_empty_current_routes(router_client):
    current_routes = {}
    target_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
    }

    router_client.get_routes = AsyncMock(return_value=current_routes)

    diff = await router_client.get_routes_diff(target_routes)

    assert diff == {
        "routes_to_add": {
            "vanilla.mc.example.com": "localhost:25565",
            "modded.mc.example.com": "localhost:25566",
        },
        "routes_to_remove": {},
        "routes_to_update": {},
    }


@pytest.mark.asyncio
async def test_get_routes_diff_empty_target_routes(router_client):
    current_routes = {
        "vanilla.mc.example.com": "localhost:25565",
        "modded.mc.example.com": "localhost:25566",
    }
    target_routes = {}

    router_client.get_routes = AsyncMock(return_value=current_routes)

    diff = await router_client.get_routes_diff(target_routes)

    assert diff == {
        "routes_to_add": {},
        "routes_to_remove": {
            "vanilla.mc.example.com": "localhost:25565",
            "modded.mc.example.com": "localhost:25566",
        },
        "routes_to_update": {},
    }


@pytest.mark.asyncio
async def test_close(router_client):
    await router_client.close()

    router_client._client.aclose.assert_called_once()


def test_base_url_normalization():
    with patch("app.dns.router.httpx.AsyncClient"):
        client1 = MCRouterClient("http://localhost:26666")
        assert client1._base_url == "http://localhost:26666/"

        client2 = MCRouterClient("http://localhost:26666/")
        assert client2._base_url == "http://localhost:26666/"


def test_timeout_configuration():
    with patch("app.dns.router.httpx.AsyncClient") as client_mock:
        MCRouterClient("http://localhost:26666")

        client_mock.assert_called_once_with(timeout=10.0)
