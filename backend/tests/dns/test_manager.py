"""
Tests for the simplified DNS manager
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.dns.dns import DNSClient
from app.dns.manager import AddressInfo, SimpleDNSManager
from app.dns.router import MCRouterClient
from app.minecraft import MCServerInfo
from app.minecraft.compose import ServerType


class MockDNSClient(DNSClient):
    """Mock DNS client for testing"""

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
        # For testing, just return all records (can be refined if needed)
        return self.records

    async def update_records(self, target_records, managed_sub_domain=None):
        # Simple mock - just store the target records and managed_sub_domain
        self.last_update_call = target_records
        self.last_managed_sub_domain = managed_sub_domain

    def has_update_capability(self) -> bool:
        return True

    async def remove_records(self, record_ids):
        pass

    async def add_records(self, records):
        pass


class MockMCRouterClient(MCRouterClient):
    """Mock MC Router client for testing"""

    def __init__(self, base_url):
        # Don't call super().__init__ to avoid creating real session
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
    """Test DNS manager initialization with DNSPod provider"""
    mock_config = Mock()
    mock_config.enabled = True
    mock_config.mc_router_base_url = "http://localhost:26666"

    # Create a proper mock for DNS config with model_dump
    mock_dns = Mock()
    mock_dns.type = "dnspod"
    mock_dns.domain = "example.com"
    mock_dns.id = "test_id"
    mock_dns.key = "test_key"
    mock_dns.model_dump.return_value = {
        "type": "dnspod",
        "domain": "example.com",
        "id": "test_id",
        "key": "test_key"
    }
    mock_config.dns = mock_dns

    with (
        patch("app.dns.manager.config") as config_mock,
        patch("app.dns.manager.settings") as settings_mock,
        patch("app.dns.manager.DNSPodClient") as dnspod_mock,
        patch("app.dns.manager.MCRouterClient") as router_mock,
        patch("app.dns.manager.DockerMCManager") as docker_mock,
    ):
        config_mock.dns = mock_config
        settings_mock.server_path = "/path/to/servers"

        # Mock the DNS client
        mock_dns_client = AsyncMock()
        mock_dns_client.is_initialized = Mock(return_value=False)  # Not async
        mock_dns_client.init = AsyncMock()
        dnspod_mock.return_value = mock_dns_client

        await dns_manager.initialize()

        assert dns_manager.is_initialized
        dnspod_mock.assert_called_once_with("example.com", "test_id", "test_key")
        mock_dns_client.init.assert_called_once()


@pytest.mark.asyncio
async def test_initialize_with_huawei(dns_manager):
    """Test DNS manager initialization with Huawei provider"""
    mock_config = Mock()
    mock_config.enabled = True
    mock_config.mc_router_base_url = "http://localhost:26666"

    # Create a proper mock for DNS config with model_dump
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
        "region": "cn-south-1"
    }
    mock_config.dns = mock_dns

    with (
        patch("app.dns.manager.config") as config_mock,
        patch("app.dns.manager.settings") as settings_mock,
        patch("app.dns.manager.HuaweiDNSClient") as huawei_mock,
        patch("app.dns.manager.MCRouterClient") as router_mock,
        patch("app.dns.manager.DockerMCManager") as docker_mock,
    ):
        config_mock.dns = mock_config
        settings_mock.server_path = "/path/to/servers"

        # Mock the DNS client
        mock_dns_client = AsyncMock()
        mock_dns_client.is_initialized = Mock(return_value=True)  # Not async
        mock_dns_client.init = AsyncMock()
        huawei_mock.return_value = mock_dns_client

        await dns_manager.initialize()

        assert dns_manager.is_initialized
        huawei_mock.assert_called_once_with(
            "example.com", "test_ak", "test_sk", "cn-south-1"
        )


@pytest.mark.asyncio
async def test_initialize_disabled():
    """Test DNS manager when disabled in configuration"""
    dns_manager = SimpleDNSManager()

    mock_config = Mock()
    mock_config.enabled = False

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_config

        await dns_manager.initialize()

        assert not dns_manager.is_initialized


def test_generate_dns_records():
    """Test DNS record generation"""
    dns_manager = SimpleDNSManager()

    addresses = {
        "*": AddressInfo(type="A", host="1.2.3.4", port=25565),
        "backup": AddressInfo(type="A", host="5.6.7.8", port=25566),
    }

    server_list = ["vanilla", "modded"]
    managed_sub_domain = "mc"
    dns_ttl = 300

    # Mock DNS client
    dns_manager._dns_client = MockDNSClient("example.com")

    records = dns_manager._generate_dns_records(
        addresses, server_list, managed_sub_domain, dns_ttl
    )

    # Should have 2 wildcard records + 4 SRV records (2 servers × 2 addresses)
    assert len(records) == 6

    # Check wildcard records
    wildcard_records = [r for r in records if r.sub_domain.startswith("*")]
    assert len(wildcard_records) == 2
    assert any(
        r.sub_domain == "*.mc" and r.value == "1.2.3.4" for r in wildcard_records
    )
    assert any(
        r.sub_domain == "*.backup.mc" and r.value == "5.6.7.8" for r in wildcard_records
    )

    # Check SRV records
    srv_records = [r for r in records if r.record_type == "SRV"]
    assert len(srv_records) == 4

    # Verify specific SRV record
    vanilla_main_srv = next(
        r for r in srv_records if "_minecraft._tcp.vanilla.mc" in r.sub_domain
    )
    assert "25565" in vanilla_main_srv.value
    assert "vanilla.mc.example.com" in vanilla_main_srv.value


def test_generate_routes():
    """Test MC Router route generation"""
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

    # Should have 4 routes (2 servers × 2 addresses)
    assert len(routes) == 4

    # Check specific routes
    route_dict = {route.server_address: route.backend for route in routes}

    assert "vanilla.mc.example.com" in route_dict
    assert route_dict["vanilla.mc.example.com"] == "localhost:25565"

    assert "vanilla.backup.mc.example.com" in route_dict
    assert route_dict["vanilla.backup.mc.example.com"] == "localhost:25565"

    assert "modded.mc.example.com" in route_dict
    assert route_dict["modded.mc.example.com"] == "localhost:25566"


@pytest.mark.asyncio
async def test_update_integration():
    """Test the complete update flow"""
    dns_manager = SimpleDNSManager()

    # Setup mocks
    mock_dns_client = MockDNSClient()
    mock_router_client = MockMCRouterClient("http://localhost:26666")
    mock_docker_manager = AsyncMock()

    # Mock server info
    server_info = [
        MCServerInfo(
            name="vanilla",
            path="/servers/vanilla",
            java_version=17,
            max_memory_bytes=2048 * 1024 * 1024,
            server_type=ServerType.VANILLA,
            game_version="1.20.1",
            game_port=25565,
            rcon_port=25575,
        ),
        MCServerInfo(
            name="modded",
            path="/servers/modded",
            java_version=17,
            max_memory_bytes=4096 * 1024 * 1024,
            server_type=ServerType.FORGE,
            game_version="1.20.1",
            game_port=25566,
            rcon_port=25576,
        ),
    ]
    mock_docker_manager.get_all_server_info.return_value = server_info

    dns_manager._dns_client = mock_dns_client
    dns_manager._mc_router_client = mock_router_client
    dns_manager._docker_manager = mock_docker_manager

    # Mock configuration
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

    # Mock the ensure_up_to_date_config method
    dns_manager._ensure_up_to_date_config = AsyncMock()

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_config

        await dns_manager.update()

        # Verify DNS client was called with managed_sub_domain
        assert hasattr(mock_dns_client, "last_update_call")
        assert hasattr(mock_dns_client, "last_managed_sub_domain")
        assert mock_dns_client.last_managed_sub_domain == "mc"

        # Verify router was updated
        assert len(mock_router_client.routes) == 2
        assert "vanilla.mc.example.com" in mock_router_client.routes
        assert "modded.mc.example.com" in mock_router_client.routes


@pytest.mark.asyncio
async def test_update_no_servers():
    """Test update with no servers"""
    dns_manager = SimpleDNSManager()

    mock_dns_client = MockDNSClient()
    mock_router_client = MockMCRouterClient("http://localhost:26666")
    mock_docker_manager = AsyncMock()
    mock_docker_manager.get_all_server_info.return_value = []

    dns_manager._dns_client = mock_dns_client
    dns_manager._mc_router_client = mock_router_client
    dns_manager._docker_manager = mock_docker_manager

    # Mock the ensure_up_to_date_config method
    dns_manager._ensure_up_to_date_config = AsyncMock()

    mock_config = Mock()
    mock_config.addresses = []

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_config

        # Should not raise exception and should return early
        await dns_manager.update()


@pytest.mark.asyncio
async def test_update_not_initialized():
    """Test update when manager is not initialized"""
    dns_manager = SimpleDNSManager()

    # Mock the ensure_up_to_date_config to not throw the ConfigManager error
    dns_manager._ensure_up_to_date_config = AsyncMock()

    with pytest.raises(RuntimeError, match="DNS manager not initialized"):
        await dns_manager.update()


def test_get_addresses_from_config():
    """Test address extraction from configuration"""
    dns_manager = SimpleDNSManager()

    # Create mock address configs with explicit attribute setting
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

    result = asyncio.run(dns_manager._get_addresses_from_config(addresses_config))

    # Should have 2 addresses (natmap is skipped)
    assert len(result) == 2
    assert "*" in result
    assert "backup" in result
    assert result["*"].host == "1.2.3.4"
    assert result["*"].port == 25565
    assert result["backup"].host == "5.6.7.8"
    assert result["backup"].port == 25566


@pytest.mark.asyncio
async def test_config_hash_calculation():
    """Test configuration hash calculation for key fields"""
    dns_manager = SimpleDNSManager()

    # Create mock DNS config
    mock_dns_config = Mock()
    mock_dns_config.enabled = True
    mock_dns_config.mc_router_base_url = "http://localhost:26666"

    # Mock DNS provider config
    mock_dns_provider = Mock()
    mock_dns_provider.model_dump.return_value = {
        "type": "dnspod",
        "domain": "example.com",
        "id": "test_id",
        "key": "test_key"
    }
    mock_dns_config.dns = mock_dns_provider

    # Calculate hash
    hash1 = dns_manager._calculate_config_hash(mock_dns_config)
    assert isinstance(hash1, str)
    assert len(hash1) == 32  # MD5 hash length

    # Calculate hash again with same config - should be identical
    hash2 = dns_manager._calculate_config_hash(mock_dns_config)
    assert hash1 == hash2

    # Change a key field and verify hash changes
    mock_dns_config.mc_router_base_url = "http://localhost:26667"
    hash3 = dns_manager._calculate_config_hash(mock_dns_config)
    assert hash1 != hash3


@pytest.mark.asyncio
async def test_config_hash_with_none_dns():
    """Test configuration hash calculation when DNS config is None"""
    dns_manager = SimpleDNSManager()

    mock_dns_config = Mock()
    mock_dns_config.enabled = False
    mock_dns_config.mc_router_base_url = "http://localhost:26666"
    mock_dns_config.dns = None

    # Should not raise exception
    hash_result = dns_manager._calculate_config_hash(mock_dns_config)
    assert isinstance(hash_result, str)
    assert len(hash_result) == 32


@pytest.mark.asyncio
async def test_ensure_up_to_date_config_no_change():
    """Test ensure_up_to_date_config when configuration hasn't changed"""
    dns_manager = SimpleDNSManager()

    # Mock config
    mock_dns_config = Mock()
    mock_dns_config.enabled = True
    mock_dns_config.mc_router_base_url = "http://localhost:26666"
    mock_dns_provider = Mock()
    mock_dns_provider.model_dump.return_value = {"type": "dnspod", "domain": "example.com"}
    mock_dns_config.dns = mock_dns_provider

    # Set initial hash
    initial_hash = dns_manager._calculate_config_hash(mock_dns_config)
    dns_manager._last_config_hash = initial_hash

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_dns_config

        # Mock initialize method to track if it's called
        dns_manager.initialize = AsyncMock()

        await dns_manager._ensure_up_to_date_config()

        # Initialize should not be called since config hasn't changed
        dns_manager.initialize.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_up_to_date_config_with_change():
    """Test ensure_up_to_date_config when configuration has changed"""
    dns_manager = SimpleDNSManager()

    # Mock config
    mock_dns_config = Mock()
    mock_dns_config.enabled = True
    mock_dns_config.mc_router_base_url = "http://localhost:26666"
    mock_dns_provider = Mock()
    mock_dns_provider.model_dump.return_value = {"type": "dnspod", "domain": "example.com"}
    mock_dns_config.dns = mock_dns_provider

    # Set initial hash with different config
    dns_manager._last_config_hash = "different_hash"

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_dns_config

        # Mock initialize method
        dns_manager.initialize = AsyncMock()

        await dns_manager._ensure_up_to_date_config()

        # Initialize should be called since config changed
        dns_manager.initialize.assert_called_once()

        # Hash should be updated
        expected_hash = dns_manager._calculate_config_hash(mock_dns_config)
        assert dns_manager._last_config_hash == expected_hash


@pytest.mark.asyncio
async def test_ensure_up_to_date_config_first_time():
    """Test ensure_up_to_date_config when no hash is set (first time)"""
    dns_manager = SimpleDNSManager()

    # Mock config
    mock_dns_config = Mock()
    mock_dns_config.enabled = True
    mock_dns_config.mc_router_base_url = "http://localhost:26666"
    mock_dns_provider = Mock()
    mock_dns_provider.model_dump.return_value = {"type": "dnspod", "domain": "example.com"}
    mock_dns_config.dns = mock_dns_provider

    # No initial hash set (None)
    assert dns_manager._last_config_hash is None

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_dns_config

        # Mock initialize method
        dns_manager.initialize = AsyncMock()

        await dns_manager._ensure_up_to_date_config()

        # Initialize should be called since no hash was set
        dns_manager.initialize.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_up_to_date_config_initialization_failure():
    """Test ensure_up_to_date_config when reinitialization fails"""
    dns_manager = SimpleDNSManager()

    # Mock config
    mock_dns_config = Mock()
    mock_dns_config.enabled = True
    mock_dns_config.mc_router_base_url = "http://localhost:26666"
    mock_dns_provider = Mock()
    mock_dns_provider.model_dump.return_value = {"type": "dnspod", "domain": "example.com"}
    mock_dns_config.dns = mock_dns_provider

    # Set different hash to trigger reinitialization
    dns_manager._last_config_hash = "different_hash"

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_dns_config

        # Mock initialize method to raise exception
        dns_manager.initialize = AsyncMock(side_effect=Exception("Init failed"))

        with pytest.raises(Exception, match="Init failed"):
            await dns_manager._ensure_up_to_date_config()


@pytest.mark.asyncio
async def test_update_with_automatic_reinitialization():
    """Test update method with automatic configuration change detection"""
    dns_manager = SimpleDNSManager()

    # Set up the manager to be "initialized"
    mock_dns_client = MockDNSClient()
    mock_router_client = MockMCRouterClient("http://localhost:26666")
    mock_docker_manager = AsyncMock()
    mock_docker_manager.get_all_server_info.return_value = []

    dns_manager._dns_client = mock_dns_client
    dns_manager._mc_router_client = mock_router_client
    dns_manager._docker_manager = mock_docker_manager

    # Mock configuration
    mock_config = Mock()
    mock_config.addresses = []

    # Mock the ensure_up_to_date_config method
    dns_manager._ensure_up_to_date_config = AsyncMock()

    with patch("app.dns.manager.config") as config_mock:
        config_mock.dns = mock_config

        await dns_manager.update()

        # Verify that ensure_up_to_date_config was called before the actual update
        dns_manager._ensure_up_to_date_config.assert_called_once()
