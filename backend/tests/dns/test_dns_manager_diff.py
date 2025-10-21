"""
Tests for DNS manager diff functionality
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.dns.manager import SimpleDNSManager
from app.dns.types import AddRecordT
from app.dns.utils import RecordDiff


class TestDNSManagerDiff:
    """Test DNS manager diff functionality"""

    @pytest.fixture
    def dns_manager(self):
        """Create a DNS manager instance"""
        return SimpleDNSManager()

    @pytest.fixture
    def mock_dns_client(self):
        """Mock DNS client"""
        client = MagicMock()
        client.get_domain.return_value = "example.com"
        client.get_records_diff = AsyncMock()
        return client

    @pytest.fixture
    def mock_mc_router_client(self):
        """Mock MC Router client"""
        client = MagicMock()
        client.get_routes = AsyncMock()
        client.get_routes_diff = AsyncMock()
        return client

    @pytest.fixture
    def mock_docker_manager(self):
        """Mock Docker manager"""
        manager = MagicMock()
        manager.get_all_server_info = AsyncMock()
        return manager

    @pytest.fixture
    def mock_config(self):
        """Mock DNS configuration"""
        # Create proper mock with dictionary-like behavior
        address_mock = MagicMock()
        address_mock.type = "manual"
        address_mock.name = "*"
        address_mock.record_type = "A"
        address_mock.value = "192.168.1.100"
        address_mock.port = 25565

        dns_config_mock = MagicMock()
        dns_config_mock.enabled = True
        dns_config_mock.managed_sub_domain = "mc"
        dns_config_mock.dns_ttl = 300
        dns_config_mock.addresses = [address_mock]
        dns_config_mock.mc_router_base_url = "http://127.0.0.1:26666"

        # Create a serializable version for model_dump
        dns_dns_mock = MagicMock()
        dns_dns_mock.type = "dnspod"
        dns_dns_mock.domain = "example.com"
        dns_dns_mock.id = "test_id"
        dns_dns_mock.key = "test_key"
        dns_dns_mock.model_dump.return_value = {
            "type": "dnspod",
            "domain": "example.com",
            "id": "test_id",
            "key": "test_key",
        }
        dns_config_mock.dns = dns_dns_mock
        dns_config_mock.model_dump.return_value = {
            "enabled": True,
            "managed_sub_domain": "mc",
            "dns_ttl": 300,
            "dns": {
                "type": "dnspod",
                "domain": "example.com",
                "id": "test_id",
                "key": "test_key",
            },
            "mc_router_base_url": "http://127.0.0.1:26666",
        }

        config = MagicMock()
        config.dns = dns_config_mock
        return config

    @pytest.mark.asyncio
    async def test_get_current_diff_manager_not_initialized(
        self, dns_manager, mock_config
    ):
        """Test get_current_diff when manager is not initialized"""
        # Don't initialize the manager
        with patch("app.dns.manager.config", mock_config):
            with patch.object(
                dns_manager, "_ensure_up_to_date_config", new_callable=AsyncMock
            ):
                # Should raise RuntimeError instead of returning error dict
                with pytest.raises(RuntimeError, match="DNS manager not initialized"):
                    await dns_manager.get_current_diff()

    @pytest.mark.asyncio
    async def test_get_current_diff_no_servers_or_addresses(
        self,
        dns_manager,
        mock_dns_client,
        mock_mc_router_client,
        mock_docker_manager,
        mock_config,
    ):
        """Test get_current_diff when no servers or addresses are found"""
        # Set up manager with mocked clients
        dns_manager._dns_client = mock_dns_client
        dns_manager._mc_router_client = mock_mc_router_client
        dns_manager._docker_manager = mock_docker_manager

        # Mock no servers
        mock_docker_manager.get_all_server_info.return_value = []

        with patch("app.dns.manager.config", mock_config):
            with patch.object(
                dns_manager, "_ensure_up_to_date_config", new_callable=AsyncMock
            ):
                # Should raise ValueError instead of returning error dict
                with pytest.raises(
                    ValueError,
                    match="No addresses or servers found for diff calculation",
                ):
                    await dns_manager.get_current_diff()

    @pytest.mark.asyncio
    async def test_get_current_diff_successful_calculation(
        self,
        dns_manager,
        mock_dns_client,
        mock_mc_router_client,
        mock_docker_manager,
        mock_config,
    ):
        """Test successful diff calculation"""
        # Set up manager with mocked clients
        dns_manager._dns_client = mock_dns_client
        dns_manager._mc_router_client = mock_mc_router_client
        dns_manager._docker_manager = mock_docker_manager

        # Mock server info
        mock_server_info = MagicMock()
        mock_server_info.name = "testserver"
        mock_server_info.game_port = 25565
        mock_docker_manager.get_all_server_info.return_value = [mock_server_info]

        # Mock DNS diff result
        mock_dns_diff = RecordDiff(
            records_to_add=[
                AddRecordT(
                    sub_domain="*.mc", value="192.168.1.100", record_type="A", ttl=300
                )
            ],
            records_to_remove=[],
            records_to_update=[],
        )
        mock_dns_client.get_records_diff.return_value = mock_dns_diff

        # Mock router diff result
        mock_router_diff = {
            "routes_to_add": {},
            "routes_to_remove": {},
            "routes_to_update": {},
        }
        mock_mc_router_client.get_routes_diff.return_value = mock_router_diff

        with patch("app.dns.manager.config", mock_config):
            with patch.object(
                dns_manager, "_ensure_up_to_date_config", new_callable=AsyncMock
            ):
                dns_diff, router_diff = await dns_manager.get_current_diff()

        assert dns_diff == mock_dns_diff
        assert router_diff == mock_router_diff

        # Verify DNS client was called correctly
        mock_dns_client.get_records_diff.assert_called_once()
        call_args = mock_dns_client.get_records_diff.call_args
        # Check that the method was called with correct parameters (positional or keyword)
        if len(call_args[0]) >= 2:
            # Called with positional arguments
            assert call_args[0][1] == "mc"
        else:
            # Called with keyword arguments
            assert call_args[1]["managed_sub_domain"] == "mc"

        # Verify router client was called correctly
        mock_mc_router_client.get_routes_diff.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_current_diff_with_router_differences(
        self,
        dns_manager,
        mock_dns_client,
        mock_mc_router_client,
        mock_docker_manager,
        mock_config,
    ):
        """Test diff calculation with router differences"""
        # Set up manager with mocked clients
        dns_manager._dns_client = mock_dns_client
        dns_manager._mc_router_client = mock_mc_router_client
        dns_manager._docker_manager = mock_docker_manager

        # Mock server info
        mock_server_info1 = MagicMock()
        mock_server_info1.name = "server1"
        mock_server_info1.game_port = 25565

        mock_server_info2 = MagicMock()
        mock_server_info2.name = "server2"
        mock_server_info2.game_port = 25566

        mock_docker_manager.get_all_server_info.return_value = [
            mock_server_info1,
            mock_server_info2,
        ]

        # Mock empty DNS diff
        mock_dns_diff = RecordDiff(
            records_to_add=[], records_to_remove=[], records_to_update=[]
        )
        mock_dns_client.get_records_diff.return_value = mock_dns_diff

        # Mock router diff result with differences
        mock_router_diff = {
            "routes_to_add": {},
            "routes_to_remove": {"oldserver.mc.example.com": "localhost:25567"},
            "routes_to_update": {
                "server2.mc.example.com": {
                    "current": "localhost:99999",
                    "target": "localhost:25566",
                }
            },
        }
        mock_mc_router_client.get_routes_diff.return_value = mock_router_diff

        with patch("app.dns.manager.config", mock_config):
            with patch.object(
                dns_manager, "_ensure_up_to_date_config", new_callable=AsyncMock
            ):
                dns_diff, router_diff = await dns_manager.get_current_diff()

        assert dns_diff == mock_dns_diff
        assert router_diff == mock_router_diff

        # No routes should be added
        assert len(router_diff["routes_to_add"]) == 0

        # oldserver should be removed
        assert len(router_diff["routes_to_remove"]) == 1
        assert "oldserver.mc.example.com" in router_diff["routes_to_remove"]

        # server2 should be updated (port mismatch)
        assert len(router_diff["routes_to_update"]) == 1
        assert "server2.mc.example.com" in router_diff["routes_to_update"]
        update_info = router_diff["routes_to_update"]["server2.mc.example.com"]
        assert update_info["current"] == "localhost:99999"
        assert update_info["target"] == "localhost:25566"

    @pytest.mark.asyncio
    async def test_get_current_diff_dns_error_handling(
        self,
        dns_manager,
        mock_dns_client,
        mock_mc_router_client,
        mock_docker_manager,
        mock_config,
    ):
        """Test error handling during DNS diff calculation - should raise exception"""
        # Set up manager with mocked clients
        dns_manager._dns_client = mock_dns_client
        dns_manager._mc_router_client = mock_mc_router_client
        dns_manager._docker_manager = mock_docker_manager

        # Mock server info
        mock_server_info = MagicMock()
        mock_server_info.name = "testserver"
        mock_server_info.game_port = 25565
        mock_docker_manager.get_all_server_info.return_value = [mock_server_info]

        # Mock DNS diff to raise an exception
        mock_dns_client.get_records_diff.side_effect = Exception(
            "DNS connection failed"
        )

        with patch("app.dns.manager.config", mock_config):
            with patch.object(
                dns_manager, "_ensure_up_to_date_config", new_callable=AsyncMock
            ):
                # Should raise exception immediately, not collect errors
                with pytest.raises(Exception, match="DNS connection failed"):
                    await dns_manager.get_current_diff()

    @pytest.mark.asyncio
    async def test_get_current_diff_router_error_handling(
        self,
        dns_manager,
        mock_dns_client,
        mock_mc_router_client,
        mock_docker_manager,
        mock_config,
    ):
        """Test error handling during router diff calculation - should raise exception"""
        # Set up manager with mocked clients
        dns_manager._dns_client = mock_dns_client
        dns_manager._mc_router_client = mock_mc_router_client
        dns_manager._docker_manager = mock_docker_manager

        # Mock server info
        mock_server_info = MagicMock()
        mock_server_info.name = "testserver"
        mock_server_info.game_port = 25565
        mock_docker_manager.get_all_server_info.return_value = [mock_server_info]

        # Mock successful DNS operation
        mock_dns_diff = RecordDiff(
            records_to_add=[], records_to_remove=[], records_to_update=[]
        )
        mock_dns_client.get_records_diff.return_value = mock_dns_diff

        # Mock router to raise an exception
        mock_mc_router_client.get_routes_diff.side_effect = Exception(
            "Router connection failed"
        )

        with patch("app.dns.manager.config", mock_config):
            with patch.object(
                dns_manager, "_ensure_up_to_date_config", new_callable=AsyncMock
            ):
                # Should raise exception immediately, not collect errors
                with pytest.raises(Exception, match="Router connection failed"):
                    await dns_manager.get_current_diff()

    @pytest.mark.asyncio
    async def test_get_current_diff_general_error_handling(
        self,
        dns_manager,
        mock_dns_client,
        mock_mc_router_client,
        mock_docker_manager,
        mock_config,
    ):
        """Test general error handling during diff calculation - should raise exception"""
        # Set up manager with mocked clients
        dns_manager._dns_client = mock_dns_client
        dns_manager._mc_router_client = mock_mc_router_client
        dns_manager._docker_manager = mock_docker_manager

        # Mock server info to raise an exception
        mock_docker_manager.get_all_server_info.side_effect = Exception(
            "Docker connection failed"
        )

        with patch("app.dns.manager.config", mock_config):
            with patch.object(
                dns_manager, "_ensure_up_to_date_config", new_callable=AsyncMock
            ):
                # Should raise exception immediately, not collect errors
                with pytest.raises(Exception, match="Docker connection failed"):
                    await dns_manager.get_current_diff()
