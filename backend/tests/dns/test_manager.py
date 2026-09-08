"""SimpleDNSManager tests."""

import asyncio
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.dns.dns import DNSClient
from app.dns.manager import AddressInfo, SimpleDNSManager
from app.dns.router import MCRouterClient
from app.dns.types import ReturnRecordT
from app.dynamic_config.configs.dns import DNSManagerConfig
from app.minecraft import MCServerInfo
from app.minecraft.compose import ServerType


@contextmanager
def _patch_active_servers(mock_docker_manager, servers_data):
    """Wire up DB-driven server enumeration for a DNS manager test.

    servers_data: iterable of (server_id, MCServerInfo). Each entry produces a
    Server row in app.servers.crud.get_active_servers and a matching MCInstance
    whose get_server_info() returns the provided info.
    """
    instances_by_sid: dict[str, MagicMock] = {}
    rows = []
    for sid, info in servers_data:
        inst = MagicMock()
        inst.get_server_info = AsyncMock(return_value=info)
        instances_by_sid[sid] = inst
        row = MagicMock()
        row.server_id = sid
        rows.append(row)

    mock_docker_manager.get_instance = MagicMock(
        side_effect=lambda s: instances_by_sid[s]
    )
    with patch(
        "app.servers.crud.get_active_servers", AsyncMock(return_value=rows)
    ):
        yield


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
        return self.records

    async def update_records(self, target_records, managed_sub_domain=None):
        self.last_update_call = target_records
        self.last_managed_sub_domain = managed_sub_domain

    def has_update_capability(self) -> bool:
        return True

    async def remove_records(self, record_ids):
        pass

    async def add_records(self, records):
        pass


class MockMCRouterClient(MCRouterClient):
    def __init__(self, base_url):
        # Bypass super().__init__ to avoid creating a real HTTP client session.
        self.base_url = base_url
        self.routes = {}

    async def get_routes(self):
        return self.routes

    async def override_routes(self, routes):
        self.routes = routes

    async def close(self):
        pass


@pytest.fixture
def mock_dns_client():
    return MockDNSClient()


@pytest.fixture
def mock_router_client():
    return MockMCRouterClient("http://localhost:26666")


@pytest.fixture
def dns_manager():
    return SimpleDNSManager()


@pytest.mark.asyncio
async def test_initialize_with_dnspod(dns_manager):
    mock_config = Mock()
    mock_config.enabled = True
    mock_config.mc_router_base_url = "http://localhost:26666"

    mock_dns = Mock()
    mock_dns.type = "dnspod"
    mock_dns.domain = "example.com"
    mock_dns.id = "test_id"
    mock_dns.key = "test_key"
    mock_dns.model_dump.return_value = {
        "type": "dnspod",
        "domain": "example.com",
        "id": "test_id",
        "key": "test_key",
    }
    mock_config.dns = mock_dns

    with (
        patch("app.dns.manager.config") as config_mock,
        patch("app.dns.manager.docker_mc_manager") as mc_manager_mock,
        patch("app.dns.manager.DNSPodClient") as dnspod_mock,
    ):
        config_mock.dns = mock_config
        mc_manager_mock.servers_path = "/path/to/servers"

        mock_dns_client = AsyncMock()
        mock_dns_client.is_initialized = Mock(return_value=False)
        mock_dns_client.init = AsyncMock()
        dnspod_mock.return_value = mock_dns_client

        await dns_manager.initialize()

        assert dns_manager.is_initialized
        dnspod_mock.assert_called_once_with("example.com", "test_id", "test_key")
        mock_dns_client.init.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_with_huawei(dns_manager):
    mock_config = Mock()
    mock_config.enabled = True
    mock_config.mc_router_base_url = "http://localhost:26666"

    mock_dns = Mock()
    mock_dns.type = "huawei"
    mock_dns.domain = "example.com"
    mock_dns.ak = "test_ak"
    mock_dns.sk = "test_sk"
    mock_dns.region = "cn-south-1"
    mock_dns.model_dump.return_value = {
        "type": "huawei",
        "domain": "example.com",
        "ak": "test_ak",
        "sk": "test_sk",
        "region": "cn-south-1",
    }
    mock_config.dns = mock_dns

    with (
        patch("app.dns.manager.config") as config_mock,
        patch("app.dns.manager.docker_mc_manager") as mc_manager_mock,
        patch("app.dns.manager.HuaweiDNSClient") as huawei_mock,
    ):
        config_mock.dns = mock_config
        mc_manager_mock.servers_path = "/path/to/servers"

        mock_dns_client = AsyncMock()
        mock_dns_client.is_initialized = Mock(return_value=True)
        mock_dns_client.init = AsyncMock()
        huawei_mock.return_value = mock_dns_client

        await dns_manager.initialize()

        assert dns_manager.is_initialized
        huawei_mock.assert_called_once_with(
            "example.com", "test_ak", "test_sk", "cn-south-1"
        )


@pytest.mark.asyncio
async def test_initialize_disabled():
    dns_manager = SimpleDNSManager()

    mock_config = DNSManagerConfig.model_validate({"enabled": False})

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_config

        await dns_manager.initialize()

        assert not dns_manager.is_initialized


def test_generate_dns_records():
    dns_manager = SimpleDNSManager()

    addresses = {
        "*": AddressInfo(type="A", host="1.2.3.4", port=25565),
        "backup": AddressInfo(type="A", host="5.6.7.8", port=25566),
    }

    server_list = ["vanilla", "modded"]
    managed_sub_domain = "mc"
    dns_ttl = 300

    dns_manager._dns_client = MockDNSClient("example.com")

    records = dns_manager._generate_dns_records(
        addresses, server_list, managed_sub_domain, dns_ttl
    )

    # 2 wildcard + 4 SRV records (2 servers × 2 addresses).
    assert len(records) == 6

    wildcard_records = [r for r in records if r.sub_domain.startswith("*")]
    assert len(wildcard_records) == 2
    assert any(
        r.sub_domain == "*.mc" and r.value == "1.2.3.4" for r in wildcard_records
    )
    assert any(
        r.sub_domain == "*.backup.mc" and r.value == "5.6.7.8" for r in wildcard_records
    )

    srv_records = [r for r in records if r.record_type == "SRV"]
    assert len(srv_records) == 4

    vanilla_main_srv = next(
        r for r in srv_records if "_minecraft._tcp.vanilla.mc" in r.sub_domain
    )
    assert "25565" in vanilla_main_srv.value
    assert "vanilla.mc.example.com" in vanilla_main_srv.value


def test_generate_routes():
    dns_manager = SimpleDNSManager()

    addresses = {
        "*": AddressInfo(type="A", host="1.2.3.4", port=25565),
        "backup": AddressInfo(type="A", host="5.6.7.8", port=25566),
    }

    servers = {"vanilla": 25565, "modded": 25566}
    managed_sub_domain = "mc"
    domain = "example.com"

    routes = dns_manager._generate_routes(
        addresses, servers, managed_sub_domain, domain
    )

    assert len(routes) == 4

    route_dict = {route.server_address: route.backend for route in routes}

    assert "vanilla.mc.example.com" in route_dict
    assert route_dict["vanilla.mc.example.com"] == "localhost:25565"

    assert "vanilla.backup.mc.example.com" in route_dict
    assert route_dict["vanilla.backup.mc.example.com"] == "localhost:25565"

    assert "modded.mc.example.com" in route_dict
    assert route_dict["modded.mc.example.com"] == "localhost:25566"


@pytest.mark.asyncio
async def test_update_integration():
    dns_manager = SimpleDNSManager()

    mock_dns_client = MockDNSClient()
    mock_router_client = MockMCRouterClient("http://localhost:26666")
    mock_docker_manager = MagicMock()

    vanilla_info = MCServerInfo(
        name="vanilla",
        path="/servers/vanilla",
        java_version=17,
        max_memory_bytes=2048 * 1024 * 1024,
        server_type=ServerType.VANILLA,
        game_version="1.20.1",
        game_port=25565,
        rcon_port=25575,
    )
    modded_info = MCServerInfo(
        name="modded",
        path="/servers/modded",
        java_version=17,
        max_memory_bytes=4096 * 1024 * 1024,
        server_type=ServerType.FORGE,
        game_version="1.20.1",
        game_port=25566,
        rcon_port=25576,
    )

    dns_manager._dns_client = mock_dns_client
    dns_manager._mc_router_client = mock_router_client
    dns_manager._docker_manager = mock_docker_manager

    mock_address = Mock()
    mock_address.type = "manual"
    mock_address.name = "*"
    mock_address.record_type = "A"
    mock_address.value = "1.2.3.4"
    mock_address.port = 25565

    mock_config = Mock()
    mock_config.addresses = [mock_address]
    mock_config.managed_sub_domain = "mc"
    mock_config.dns_ttl = 300

    dns_manager._ensure_up_to_date_config = AsyncMock()

    with (
        patch("app.dns.manager.config") as config_mock,
        _patch_active_servers(
            mock_docker_manager,
            [("vanilla", vanilla_info), ("modded", modded_info)],
        ),
    ):
        config_mock.dns = mock_config

        await dns_manager.update(AsyncMock())

        assert hasattr(mock_dns_client, "last_update_call")
        assert hasattr(mock_dns_client, "last_managed_sub_domain")
        assert mock_dns_client.last_managed_sub_domain == "mc"

        assert len(mock_router_client.routes) == 2
        assert "vanilla.mc.example.com" in mock_router_client.routes
        assert "modded.mc.example.com" in mock_router_client.routes


@pytest.mark.asyncio
async def test_update_no_servers():
    dns_manager = SimpleDNSManager()

    mock_dns_client = MockDNSClient()
    mock_router_client = MockMCRouterClient("http://localhost:26666")
    mock_docker_manager = MagicMock()

    dns_manager._dns_client = mock_dns_client
    dns_manager._mc_router_client = mock_router_client
    dns_manager._docker_manager = mock_docker_manager

    dns_manager._ensure_up_to_date_config = AsyncMock()

    mock_config = Mock()
    mock_config.addresses = []

    with (
        patch("app.dns.manager.config") as config_mock,
        _patch_active_servers(mock_docker_manager, []),
    ):
        config_mock.dns = mock_config

        await dns_manager.update(AsyncMock())


@pytest.mark.asyncio
async def test_update_not_initialized():
    dns_manager = SimpleDNSManager()

    dns_manager._ensure_up_to_date_config = AsyncMock()

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = DNSManagerConfig.model_validate({"enabled": True})
        with pytest.raises(RuntimeError, match="DNS manager not initialized"):
            await dns_manager.update(AsyncMock())


async def test_hot_disable_clears_clients_without_writing_and_can_reenable():
    manager = SimpleDNSManager()
    enabled = DNSManagerConfig.model_validate({"enabled": True, "dns": {"type": "dnspod"}})
    router = MockMCRouterClient("http://localhost:26666")
    router.close = AsyncMock()
    manager._get_target_records_and_routes = AsyncMock()
    with (
        patch("app.dns.manager.config") as settings,
        patch("app.dns.manager.DNSPodClient", side_effect=lambda *args: MockDNSClient()) as provider,
        patch("app.dns.manager.MCRouterClient", return_value=router),
    ):
        settings.dns = enabled
        await manager.initialize()
        original_client = manager._dns_client
        assert manager.is_initialized
        settings.dns = enabled.model_copy(update={"enabled": False})
        await manager.update(AsyncMock())
        await manager.update(AsyncMock())
        assert not manager.is_initialized
        manager._get_target_records_and_routes.assert_not_called()
        router.close.assert_awaited_once()
        assert provider.call_count == 1
        settings.dns = enabled
        await manager._ensure_up_to_date_config()
        assert manager.is_initialized
        assert manager._dns_client is not original_client


async def test_failed_update_settles_other_branch_before_next_update():
    manager = SimpleDNSManager()
    manager._dns_client = MockDNSClient()
    manager._mc_router_client = MockMCRouterClient("http://localhost:26666")
    manager._ensure_up_to_date_config = AsyncMock()
    manager._get_target_records_and_routes = AsyncMock(return_value=([], [], {}, {}))
    manager._update_dns_records = AsyncMock(side_effect=[RuntimeError("provider failed"), None])
    entered = asyncio.Event()
    finish = asyncio.Event()
    calls = []

    async def update_router(target_routes):
        calls.append(target_routes)
        entered.set()
        await finish.wait()

    manager._update_mc_router = update_router
    with patch("app.dns.manager.config") as settings:
        settings.dns = DNSManagerConfig.model_validate({"enabled": True})
        first = asyncio.create_task(manager.update(AsyncMock()))
        second = None
        try:
            await asyncio.wait_for(entered.wait(), 1)
            assert not first.done()
            second = asyncio.create_task(manager.update(AsyncMock()))
            await asyncio.sleep(0)
            assert len(calls) == 1
            finish.set()
            with pytest.raises(RuntimeError, match="provider failed"):
                await first
            await second
            assert len(calls) == 2
        finally:
            finish.set()
            await asyncio.gather(first, *([second] if second is not None else []), return_exceptions=True)


async def test_dns_page_parallel_reads_initialize_clients_once():
    from app.routers.dns import get_dns_records, get_dns_status, get_router_routes

    manager = SimpleDNSManager()
    manager._get_target_records_and_routes = AsyncMock(return_value=([], [], {}, {}))
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
        patch("app.dns.manager.config", settings),
        patch("app.routers.dns.config", settings),
        patch("app.routers.dns.simple_dns_manager", manager),
        patch("app.dns.manager.DNSPodClient", return_value=provider) as make_provider,
        patch("app.dns.manager.MCRouterClient", return_value=router) as make_router,
    ):
        queries = [
            asyncio.create_task(get_dns_status(Mock(), AsyncMock())),
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
        patch("app.dns.manager.config") as settings,
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
        patch("app.dns.manager.config") as settings,
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
    dns_manager = SimpleDNSManager()

    mock_address1 = Mock()
    mock_address1.type = "manual"
    mock_address1.name = "*"
    mock_address1.record_type = "A"
    mock_address1.value = "1.2.3.4"
    mock_address1.port = 25565

    mock_address2 = Mock()
    mock_address2.type = "manual"
    mock_address2.name = "backup"
    mock_address2.record_type = "A"
    mock_address2.value = "5.6.7.8"
    mock_address2.port = 25566

    mock_address3 = Mock()
    mock_address3.type = "natmap"
    mock_address3.name = "natmap1"
    mock_address3.internal_port = 25567

    addresses_config = [mock_address1, mock_address2, mock_address3]

    result = dns_manager._get_addresses_from_config(addresses_config)

    # natmap entries are skipped.
    assert len(result) == 2
    assert "*" in result
    assert "backup" in result
    assert result["*"].host == "1.2.3.4"
    assert result["*"].port == 25565
    assert result["backup"].host == "5.6.7.8"
    assert result["backup"].port == 25566


@pytest.mark.asyncio
async def test_config_hash_calculation():
    dns_manager = SimpleDNSManager()

    mock_dns_config = Mock()
    mock_dns_config.enabled = True
    mock_dns_config.mc_router_base_url = "http://localhost:26666"

    mock_dns_provider = Mock()
    mock_dns_provider.model_dump.return_value = {
        "type": "dnspod",
        "domain": "example.com",
        "id": "test_id",
        "key": "test_key",
    }
    mock_dns_config.dns = mock_dns_provider

    hash1 = dns_manager._calculate_config_hash(mock_dns_config)
    assert isinstance(hash1, str)
    assert len(hash1) == 32  # MD5 hash length

    hash2 = dns_manager._calculate_config_hash(mock_dns_config)
    assert hash1 == hash2

    mock_dns_config.mc_router_base_url = "http://localhost:26667"
    hash3 = dns_manager._calculate_config_hash(mock_dns_config)
    assert hash1 != hash3


@pytest.mark.asyncio
async def test_config_hash_with_none_dns():
    dns_manager = SimpleDNSManager()

    mock_dns_config = Mock()
    mock_dns_config.enabled = False
    mock_dns_config.mc_router_base_url = "http://localhost:26666"
    mock_dns_config.dns = None

    hash_result = dns_manager._calculate_config_hash(mock_dns_config)
    assert isinstance(hash_result, str)
    assert len(hash_result) == 32


@pytest.mark.asyncio
async def test_ensure_up_to_date_config_no_change():
    dns_manager = SimpleDNSManager()

    mock_dns_config = Mock()
    mock_dns_config.enabled = True
    mock_dns_config.mc_router_base_url = "http://localhost:26666"
    mock_dns_provider = Mock()
    mock_dns_provider.model_dump.return_value = {
        "type": "dnspod",
        "domain": "example.com",
    }
    mock_dns_config.dns = mock_dns_provider

    initial_hash = dns_manager._calculate_config_hash(mock_dns_config)
    dns_manager._last_config_hash = initial_hash

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_dns_config

        dns_manager._initialize = AsyncMock()

        await dns_manager._ensure_up_to_date_config()

        dns_manager._initialize.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_up_to_date_config_with_change():
    dns_manager = SimpleDNSManager()

    mock_dns_config = Mock()
    mock_dns_config.enabled = True
    mock_dns_config.mc_router_base_url = "http://localhost:26666"
    mock_dns_provider = Mock()
    mock_dns_provider.model_dump.return_value = {
        "type": "dnspod",
        "domain": "example.com",
    }
    mock_dns_config.dns = mock_dns_provider

    dns_manager._last_config_hash = "different_hash"

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_dns_config

        dns_manager._initialize = AsyncMock()

        await dns_manager._ensure_up_to_date_config()

        dns_manager._initialize.assert_called_once()

        expected_hash = dns_manager._calculate_config_hash(mock_dns_config)
        assert dns_manager._last_config_hash == expected_hash


@pytest.mark.asyncio
async def test_ensure_up_to_date_config_first_time():
    dns_manager = SimpleDNSManager()

    mock_dns_config = Mock()
    mock_dns_config.enabled = True
    mock_dns_config.mc_router_base_url = "http://localhost:26666"
    mock_dns_provider = Mock()
    mock_dns_provider.model_dump.return_value = {
        "type": "dnspod",
        "domain": "example.com",
    }
    mock_dns_config.dns = mock_dns_provider

    assert dns_manager._last_config_hash is None

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_dns_config

        dns_manager._initialize = AsyncMock()

        await dns_manager._ensure_up_to_date_config()

        dns_manager._initialize.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_up_to_date_config_initialization_failure():
    dns_manager = SimpleDNSManager()

    mock_dns_config = Mock()
    mock_dns_config.enabled = True
    mock_dns_config.mc_router_base_url = "http://localhost:26666"
    mock_dns_provider = Mock()
    mock_dns_provider.model_dump.return_value = {
        "type": "dnspod",
        "domain": "example.com",
    }
    mock_dns_config.dns = mock_dns_provider

    dns_manager._last_config_hash = "different_hash"

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_dns_config

        dns_manager._initialize = AsyncMock(side_effect=Exception("Init failed"))

        with pytest.raises(Exception, match="Init failed"):
            await dns_manager._ensure_up_to_date_config()


@pytest.mark.asyncio
async def test_update_with_automatic_reinitialization():
    dns_manager = SimpleDNSManager()

    mock_dns_client = MockDNSClient()
    mock_router_client = MockMCRouterClient("http://localhost:26666")
    mock_docker_manager = MagicMock()

    dns_manager._dns_client = mock_dns_client
    dns_manager._mc_router_client = mock_router_client
    dns_manager._docker_manager = mock_docker_manager

    mock_config = Mock()
    mock_config.addresses = []

    dns_manager._ensure_up_to_date_config = AsyncMock()

    with (
        patch("app.dns.manager.config") as config_mock,
        _patch_active_servers(mock_docker_manager, []),
    ):
        config_mock.dns = mock_config

        await dns_manager.update(AsyncMock())

        dns_manager._ensure_up_to_date_config.assert_called_once()


@pytest.mark.asyncio
async def test_dns_keyed_by_server_id_not_compose_name():
    """REGRESSION: DNS records and routes must use `row.server_id` as the
    canonical key, not the compose project name.

    A server adopted by sync can legitimately have a compose `container_name`
    that doesn't match its directory name (the server_id). Routes must follow
    the DB identifier so the rest of the system can address them.
    """
    dns_manager = SimpleDNSManager()
    mock_dns_client = MockDNSClient()
    mock_router_client = MockMCRouterClient("http://localhost:26666")
    mock_docker_manager = MagicMock()

    drifted_info = MCServerInfo(
        name="legacy-name",  # compose project name, diverged from server_id
        path="/servers/survival",
        java_version=17,
        max_memory_bytes=2048 * 1024 * 1024,
        server_type=ServerType.VANILLA,
        game_version="1.20.1",
        game_port=25577,
        rcon_port=25587,
    )

    dns_manager._dns_client = mock_dns_client
    dns_manager._mc_router_client = mock_router_client
    dns_manager._docker_manager = mock_docker_manager

    mock_address = Mock()
    mock_address.type = "manual"
    mock_address.name = "*"
    mock_address.record_type = "A"
    mock_address.value = "1.2.3.4"
    mock_address.port = 25565
    mock_config = Mock()
    mock_config.addresses = [mock_address]
    mock_config.managed_sub_domain = "mc"
    mock_config.dns_ttl = 300

    dns_manager._ensure_up_to_date_config = AsyncMock()

    with (
        patch("app.dns.manager.config") as config_mock,
        _patch_active_servers(
            mock_docker_manager, [("survival", drifted_info)]
        ),
    ):
        config_mock.dns = mock_config
        await dns_manager.update(AsyncMock())

    # Route should use the server_id ("survival"), NOT the compose name ("legacy-name")
    assert "survival.mc.example.com" in mock_router_client.routes
    assert mock_router_client.routes["survival.mc.example.com"] == "localhost:25577"
    assert "legacy-name.mc.example.com" not in mock_router_client.routes


@pytest.mark.asyncio
async def test_update_skips_row_with_unreadable_compose(caplog):
    """A single ACTIVE row whose compose read fails must not poison the tick.

    The row is dropped with a warning; the surviving row still produces routes.
    """
    import logging

    dns_manager = SimpleDNSManager()
    mock_dns_client = MockDNSClient()
    mock_router_client = MockMCRouterClient("http://localhost:26666")
    mock_docker_manager = MagicMock()

    good_info = MCServerInfo(
        name="good",
        path="/servers/good",
        java_version=17,
        max_memory_bytes=2048 * 1024 * 1024,
        server_type=ServerType.VANILLA,
        game_version="1.20.1",
        game_port=25565,
        rcon_port=25575,
    )

    # Build instances by hand: one good, one whose get_server_info raises.
    good_instance = MagicMock()
    good_instance.get_server_info = AsyncMock(return_value=good_info)
    bad_instance = MagicMock()
    bad_instance.get_server_info = AsyncMock(
        side_effect=FileNotFoundError("compose.yml missing")
    )
    instances = {"good": good_instance, "drifted": bad_instance}
    mock_docker_manager.get_instance = MagicMock(side_effect=lambda s: instances[s])

    good_row = MagicMock()
    good_row.server_id = "good"
    bad_row = MagicMock()
    bad_row.server_id = "drifted"

    dns_manager._dns_client = mock_dns_client
    dns_manager._mc_router_client = mock_router_client
    dns_manager._docker_manager = mock_docker_manager

    mock_address = Mock()
    mock_address.type = "manual"
    mock_address.name = "*"
    mock_address.record_type = "A"
    mock_address.value = "1.2.3.4"
    mock_address.port = 25565
    mock_config = Mock()
    mock_config.addresses = [mock_address]
    mock_config.managed_sub_domain = "mc"
    mock_config.dns_ttl = 300

    dns_manager._ensure_up_to_date_config = AsyncMock()

    with (
        patch("app.dns.manager.config") as config_mock,
        patch(
            "app.servers.crud.get_active_servers",
            AsyncMock(return_value=[good_row, bad_row]),
        ),
        caplog.at_level(logging.WARNING),
    ):
        config_mock.dns = mock_config
        await dns_manager.update(AsyncMock())

    # The good row produced a route; the drifted one did not.
    assert "good.mc.example.com" in mock_router_client.routes
    assert "drifted.mc.example.com" not in mock_router_client.routes

    # And a warning identifying the skipped server_id was logged.
    assert any(
        "drifted" in record.message and "cannot read compose" in record.message
        for record in caplog.records
    )
