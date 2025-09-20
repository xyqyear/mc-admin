from unittest.mock import AsyncMock, patch

import pytest

from app.dns.manager import DNSManager, Local, Remote
from app.dns.mcdns import MCDNS, AddressesT, AddressInfoT
from app.dns.monitor import DockerWatcher
from app.dns.router import MCRouter


@pytest.mark.asyncio
async def test_local_pull_basic():
    """Test Local.pull with basic configuration"""
    # Mock docker watcher
    mock_docker_watcher = AsyncMock(spec=DockerWatcher)
    mock_docker_watcher.get_servers.return_value = {"vanilla": 25565, "creative": 25566}

    # Test with manual address configuration
    # Create mock objects with attributes
    class MockAddressConfig:
        def __init__(
            self, type_val, name="*", record_type="A", value="1.1.1.1", port=25565
        ):
            self.type = type_val
            self.name = name
            self.record_type = record_type
            self.value = value
            self.port = port

    addresses_config = [MockAddressConfig("manual", "*", "A", "1.1.1.1", 25565)]

    local = Local(mock_docker_watcher, None, addresses_config)
    result = await local.pull()

    # Check servers
    assert result.servers == {"vanilla": 25565, "creative": 25566}

    # Check addresses
    assert len(result.addresses) == 1
    assert "*" in result.addresses
    assert result.addresses["*"].type == "A"
    assert result.addresses["*"].host == "1.1.1.1"
    assert result.addresses["*"].port == 25565


@pytest.mark.asyncio
async def test_remote_push():
    """Test Remote.push functionality"""
    # Mock components
    mock_router = AsyncMock(spec=MCRouter)
    mock_dns = AsyncMock(spec=MCDNS)

    remote = Remote(mock_router, mock_dns)

    addresses = AddressesT({"*": AddressInfoT(type="A", host="1.1.1.1", port=25565)})
    servers = {"vanilla": 25565}

    await remote.push(addresses, servers)

    # Verify both router and DNS were called
    mock_router.push.assert_called_once_with(["*"], servers)
    mock_dns.push.assert_called_once_with(addresses, ["vanilla"])


@pytest.mark.asyncio
async def test_remote_pull_consistent():
    """Test Remote.pull with consistent router/DNS state"""
    # Mock components
    mock_router = AsyncMock(spec=MCRouter)
    mock_dns = AsyncMock(spec=MCDNS)

    # Set up consistent return values
    addresses = AddressesT({"*": AddressInfoT(type="A", host="1.1.1.1", port=25565)})
    servers = {"vanilla": 25565}
    server_list = ["vanilla"]

    mock_router.pull.return_value = (["*"], servers)
    mock_dns.pull.return_value = (addresses, server_list)

    remote = Remote(mock_router, mock_dns)
    result = await remote.pull()

    assert result is not None
    assert result.addresses == addresses
    assert result.servers == servers


@pytest.mark.asyncio
async def test_remote_pull_inconsistent():
    """Test Remote.pull with inconsistent router/DNS state"""
    # Mock components
    mock_router = AsyncMock(spec=MCRouter)
    mock_dns = AsyncMock(spec=MCDNS)

    # Set up inconsistent return values
    addresses = AddressesT({"*": AddressInfoT(type="A", host="1.1.1.1", port=25565)})
    servers = {"vanilla": 25565}

    # Router has different address names than DNS
    mock_router.pull.return_value = (["backup"], servers)
    mock_dns.pull.return_value = (addresses, ["vanilla"])

    remote = Remote(mock_router, mock_dns)
    result = await remote.pull()

    # Should return None due to inconsistency
    assert result is None


@pytest.mark.asyncio
async def test_dns_manager_disabled():
    """Test DNSManager when DNS is disabled in config"""
    with patch("app.dns.manager.config") as mock_config:
        mock_config.dns.enabled = False

        manager = DNSManager()
        await manager.start()

        # Should not initialize components when disabled
        assert manager._mcdns is None
        assert manager._mcrouter is None
        assert not manager.is_running


@pytest.mark.asyncio
async def test_dns_manager_lifecycle():
    """Test DNSManager basic initialization and properties"""
    manager = DNSManager()

    # Test initial state
    assert not manager.is_running
    assert manager._mcdns is None
    assert manager._mcrouter is None

    # Test basic properties
    assert manager._update_queue == 0
    assert manager._backoff_timer == 2

    # Test _queue_update method
    manager._queue_update()
    assert manager._update_queue == 1

    # Test stop when not running (should handle gracefully)
    await manager.stop()
    assert not manager.is_running


@pytest.mark.asyncio
async def test_dns_manager_start_already_running():
    """Test starting DNS manager when already running"""
    manager = DNSManager()
    manager._running = True

    # Should not start again
    await manager.start()

    # Should still be in the same state
    assert manager._running is True


@pytest.mark.asyncio
async def test_dns_manager_stop_not_running():
    """Test stopping DNS manager when not running"""
    manager = DNSManager()

    # Should handle gracefully
    await manager.stop()

    assert not manager.is_running
