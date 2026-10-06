"""Known, empty and degraded observations remain read-only."""

from unittest.mock import AsyncMock

import pytest

from app.dns.manager import SimpleDNSManager
from app.dns.types import ReturnRecordT
from tests.dns.test_reconciliation import connectivity as connectivity_fixture

connectivity = connectivity_fixture


async def test_observe_uninitialized_adapters_reports_unknown(connectivity, monkeypatch):
    manager = SimpleDNSManager(configuration=lambda: connectivity.configuration, docker_manager=connectivity.manager._docker_manager)
    monkeypatch.setattr(manager, "_ensure_up_to_date_config", AsyncMock())
    async with connectivity.db() as db:
        observed = await manager.observe(db)
    assert observed.state == "degraded" and not observed.dns_known and not observed.router_known
    assert not observed.empty_desired


async def test_observe_empty_desired_state_retains_remote_state(connectivity):
    retained_record = ReturnRecordT(sub_domain="*.mc", value="192.0.2.8", record_id="retained", record_type="A", ttl=600)
    connectivity.provider.records = [retained_record]
    connectivity.router.routes = {"survival.mc.example.com": "localhost:25566"}
    connectivity.configuration.addresses = []
    async with connectivity.db() as db:
        observed = await connectivity.manager.observe(db)
    assert observed.state == "empty" and observed.empty_desired
    assert observed.dns_known and observed.router_known
    assert observed.dns_diff is not None and not any(observed.dns_diff)
    assert observed.router_diff is not None and not observed.router_diff.pending
    assert connectivity.provider.calls == [] and connectivity.router.calls == []
    assert connectivity.provider.records == [retained_record]
    assert connectivity.router.routes == {"survival.mc.example.com": "localhost:25566"}


async def test_observe_successful_calculation_without_writes(connectivity):
    async with connectivity.db() as db:
        observed = await connectivity.manager.observe(db)
    dns, router = observed.dns_diff, observed.router_diff
    assert dns is not None and router is not None and observed.state == "pending"
    assert {record.sub_domain for record in dns.records_to_add} == {"*.mc", "_minecraft._tcp.survival.mc"}
    assert not dns.records_to_remove and not dns.records_to_update
    assert router.as_dict() == {"routes_to_add": {"survival.mc.example.com": "localhost:25565"}, "routes_to_remove": {}, "routes_to_update": {}}
    assert connectivity.provider.calls == []
    assert connectivity.router.calls == []


async def test_observe_router_differences_without_writes(connectivity):
    connectivity.router.routes = {"survival.mc.example.com": "localhost:25566", "obsolete.mc.example.com": "localhost:25567"}
    async with connectivity.db() as db:
        observed = await connectivity.manager.observe(db)
    assert observed.router_diff is not None
    router = observed.router_diff.as_dict()
    assert router["routes_to_update"] == {"survival.mc.example.com": {"current": "localhost:25566", "target": "localhost:25565"}}
    assert router["routes_to_remove"] == {"obsolete.mc.example.com": "localhost:25567"}
    assert not router["routes_to_add"]
    assert connectivity.provider.calls == [] and connectivity.router.calls == []


@pytest.mark.parametrize("adapter", ["provider", "router"])
async def test_observe_does_not_turn_unknown_into_empty(connectivity, adapter):
    getattr(connectivity, adapter).unavailable = True
    async with connectivity.db() as db:
        observed = await connectivity.manager.observe(db)
    assert observed.state == "degraded" and not observed.empty_desired
    assert observed.dns_known == (adapter != "provider")
    assert observed.router_known == (adapter != "router")
    assert connectivity.provider.calls == []
    assert connectivity.router.calls == []


async def test_observe_inventory_error_does_not_authorize_changes(connectivity, monkeypatch):
    monkeypatch.setattr("app.servers.crud.get_active_servers", AsyncMock(side_effect=RuntimeError("unavailable")))
    async with connectivity.db() as db:
        observed = await connectivity.manager.observe(db)
    assert observed.state == "degraded" and not observed.dns_known and not observed.router_known
    assert not observed.empty_desired
    assert connectivity.provider.calls == []
    assert connectivity.router.calls == []
