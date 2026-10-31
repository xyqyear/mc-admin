"""SimpleDNSManager tests."""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.dns.dns import DNSClient
from app.dns.manager import AddressInfo, SimpleDNSManager
from app.dns.planning import RouteEntry, generate_dns_records, generate_routes
from app.dns.router import MCRouterClient
from app.dns.types import AddRecordT, ReturnRecordT
from app.dynamic_config.configs.dns import DNSManagerConfig, DNSPod, Huawei, Manual
from app.errors import PublicOperationError
from tests.dns.fakes import StatefulDNS, StatefulRouter
from tests.dns.helpers import patch_accessor


class MockDNSClient(DNSClient):
    def __init__(self, domain="example.com"):
        self._domain = domain
        self._initialized = True
        self.records = []

    def get_domain(self) -> str:
        return self._domain

    def is_initialized(self) -> bool:
        return self._initialized

    async def init(self):
        self._initialized = True

    async def list_records(self):
        return self.records

    async def list_relevant_records(self, managed_sub_domain):
        self.last_managed_sub_domain = managed_sub_domain
        return self.records

    def has_update_capability(self) -> bool:
        return True

    async def remove_records(self, record_ids):
        self.records = [record for record in self.records if record.record_id not in record_ids]

    async def add_records(self, records):
        self.last_update_call = [*getattr(self, "last_update_call", []), *records]
        self.records.extend(ReturnRecordT(record.sub_domain, record.value, len(self.records) + index + 1, record.record_type, record.ttl) for index, record in enumerate(records))

    async def _update_records_batch(self, records):
        for record in records:
            self.records = [record if current.record_id == record.record_id else current for current in self.records]


class MockMCRouterClient(MCRouterClient):
    def __init__(self, base_url):
        # Bypass super().__init__ to avoid creating a real HTTP client session.
        self.base_url = base_url
        self.routes = {}

    async def get_routes(self):
        return self.routes

    async def _add_route(self, route, backend):
        self.routes[route] = backend

    async def _remove_route(self, route):
        self.routes.pop(route, None)


    async def close(self):
        pass












@pytest.mark.asyncio
async def test_initialize_disabled():
    dns_manager = SimpleDNSManager()

    mock_config = DNSManagerConfig.model_validate({"enabled": False})

    with patch_accessor("app.dns.manager.get_config") as config_mock:
        config_mock.dns = mock_config

        await dns_manager.initialize()

        assert not dns_manager.is_initialized


@pytest.mark.parametrize("record_type,value", [("A", "1.2.3.4"), ("AAAA", "2001:db8::1"), ("CNAME", "proxy.example.net")])
def test_generate_dns_records(record_type, value):
    addresses = {
        "*": AddressInfo(type=record_type, host=value, port=25565),
        "backup": AddressInfo(type="A", host="5.6.7.8", port=25566),
    }

    server_list = ["vanilla", "modded"]
    managed_sub_domain = "mc"
    dns_ttl = 300

    records = generate_dns_records(
        addresses, server_list, managed_sub_domain, dns_ttl, "example.com"
    )

    assert [record._asdict() for record in records] == [
        {"sub_domain": "*.mc", "value": value, "record_type": record_type, "ttl": 300},
        {"sub_domain": "_minecraft._tcp.vanilla.mc", "value": "0 5 25565 vanilla.mc.example.com", "record_type": "SRV", "ttl": 300},
        {"sub_domain": "_minecraft._tcp.modded.mc", "value": "0 5 25565 modded.mc.example.com", "record_type": "SRV", "ttl": 300},
        {"sub_domain": "*.backup.mc", "value": "5.6.7.8", "record_type": "A", "ttl": 300},
        {"sub_domain": "_minecraft._tcp.vanilla.backup.mc", "value": "0 5 25566 vanilla.backup.mc.example.com", "record_type": "SRV", "ttl": 300},
        {"sub_domain": "_minecraft._tcp.modded.backup.mc", "value": "0 5 25566 modded.backup.mc.example.com", "record_type": "SRV", "ttl": 300},
    ]


def test_generate_routes():
    addresses = {
        "*": AddressInfo(type="A", host="1.2.3.4", port=25565),
        "backup": AddressInfo(type="A", host="5.6.7.8", port=25566),
    }

    servers = {"vanilla": 25565, "modded": 25566}
    managed_sub_domain = "mc"
    domain = "example.com"

    routes = generate_routes(
        addresses, servers, managed_sub_domain, domain
    )

    assert routes == [
        RouteEntry("vanilla.mc.example.com", "localhost:25565"),
        RouteEntry("vanilla.backup.mc.example.com", "localhost:25565"),
        RouteEntry("modded.mc.example.com", "localhost:25566"),
        RouteEntry("modded.backup.mc.example.com", "localhost:25566"),
    ]




@pytest.mark.asyncio
async def test_update_not_initialized(db_session):
    dns_manager = SimpleDNSManager()

    dns_manager._ensure_up_to_date_config = AsyncMock()

    with (
        patch_accessor("app.dns.manager.get_config") as config_mock,
        patch("app.servers.crud.get_active_servers", AsyncMock(side_effect=OSError("unavailable"))),
    ):
        config_mock.dns = DNSManagerConfig.model_validate({"enabled": True})
        with pytest.raises(PublicOperationError, match="部分网络配置未完成"):
            await dns_manager.update(db_session)


async def test_hot_disable_clears_clients_without_writing_and_can_reenable(db_session):
    manager = SimpleDNSManager()
    enabled = DNSManagerConfig.model_validate({"enabled": True, "dns": {"type": "dnspod"}})
    router = MockMCRouterClient("http://localhost:26666")
    router.close = AsyncMock()
    manager._get_target_records_and_routes = AsyncMock()
    with (
        patch_accessor("app.dns.manager.get_config") as settings,
        patch("app.dns.manager.DNSPodClient", side_effect=lambda *args: MockDNSClient()) as provider,
        patch("app.dns.manager.MCRouterClient", return_value=router),
    ):
        settings.dns = enabled
        await manager.initialize()
        original_client = manager._dns_client
        assert manager.is_initialized
        settings.dns = enabled.model_copy(update={"enabled": False})
        await manager.update(db_session)
        await manager.update(db_session)
        assert not manager.is_initialized
        manager._get_target_records_and_routes.assert_not_called()
        router.close.assert_awaited_once()
        assert provider.call_count == 1
        settings.dns = enabled
        await manager._ensure_up_to_date_config()
        assert manager.is_initialized
        assert manager._dns_client is not original_client


async def test_failed_update_settles_other_branch_before_next_update(db_session):
    manager = SimpleDNSManager()
    manager._dns_client = MockDNSClient()
    manager._mc_router_client = MockMCRouterClient("http://localhost:26666")
    manager._ensure_up_to_date_config = AsyncMock()
    manager._get_target_records_and_routes = AsyncMock(return_value=([AddRecordT(sub_domain="*.mc", value="127.0.0.1", record_type="A", ttl=15)], [RouteEntry("server.mc.example.com", "localhost:25565")], {}, {}))
    manager._dns_client.apply_diff = AsyncMock(side_effect=[RuntimeError("provider failed"), None])
    entered = asyncio.Event()
    finish = asyncio.Event()
    calls = []

    async def update_router(diff):
        calls.append(diff)
        entered.set()
        await finish.wait()

    manager._mc_router_client.apply_diff = update_router
    with patch_accessor("app.dns.manager.get_config") as settings:
        settings.dns = DNSManagerConfig.model_validate({"enabled": True})
        first = asyncio.create_task(manager.update(db_session))
        second = None
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert not first.done()
            second = asyncio.create_task(manager.update(db_session))
            await asyncio.sleep(0)
            assert len(calls) == 1
            finish.set()
            with pytest.raises(PublicOperationError, match="部分网络配置未完成"):
                await first
            await second
            assert len(calls) == 2
        finally:
            finish.set()
            await asyncio.gather(first, *([second] if second is not None else []), return_exceptions=True)


async def test_dns_page_parallel_reads_initialize_clients_once(db_session):
    from app.routers.dns import get_dns_records, get_dns_status, get_router_routes

    manager = SimpleDNSManager()
    provider = MockDNSClient()
    provider._initialized = False
    provider.records = [ReturnRecordT("*.mc", "192.0.2.1", "1", "A", 300)]
    entered = asyncio.Event()
    finish = asyncio.Event()

    async def initialize_provider():
        entered.set()
        await finish.wait()
        provider._initialized = True

    provider.init = AsyncMock(side_effect=initialize_provider)
    router = MockMCRouterClient("http://localhost:26666")
    router.routes = {"server.mc.example.com": "localhost:25565"}
    router.close = AsyncMock()
    settings = Mock(dns=DNSManagerConfig.model_validate({"enabled": True, "dns": {"type": "dnspod"}}))
    with (
        patch_accessor("app.dns.manager.get_config", settings),
        patch_accessor("app.routers.dns.get_config", settings),
        patch_accessor("app.routers.dns.get_dns_manager", manager),
        patch("app.dns.manager.DNSPodClient", return_value=provider) as make_provider,
        patch("app.dns.manager.MCRouterClient", return_value=router) as make_router,
    ):
        queries = [
            asyncio.create_task(get_dns_status(Mock(), db_session)),
            asyncio.create_task(get_dns_records(Mock())),
            asyncio.create_task(get_router_routes(Mock())),
        ]
        try:
            await asyncio.wait_for(entered.wait(), 1)
            await asyncio.sleep(0)
            make_provider.assert_called_once()
            assert all(not query.done() for query in queries)
            finish.set()
            status, records, routes = await asyncio.wait_for(asyncio.gather(*queries), 1)
            assert status.initialized
            assert records[0].model_dump() == provider.records[0]._asdict()
            assert routes == router.routes
            provider.init.assert_awaited_once()
            make_provider.assert_called_once()
            make_router.assert_called_once()
            router.close.assert_not_awaited()
        finally:
            finish.set()
            await asyncio.gather(*queries, return_exceptions=True)


@pytest.mark.parametrize("read_method", ["get_dns_records", "get_router_routes"])
async def test_current_reads_refresh_clients_inside_read_boundary(read_method):
    manager = SimpleDNSManager()
    enabled = DNSManagerConfig.model_validate({"enabled": True, "dns": {"type": "dnspod"}})
    first_provider = MockDNSClient()
    next_provider = MockDNSClient("next.example.com")
    next_provider.records = [ReturnRecordT("*.next", "192.0.2.2", "2", "A", 300)]
    next_provider.list_relevant_records = AsyncMock(return_value=next_provider.records)
    first_router = MockMCRouterClient("http://first:26666")
    close_first_router = AsyncMock()
    first_router.close = close_first_router
    next_router = MockMCRouterClient("http://next:26666")
    next_router.routes = {"server.next.example.com": "localhost:25566"}
    with (
        patch_accessor("app.dns.manager.get_config") as settings,
        patch("app.dns.manager.DNSPodClient", side_effect=[first_provider, next_provider]),
        patch("app.dns.manager.MCRouterClient", side_effect=[first_router, next_router]),
    ):
        settings.dns = enabled
        await manager.initialize()
        settings.dns = enabled.model_copy(update={
            "mc_router_base_url": "http://next:26666",
            "managed_sub_domain": "next",
        })
        result = await getattr(manager, read_method)()
        first_router.close.assert_awaited_once()
        if read_method == "get_dns_records":
            assert result == next_provider.records
            next_provider.list_relevant_records.assert_awaited_once_with("next")
        else:
            assert result == next_router.routes


async def test_explicit_initialize_waits_for_active_router_read():
    manager = SimpleDNSManager()
    first_router = MockMCRouterClient("http://first:26666")
    close_first_router = AsyncMock()
    first_router.close = close_first_router
    next_router = MockMCRouterClient("http://next:26666")
    entered = asyncio.Event()
    finish = asyncio.Event()

    async def read_routes():
        entered.set()
        await finish.wait()
        close_first_router.assert_not_awaited()
        return {"first.example.com": "localhost:25565"}

    first_router.get_routes = AsyncMock(side_effect=read_routes)
    with (
        patch_accessor("app.dns.manager.get_config") as settings,
        patch("app.dns.manager.DNSPodClient", side_effect=lambda *args: MockDNSClient()) as provider,
        patch("app.dns.manager.MCRouterClient", side_effect=[first_router, next_router]),
    ):
        settings.dns = DNSManagerConfig.model_validate({"enabled": True, "dns": {"type": "dnspod"}})
        await manager.initialize()
        read = asyncio.create_task(manager.get_router_routes())
        refresh = None
        try:
            await asyncio.wait_for(entered.wait(), 1)
            settings.dns = settings.dns.model_copy(update={"mc_router_base_url": "http://next:26666"})
            refresh = asyncio.create_task(manager.initialize())
            await asyncio.sleep(0)
            assert not refresh.done()
            provider.assert_called_once()
            close_first_router.assert_not_awaited()
            finish.set()
            assert await read == {"first.example.com": "localhost:25565"}
            await asyncio.wait_for(refresh, 1)
            assert provider.call_count == 2
            first_router.close.assert_awaited_once()
        finally:
            finish.set()
            await asyncio.gather(read, *([refresh] if refresh else []), return_exceptions=True)


def test_get_addresses_from_config():
    manager = SimpleDNSManager()
    result = manager._get_addresses_from_config([
        Manual(name="*", value="192.0.2.1", port=25565),
        Manual(name="backup", value="192.0.2.2", port=25566),
    ])
    assert result == {
        "*": AddressInfo(type="A", host="192.0.2.1", port=25565),
        "backup": AddressInfo(type="A", host="192.0.2.2", port=25566),
    }


@pytest.mark.parametrize("provider_config,factory", [
    (DNSPod(domain="configured.example.com", id="synthetic-id", key="synthetic-key"), "DNSPodClient"),
    (Huawei(domain="configured.example.com", ak="synthetic-id", sk="synthetic-key"), "HuaweiDNSClient"),
])
async def test_typed_provider_configuration_initializes_usable_external_clients(monkeypatch, provider_config, factory):
    configuration = DNSManagerConfig(enabled=True, dns=provider_config, addresses=[])
    provider = StatefulDNS(provider_config.domain)
    provider.initialized = False
    router = StatefulRouter()
    monkeypatch.setattr("app.dns.manager." + factory, lambda *args: provider)
    monkeypatch.setattr("app.dns.manager.MCRouterClient", lambda *args: router)
    manager = SimpleDNSManager(configuration=lambda: configuration)
    try:
        await manager.initialize()
        assert manager.is_initialized
        assert await manager.get_dns_records() == []
        assert await manager.get_router_routes() == {}
    finally:
        await manager.close()
    assert provider.closed and router.closed


async def test_mismatched_compose_preserves_connectivity_until_repaired(connectivity):
    async with connectivity.db() as session:
        await connectivity.manager.update(session)
    connectivity.write_server("survival", 25577, compose_name="legacy-name")
    async with connectivity.db() as session:
        with pytest.raises(PublicOperationError):
            await connectivity.manager.update(session)
        observed = await connectivity.manager.observe(session)
    assert observed.state == "degraded" and observed.unknown_servers == ("survival",)
    assert connectivity.router.routes == {"survival.mc.example.com": "localhost:25565"}
    assert not any("legacy-name" in record.sub_domain for record in connectivity.provider.records)
    connectivity.write_server("survival", 25577)
    async with connectivity.db() as session:
        await connectivity.manager.update(session)
        observed = await connectivity.manager.observe(session)
    assert observed.state == "ready"
    assert connectivity.router.routes == {"survival.mc.example.com": "localhost:25577"}
