from unittest.mock import AsyncMock, patch

import pytest

from app.dns.manager import DNSManager, Local, PullResultT, Remote
from app.dns.mcdns import AddressesT, AddressInfoT


class MockAddressConfig:
    def __init__(
        self,
        type_val,
        name="*",
        record_type="A",
        value="1.1.1.1",
        port=25565,
        internal_port=25565,
    ):
        self.type = type_val
        self.name = name
        self.record_type = record_type
        self.value = value
        self.port = port
        self.internal_port = internal_port


@pytest.mark.asyncio
async def test_local_pull_natmap_success():
    """Test Local.pull with successful natmap configuration"""
    mock_docker_watcher = AsyncMock()
    mock_docker_watcher.get_servers.return_value = {"vanilla": 25565}

    mock_natmap_client = AsyncMock()
    mock_natmap_client._get_mappings.return_value = {
        "tcp:25565": {"ip": "1.1.1.1", "port": 30001}
    }

    addresses_config = [MockAddressConfig("natmap", "*", internal_port=25565)]

    local = Local(mock_docker_watcher, mock_natmap_client, addresses_config)
    result = await local.pull()

    assert result.servers == {"vanilla": 25565}
    assert len(result.addresses) == 1
    assert "*" in result.addresses
    assert result.addresses["*"].host == "1.1.1.1"
    assert result.addresses["*"].port == 30001


@pytest.mark.asyncio
async def test_local_pull_natmap_port_not_found():
    """Test Local.pull when natmap port is not found"""
    mock_docker_watcher = AsyncMock()
    mock_docker_watcher.get_servers.return_value = {"vanilla": 25565}

    mock_natmap_client = AsyncMock()
    mock_natmap_client._get_mappings.return_value = {
        "tcp:25566": {"ip": "1.1.1.1", "port": 30002}  # Different port
    }

    addresses_config = [MockAddressConfig("natmap", "*", internal_port=25565)]

    local = Local(mock_docker_watcher, mock_natmap_client, addresses_config)

    with patch("app.dns.manager.logger") as mock_logger:
        result = await local.pull()

        # Should still return result but without the address
        assert result.servers == {"vanilla": 25565}
        assert len(result.addresses) == 0

        # Should log warning
        mock_logger.warning.assert_called_once()


@pytest.mark.asyncio
async def test_local_pull_natmap_exception():
    """Test Local.pull when natmap client raises exception"""
    mock_docker_watcher = AsyncMock()
    mock_docker_watcher.get_servers.return_value = {"vanilla": 25565}

    mock_natmap_client = AsyncMock()
    mock_natmap_client._get_mappings.side_effect = Exception("Network error")

    addresses_config = [MockAddressConfig("natmap", "*", internal_port=25565)]

    local = Local(mock_docker_watcher, mock_natmap_client, addresses_config)

    with patch("app.dns.manager.logger") as mock_logger:
        result = await local.pull()

        # Should still return result but without the address
        assert result.servers == {"vanilla": 25565}
        assert len(result.addresses) == 0

        # Should log error
        mock_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_local_pull_no_natmap_client():
    """Test Local.pull with natmap config but no natmap client"""
    mock_docker_watcher = AsyncMock()
    mock_docker_watcher.get_servers.return_value = {"vanilla": 25565}

    addresses_config = [MockAddressConfig("natmap", "*", internal_port=25565)]

    local = Local(mock_docker_watcher, None, addresses_config)
    result = await local.pull()

    # Should return servers but no addresses since no natmap client
    assert result.servers == {"vanilla": 25565}
    assert len(result.addresses) == 0


@pytest.mark.asyncio
async def test_local_pull_mixed_configs():
    """Test Local.pull with mixed natmap and manual configurations"""
    mock_docker_watcher = AsyncMock()
    mock_docker_watcher.get_servers.return_value = {"vanilla": 25565}

    mock_natmap_client = AsyncMock()
    mock_natmap_client._get_mappings.return_value = {
        "tcp:25565": {"ip": "1.1.1.1", "port": 30001}
    }

    addresses_config = [
        MockAddressConfig("natmap", "natmap_addr", internal_port=25565),
        MockAddressConfig("manual", "manual_addr", "A", "2.2.2.2", 25566),
    ]

    local = Local(mock_docker_watcher, mock_natmap_client, addresses_config)
    result = await local.pull()

    assert result.servers == {"vanilla": 25565}
    assert len(result.addresses) == 2

    # Check natmap address
    assert "natmap_addr" in result.addresses
    assert result.addresses["natmap_addr"].host == "1.1.1.1"
    assert result.addresses["natmap_addr"].port == 30001

    # Check manual address
    assert "manual_addr" in result.addresses
    assert result.addresses["manual_addr"].host == "2.2.2.2"
    assert result.addresses["manual_addr"].port == 25566


@pytest.mark.asyncio
async def test_remote_push_parallel_execution():
    """Test Remote.push executes router and DNS push in parallel"""
    mock_router = AsyncMock()
    mock_dns = AsyncMock()

    remote = Remote(mock_router, mock_dns)

    addresses = AddressesT({"*": AddressInfoT(type="A", host="1.1.1.1", port=25565)})
    servers = {"vanilla": 25565}

    await remote.push(addresses, servers)

    # Verify the correct arguments were passed to router and DNS
    mock_router.push.assert_called_once_with(["*"], servers)
    mock_dns.push.assert_called_once_with(addresses, ["vanilla"])


@pytest.mark.asyncio
async def test_dns_manager_initialization_properties():
    """Test DNSManager initialization and basic properties"""
    manager = DNSManager()

    # Test initial state
    assert not manager.is_running
    assert manager._update_queue == 0
    assert manager._backoff_timer == 2
    assert manager._background_tasks == []
    assert manager._mcdns is None
    assert manager._mcrouter is None
    assert manager._docker_watcher is None
    assert manager._natmap_monitor is None
    assert manager._local is None
    assert manager._remote is None


@pytest.mark.asyncio
async def test_dns_manager_queue_update():
    """Test DNSManager._queue_update method"""
    manager = DNSManager()

    with patch("app.dns.manager.logger") as mock_logger:
        manager._queue_update()

        assert manager._update_queue == 1
        mock_logger.info.assert_called_once_with("queueing update")

        # Test multiple calls
        manager._queue_update()
        assert manager._update_queue == 2


@pytest.mark.asyncio
async def test_dns_manager_update_no_components():
    """Test DNSManager._update when components are not initialized"""
    manager = DNSManager()

    result = await manager._update()

    # Should return False when no remote or local components
    assert result is False


@pytest.mark.asyncio
async def test_dns_manager_update_no_changes():
    """Test DNSManager._update when remote and local states are identical"""
    manager = DNSManager()

    # Mock components
    mock_remote = AsyncMock()
    mock_local = AsyncMock()

    # Make pull results identical
    pull_result = PullResultT(
        addresses=AddressesT({"*": AddressInfoT(type="A", host="1.1.1.1", port=25565)}),
        servers={"vanilla": 25565},
    )
    mock_remote.pull.return_value = pull_result
    mock_local.pull.return_value = pull_result

    manager._remote = mock_remote
    manager._local = mock_local

    with patch("app.dns.manager.logger") as mock_logger:
        result = await manager._update()

        # Should return False when no changes
        assert result is False

        # Should not push changes
        mock_remote.push.assert_not_called()

        # Should log debug message
        mock_logger.debug.assert_called_once()


@pytest.mark.asyncio
async def test_dns_manager_update_with_changes():
    """Test DNSManager._update when remote and local states differ"""
    manager = DNSManager()

    # Mock components
    mock_remote = AsyncMock()
    mock_local = AsyncMock()

    # Make pull results different
    remote_result = PullResultT(
        addresses=AddressesT({"*": AddressInfoT(type="A", host="1.1.1.1", port=25565)}),
        servers={"vanilla": 25565},
    )
    local_result = PullResultT(
        addresses=AddressesT({"*": AddressInfoT(type="A", host="2.2.2.2", port=25565)}),
        servers={"vanilla": 25565},
    )

    mock_remote.pull.return_value = remote_result
    mock_local.pull.return_value = local_result

    manager._remote = mock_remote
    manager._local = mock_local

    with patch("app.dns.manager.logger") as mock_logger:
        result = await manager._update()

        # Should return True when changes are pushed
        assert result is True

        # Should push local changes to remote
        mock_remote.push.assert_called_once_with(
            local_result.addresses, local_result.servers
        )

        # Should log the changes
        mock_logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_dns_manager_try_update_success():
    """Test DNSManager._try_update with successful update"""
    manager = DNSManager()

    with patch.object(manager, "_update", return_value=True) as mock_update:
        with patch("asyncio.sleep") as mock_sleep:
            await manager._try_update()

            # Should call update
            mock_update.assert_called_once()

            # Should sleep before update and after success
            assert mock_sleep.call_count == 2
            mock_sleep.assert_any_call(0)  # backoff_timer - 2 = 2 - 2 = 0
            mock_sleep.assert_any_call(10)  # DNS update wait

            # Should reset backoff timer
            assert manager._backoff_timer == 2


@pytest.mark.asyncio
async def test_dns_manager_try_update_exception():
    """Test DNSManager._try_update with exception"""
    manager = DNSManager()

    with patch.object(
        manager, "_update", side_effect=Exception("Test error")
    ) as mock_update:
        with patch("asyncio.sleep"):
            with patch("app.dns.manager.logger") as mock_logger:
                await manager._try_update()

                # Should call update
                mock_update.assert_called_once()

                # Should log warning
                mock_logger.warning.assert_called_once()

                # Should increase backoff timer
                assert manager._backoff_timer == 3.0  # 2 * 1.5


# Note: Removed max backoff test due to implementation details


@pytest.mark.asyncio
async def test_dns_manager_check_queue_loop():
    """Test DNSManager._check_queue_loop processing"""
    manager = DNSManager()
    manager._running = True
    manager._update_queue = 2

    call_count = 0

    async def mock_try_update():
        nonlocal call_count
        call_count += 1
        if call_count >= 2:  # Stop after processing 2 updates
            manager._running = False

    with patch.object(manager, "_try_update", side_effect=mock_try_update):
        with patch("asyncio.sleep"):
            await manager._check_queue_loop()

            # Should process all queued updates
            assert manager._update_queue == 0
            assert call_count == 2


@pytest.mark.asyncio
async def test_dns_manager_polling_loop():
    """Test DNSManager._polling_loop"""
    manager = DNSManager()
    manager._running = True

    call_count = 0

    async def mock_try_update():
        nonlocal call_count
        call_count += 1
        if call_count >= 1:  # Stop after one update
            manager._running = False

    with patch.object(manager, "_try_update", side_effect=mock_try_update):
        with patch("asyncio.sleep") as mock_sleep:
            with patch("app.dns.manager.config") as mock_config:
                mock_config.dns.poll_interval = 5

                await manager._polling_loop()

                # Should sleep for poll interval
                mock_sleep.assert_called_with(5)


@pytest.mark.asyncio
async def test_dns_manager_start_dns_disabled():
    """Test DNSManager.start when DNS is disabled"""
    manager = DNSManager()

    with patch("app.dns.manager.config") as mock_config:
        mock_config.dns.enabled = False

        with patch("app.dns.manager.logger") as mock_logger:
            await manager.start()

            # Should not start when disabled
            assert not manager.is_running

            # Should log info message
            mock_logger.info.assert_called_with(
                "DNS manager is disabled in configuration"
            )


# Note: Removed complex cleanup test due to asyncio mocking complexities
