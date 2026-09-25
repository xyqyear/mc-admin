"""Real database inputs and stateful adapters verify incremental reconciliation."""

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.metadata import Base
from app.dns.dns import DNSClient
from app.dns.manager import SimpleDNSManager
from app.dns.router import MCRouterClient
from app.dns.types import ReturnRecordT
from app.dynamic_config.configs.dns import DNSManagerConfig, DNSPod, Manual
from app.errors import PublicOperationError
from app.servers.models import Server, ServerStatus


class StatefulDNS(DNSClient):
    def __init__(self):
        self.records = []
        self.calls = []
        self.unavailable = False
        self.fail_name = None
        self.next_id = 1
        self.started: asyncio.Event | None = None
        self.release: asyncio.Event | None = None
        self.closed = False

    def get_domain(self):
        return "example.com"

    def is_initialized(self):
        return True

    async def list_records(self):
        if self.unavailable:
            raise OSError("synthetic-provider-secret")
        return list(self.records)

    async def add_records(self, records):
        for record in records:
            self.calls.append(("add", record.sub_domain))
            if self.started is not None:
                self.started.set()
                assert self.release is not None
                await self.release.wait()
            if record.sub_domain == self.fail_name:
                raise OSError("synthetic-provider-secret")
            self.records.append(ReturnRecordT(record.sub_domain, record.value, self.next_id, record.record_type, record.ttl))
            self.next_id += 1

    async def remove_records(self, record_ids):
        self.calls.extend(("remove", identifier) for identifier in record_ids)
        self.records = [record for record in self.records if record.record_id not in record_ids]

    def has_update_capability(self):
        return True

    async def _update_records_batch(self, records):
        for record in records:
            self.calls.append(("update", record.sub_domain))
            self.records = [record if current.record_id == record.record_id else current for current in self.records]

    async def close(self):
        self.closed = True


class StatefulRouter(MCRouterClient):
    def __init__(self):
        self.routes = {}
        self.calls = []
        self.unavailable = False
        self.fail_name = None
        self.closed = False

    async def _send_request(self, method, path, headers=None, json=None):
        if method == "GET":
            if self.unavailable:
                raise OSError("synthetic-router-secret")
            return {key: {"backend": value} for key, value in self.routes.items()}
        self.calls.append((method, path, json))
        if method == "POST":
            assert json is not None
            if json["serverAddress"] == self.fail_name:
                raise OSError("synthetic-router-secret")
            self.routes[json["serverAddress"]] = json["backend"]
        elif method == "DELETE":
            self.routes.pop(path.removeprefix("routes/"), None)
        return None

    async def close(self):
        self.closed = True


@pytest.fixture
async def connectivity(isolated_runtime):
    runtime = isolated_runtime
    async with runtime.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    db = runtime.database.session_factory
    async with db() as session:
        now = datetime.now(UTC)
        session.add(Server(server_id="survival", status=ServerStatus.ACTIVE, created_at=now, updated_at=now))
        await session.commit()
    ports = {"survival": 25565}

    class Instance:
        def __init__(self, server_id):
            self.server_id = server_id

        async def get_server_info(self):
            port = ports[self.server_id]
            if isinstance(port, Exception):
                raise port
            return SimpleNamespace(game_port=port)

    configuration = DNSManagerConfig(enabled=True, dns=DNSPod(), addresses=[Manual()])
    docker_manager = MagicMock()
    docker_manager.get_instance.side_effect = Instance
    manager = SimpleDNSManager(configuration=lambda: configuration, docker_manager=docker_manager)
    provider, router = StatefulDNS(), StatefulRouter()
    manager._dns_client = provider
    manager._mc_router_client = router
    manager._last_config_hash = manager._calculate_config_hash(configuration)
    yield SimpleNamespace(manager=manager, provider=provider, router=router, configuration=configuration, db=db, ports=ports)
    await manager.close()


async def synchronize(system):
    async with system.db() as db:
        return await system.manager.update(db)


async def observe(system):
    async with system.db() as db:
        return await system.manager.observe(db)


async def test_failed_provider_initialization_keeps_router_available(connectivity, monkeypatch, caplog):
    system = connectivity
    manager = SimpleDNSManager(configuration=lambda: system.configuration)
    provider, router = StatefulDNS(), StatefulRouter()
    monkeypatch.setattr(provider, "is_initialized", lambda: False)
    monkeypatch.setattr(provider, "init", AsyncMock(side_effect=OSError("synthetic-provider-secret")))
    monkeypatch.setattr("app.dns.manager.DNSPodClient", lambda *args: provider)
    monkeypatch.setattr("app.dns.manager.MCRouterClient", lambda *args: router)

    await manager.initialize()
    assert provider.closed
    assert not router.closed
    assert manager._dns_client is None
    assert manager._mc_router_client is router
    assert not manager.is_initialized
    assert "synthetic-provider-secret" not in caplog.text
    assert "initialized successfully" not in caplog.text
    await manager.close()
    assert router.closed
    assert manager._owned_clients == []


async def test_failed_initialization_cleanup_retains_only_unclosed_clients(connectivity, monkeypatch):
    manager = SimpleDNSManager(configuration=lambda: connectivity.configuration)
    provider, router = StatefulDNS(), StatefulRouter()
    monkeypatch.setattr(provider, "is_initialized", lambda: False)
    monkeypatch.setattr(provider, "init", AsyncMock(side_effect=OSError("initialization failed")))
    close_provider = AsyncMock(side_effect=[OSError("close failed"), None])
    monkeypatch.setattr(provider, "close", close_provider)
    monkeypatch.setattr("app.dns.manager.DNSPodClient", lambda *args: provider)
    monkeypatch.setattr("app.dns.manager.MCRouterClient", lambda *args: router)

    with pytest.raises(ExceptionGroup, match="DNS 客户端关闭失败"):
        await manager.initialize()
    assert router.closed
    assert manager._owned_clients == [provider]
    assert manager._dns_client is None
    assert manager._mc_router_client is None
    await manager.close()
    assert close_provider.await_count == 2
    assert manager._owned_clients == []


async def test_unchanged_plan_performs_no_writes(connectivity):
    system = connectivity
    assert (await observe(system)).state == "pending"
    await synchronize(system)
    assert (await observe(system)).state == "ready"
    system.provider.calls.clear()
    system.router.calls.clear()
    await synchronize(system)
    assert system.provider.calls == []
    assert system.router.calls == []


@pytest.mark.parametrize("unavailable", ["provider", "router"])
async def test_unknown_endpoint_is_preserved_while_known_endpoint_converges(connectivity, unavailable, caplog):
    system = connectivity
    adapter = getattr(system, unavailable)
    adapter.unavailable = True
    with pytest.raises(PublicOperationError):
        await synchronize(system)
    state = await observe(system)
    assert state.state == "degraded"
    assert state.dns_known is (unavailable != "provider")
    assert state.router_known is (unavailable != "router")
    assert adapter.calls == []
    if unavailable == "provider":
        assert system.router.routes == {"survival.mc.example.com": "localhost:25565"}
    else:
        assert len(system.provider.records) == 2
    assert "synthetic-provider-secret" not in caplog.text
    assert "synthetic-router-secret" not in caplog.text
    adapter.unavailable = False
    await synchronize(system)
    assert (await observe(system)).state == "ready"


async def test_unreadable_active_server_suppresses_deletions_but_allows_known_writes(connectivity):
    system = connectivity
    await synchronize(system)
    system.router.routes["obsolete.mc.example.com"] = "localhost:25566"
    system.provider.records.append(ReturnRecordT("_minecraft._tcp.obsolete.mc", "0 5 25565 obsolete.mc.example.com", 99, "SRV", 15))
    async with system.db() as session:
        now = datetime.now(UTC)
        session.add(Server(server_id="unreadable", status=ServerStatus.ACTIVE, created_at=now, updated_at=now))
        session.add(Server(server_id="creative", status=ServerStatus.ACTIVE, created_at=now, updated_at=now))
        await session.commit()
    system.ports["unreadable"] = PermissionError("owned compose unreadable")
    system.ports["creative"] = 25567
    with pytest.raises(PublicOperationError):
        await synchronize(system)
    state = await observe(system)
    assert state.unknown_servers == ("unreadable",)
    assert state.state == "degraded"
    assert system.router.routes["obsolete.mc.example.com"] == "localhost:25566"
    assert system.router.routes["creative.mc.example.com"] == "localhost:25567"
    assert any(record.record_id == 99 for record in system.provider.records)
    system.ports["unreadable"] = 25568
    await synchronize(system)
    assert "obsolete.mc.example.com" not in system.router.routes
    assert not any(record.record_id == 99 for record in system.provider.records)
    assert (await observe(system)).state == "ready"


@pytest.mark.parametrize("empty", ["addresses", "servers"])
async def test_empty_desired_state_preserves_existing_connectivity(connectivity, empty):
    from sqlalchemy import delete

    system = connectivity
    await synchronize(system)
    original_records = list(system.provider.records)
    original_routes = dict(system.router.routes)
    if empty == "addresses":
        system.configuration.addresses = []
    else:
        async with system.db() as db:
            await db.execute(delete(Server))
            await db.commit()
    await synchronize(system)
    state = await observe(system)
    assert state.state == "empty"
    assert state.empty_desired
    assert system.provider.records == original_records
    assert system.router.routes == original_routes


@pytest.mark.parametrize("failed", ["provider", "router"])
async def test_target_failure_does_not_cancel_unrelated_writes_and_retry_is_fresh(connectivity, failed):
    system = connectivity
    async with system.db() as session:
        now = datetime.now(UTC)
        session.add(Server(server_id="creative", status=ServerStatus.ACTIVE, created_at=now, updated_at=now))
        await session.commit()
    system.ports["creative"] = 25567
    adapter = getattr(system, failed)
    adapter.fail_name = "_minecraft._tcp.survival.mc" if failed == "provider" else "survival.mc.example.com"
    with pytest.raises(PublicOperationError):
        await synchronize(system)
    assert "creative.mc.example.com" in system.router.routes
    assert any(record.sub_domain == "_minecraft._tcp.creative.mc" for record in system.provider.records)
    assert (await observe(system)).state == "degraded"
    adapter.fail_name = None
    await synchronize(system)
    assert (await observe(system)).state == "ready"
    assert len(system.provider.records) == 3
    assert len(system.router.routes) == 2


async def test_cancelled_update_drains_writes_before_closing_clients(connectivity):
    system = connectivity
    system.provider.started = asyncio.Event()
    system.provider.release = asyncio.Event()
    update = asyncio.create_task(synchronize(system))
    close = None
    try:
        await asyncio.wait_for(system.provider.started.wait(), 5)
        update.cancel()
        close = asyncio.create_task(system.manager.close())
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(asyncio.shield(close), 0.05)
        assert not system.provider.closed
        assert not update.done()
    finally:
        system.provider.release.set()
        results = await asyncio.wait_for(asyncio.gather(update, *([close] if close is not None else []), return_exceptions=True), 5)
    assert isinstance(results[0], asyncio.CancelledError)
    assert system.provider.closed and system.router.closed
    assert len(system.provider.records) == 2
