"""Known differences and compatibility errors use actual adapter observations."""

from unittest.mock import AsyncMock

import pytest

from app.dns.manager import SimpleDNSManager
from app.errors import PublicOperationError
from tests.dns.test_reconciliation import connectivity as connectivity_fixture

connectivity = connectivity_fixture


async def test_get_current_diff_manager_not_initialized(connectivity, monkeypatch):
    manager = SimpleDNSManager(configuration=lambda: connectivity.configuration)
    monkeypatch.setattr(manager, "_ensure_up_to_date_config", AsyncMock())
    async with connectivity.db() as db:
        with pytest.raises(RuntimeError, match="DNS manager not initialized"):
            await manager.get_current_diff(db)


async def test_get_current_diff_no_servers_or_addresses(connectivity):
    connectivity.configuration.addresses = []
    async with connectivity.db() as db:
        with pytest.raises(ValueError, match="No addresses or servers"):
            await connectivity.manager.get_current_diff(db)


async def test_get_current_diff_successful_calculation(connectivity):
    async with connectivity.db() as db:
        dns, router = await connectivity.manager.get_current_diff(db)
    assert {record.sub_domain for record in dns.records_to_add} == {"*.mc", "_minecraft._tcp.survival.mc"}
    assert not dns.records_to_remove and not dns.records_to_update
    assert router == {"routes_to_add": {"survival.mc.example.com": "localhost:25565"}, "routes_to_remove": {}, "routes_to_update": {}}
    assert connectivity.provider.calls == []
    assert connectivity.router.calls == []


async def test_get_current_diff_with_router_differences(connectivity):
    connectivity.router.routes = {"survival.mc.example.com": "localhost:25566", "obsolete.mc.example.com": "localhost:25567"}
    async with connectivity.db() as db:
        _, router = await connectivity.manager.get_current_diff(db)
    assert router["routes_to_update"] == {"survival.mc.example.com": {"current": "localhost:25566", "target": "localhost:25565"}}
    assert router["routes_to_remove"] == {"obsolete.mc.example.com": "localhost:25567"}
    assert not router["routes_to_add"]


@pytest.mark.parametrize("adapter", ["provider", "router"])
async def test_get_current_diff_does_not_turn_unknown_into_empty(connectivity, adapter):
    getattr(connectivity, adapter).unavailable = True
    async with connectivity.db() as db:
        with pytest.raises(PublicOperationError, match="网络状态未知"):
            await connectivity.manager.get_current_diff(db)
    assert connectivity.provider.calls == []
    assert connectivity.router.calls == []


async def test_get_current_diff_inventory_error_does_not_authorize_changes(connectivity, monkeypatch):
    monkeypatch.setattr("app.servers.crud.get_active_servers", AsyncMock(side_effect=RuntimeError("unavailable")))
    async with connectivity.db() as db:
        with pytest.raises(PublicOperationError, match="网络状态未知"):
            await connectivity.manager.get_current_diff(db)
    assert connectivity.provider.calls == []
    assert connectivity.router.calls == []
