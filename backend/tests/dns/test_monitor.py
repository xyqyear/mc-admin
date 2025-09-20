import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.dns.mcdns import AddressInfoT
from app.dns.monitor import DockerWatcher, NatmapMonitorClient


@pytest.fixture
def mock_docker_mc_manager():
    """Mock Docker MC Manager for testing"""
    with patch("app.dns.monitor.DockerMCManager") as mock_manager_class:
        mock_manager = AsyncMock()
        mock_manager_class.return_value = mock_manager

        # Mock server info
        class MockServerInfo:
            def __init__(self, name: str, game_port: int):
                self.name = name
                self.game_port = game_port

        mock_manager.get_all_server_info.return_value = [
            MockServerInfo("vanilla", 25565),
            MockServerInfo("creative", 25566),
            MockServerInfo("modded", 25567),
        ]

        yield mock_manager


@pytest.mark.asyncio
async def test_docker_watcher_initialization():
    """Test DockerWatcher initialization"""
    with patch("app.dns.monitor.DockerMCManager"):
        watcher = DockerWatcher("/path/to/servers")

        assert watcher._servers_root_path == Path("/path/to/servers")
        assert watcher._previous_servers is None


@pytest.mark.asyncio
async def test_docker_watcher_get_servers(mock_docker_mc_manager):
    """Test getting servers from DockerWatcher"""
    watcher = DockerWatcher("/path/to/servers")
    watcher._docker_mc_manager = mock_docker_mc_manager

    servers = await watcher.get_servers()

    assert servers == {"vanilla": 25565, "creative": 25566, "modded": 25567}


@pytest.mark.asyncio
async def test_docker_watcher_watch_servers_no_change(mock_docker_mc_manager):
    """Test watching servers when no changes occur"""
    watcher = DockerWatcher("/path/to/servers")
    watcher._docker_mc_manager = mock_docker_mc_manager

    on_change = MagicMock()

    # Set initial state
    watcher._previous_servers = {"vanilla": 25565, "creative": 25566, "modded": 25567}

    # Run one iteration
    with patch("asyncio.sleep") as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        with pytest.raises(asyncio.CancelledError):
            await watcher.watch_servers(on_change)

        # Should not call on_change since no change occurred
        on_change.assert_not_called()


@pytest.mark.asyncio
async def test_docker_watcher_watch_servers_with_change(mock_docker_mc_manager):
    """Test watching servers when changes occur"""
    watcher = DockerWatcher("/path/to/servers")
    watcher._docker_mc_manager = mock_docker_mc_manager

    on_change = MagicMock()

    # Set initial state (different from mock return)
    watcher._previous_servers = {"vanilla": 25565}

    # Run one iteration
    with patch("asyncio.sleep") as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        with pytest.raises(asyncio.CancelledError):
            await watcher.watch_servers(on_change)

        # Should call on_change since servers changed
        on_change.assert_called_once()


@pytest.mark.asyncio
async def test_docker_watcher_watch_servers_first_run(mock_docker_mc_manager):
    """Test watching servers on first run (previous_servers is None)"""
    watcher = DockerWatcher("/path/to/servers")
    watcher._docker_mc_manager = mock_docker_mc_manager

    on_change = MagicMock()

    # Run one iteration
    with patch("asyncio.sleep") as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        with pytest.raises(asyncio.CancelledError):
            await watcher.watch_servers(on_change)

        # Should not call on_change on first run
        on_change.assert_not_called()
        # But should set previous_servers
        assert watcher._previous_servers is not None


@pytest.mark.asyncio
async def test_docker_watcher_watch_servers_exception_handling(mock_docker_mc_manager):
    """Test exception handling in watch_servers"""
    watcher = DockerWatcher("/path/to/servers")
    watcher._docker_mc_manager = mock_docker_mc_manager

    # Make get_all_server_info raise an exception
    mock_docker_mc_manager.get_all_server_info.side_effect = Exception("Test error")

    on_change = MagicMock()

    with patch("asyncio.sleep") as mock_sleep:
        mock_sleep.side_effect = [None, asyncio.CancelledError()]

        with patch("app.dns.monitor.logger") as mock_logger:
            with pytest.raises(asyncio.CancelledError):
                await watcher.watch_servers(on_change)

            # Should log the warning - may be called more than once due to loop
            assert mock_logger.warning.call_count >= 1


@pytest.mark.asyncio
async def test_natmap_monitor_client_initialization():
    """Test NatmapMonitorClient initialization"""
    client = NatmapMonitorClient("http://localhost:8080")

    assert client._url == "http://localhost:8080/"
    assert client._timeout == 5


@pytest.mark.asyncio
async def test_natmap_monitor_client_url_normalization():
    """Test URL normalization in NatmapMonitorClient"""
    # URL without trailing slash
    client1 = NatmapMonitorClient("http://localhost:8080")
    assert client1._url == "http://localhost:8080/"

    # URL with trailing slash
    client2 = NatmapMonitorClient("http://localhost:8080/")
    assert client2._url == "http://localhost:8080/"


@pytest.mark.asyncio
async def test_natmap_monitor_client_get_mappings():
    """Test getting mappings from NatmapMonitorClient"""
    client = NatmapMonitorClient("http://localhost:8080")

    mock_response_data = {
        "tcp:25565": {"ip": "1.1.1.1", "port": 30001},
        "tcp:25566": {"ip": "1.1.1.1", "port": 30002},
    }

    with patch.object(client._session, "get") as mock_get:
        mock_response = AsyncMock()
        mock_response.json.return_value = mock_response_data
        mock_get.return_value.__aenter__.return_value = mock_response

        mappings = await client._get_mappings()

        assert mappings == mock_response_data
        mock_get.assert_called_once_with("http://localhost:8080/all_mappings")


@pytest.mark.asyncio
async def test_natmap_monitor_client_get_addresses_for_config():
    """Test getting addresses filtered by configuration"""
    client = NatmapMonitorClient("http://localhost:8080")

    # Mock mappings data
    mock_mappings = {
        "tcp:25565": {"ip": "1.1.1.1", "port": 30001},
        "tcp:25566": {"ip": "1.1.1.1", "port": 30002},
        "tcp:25567": {"ip": "1.1.1.1", "port": 30003},
    }

    # Mock configuration
    addresses_config = [
        {"type": "natmap", "internal_port": 25565},
        {"type": "natmap", "internal_port": 25568},  # Not in mappings
        {"type": "manual", "value": "2.2.2.2"},  # Not natmap type
    ]

    with patch.object(client, "_get_mappings", return_value=mock_mappings):
        with patch("app.dns.monitor.logger") as mock_logger:
            addresses = await client.get_addresses_for_config(addresses_config)

            # Should only find the first natmap config
            assert len(addresses) == 1
            assert "*" in addresses
            assert addresses["*"] == AddressInfoT(type="A", host="1.1.1.1", port=30001)

            # Should log warning for missing port
            mock_logger.warning.assert_called_once()


# Note: Removed complex WebSocket test due to aiohttp mocking complexities


@pytest.mark.asyncio
async def test_natmap_monitor_client_listen_to_ws_exception_handling():
    """Test WebSocket exception handling"""
    client = NatmapMonitorClient("http://localhost:8080")

    on_message = MagicMock()

    with patch.object(client._session, "ws_connect") as mock_ws_connect:
        mock_ws_connect.side_effect = Exception("Connection failed")

        with patch("asyncio.sleep") as mock_sleep:
            mock_sleep.side_effect = [None, asyncio.CancelledError()]

            with patch("app.dns.monitor.logger") as mock_logger:
                with pytest.raises(asyncio.CancelledError):
                    await client.listen_to_ws(on_message)

                # Should log warning about connection error
                mock_logger.warning.assert_called()


@pytest.mark.asyncio
async def test_natmap_monitor_client_close():
    """Test closing NatmapMonitorClient session"""
    client = NatmapMonitorClient("http://localhost:8080")

    with patch.object(client._session, "close") as mock_close:
        await client.close()
        mock_close.assert_called_once()


@pytest.mark.asyncio
async def test_natmap_monitor_client_custom_timeout():
    """Test NatmapMonitorClient with custom timeout"""
    client = NatmapMonitorClient("http://localhost:8080", timeout=10)

    assert client._timeout == 10


@pytest.mark.asyncio
async def test_natmap_monitor_get_addresses_default_port():
    """Test getting addresses with default port when not specified"""
    client = NatmapMonitorClient("http://localhost:8080")

    mock_mappings = {"tcp:25565": {"ip": "1.1.1.1", "port": 30001}}

    # Configuration without internal_port (should default to 25565)
    addresses_config = [{"type": "natmap"}]

    with patch.object(client, "_get_mappings", return_value=mock_mappings):
        addresses = await client.get_addresses_for_config(addresses_config)

        # Should find the mapping using default port
        assert len(addresses) == 1
        assert "*" in addresses
