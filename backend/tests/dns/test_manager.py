"""SimpleDNSManager tests."""

from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from app.dns.dns import DNSClient
from app.dns.manager import AddressInfo, SimpleDNSManager
from app.dns.router import MCRouterClient
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
        # Bypass super().__init__ to avoid creating a real httpx session.
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

    mock_config = Mock()
    mock_config.enabled = False

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

    with pytest.raises(RuntimeError, match="DNS manager not initialized"):
        await dns_manager.update(AsyncMock())


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

        dns_manager.initialize = AsyncMock()

        await dns_manager._ensure_up_to_date_config()

        dns_manager.initialize.assert_not_called()


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

        dns_manager.initialize = AsyncMock()

        await dns_manager._ensure_up_to_date_config()

        dns_manager.initialize.assert_called_once()

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

        dns_manager.initialize = AsyncMock()

        await dns_manager._ensure_up_to_date_config()

        dns_manager.initialize.assert_called_once()


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

        dns_manager.initialize = AsyncMock(side_effect=Exception("Init failed"))

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
