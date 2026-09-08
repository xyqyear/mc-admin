"""
Tests for the DNS API router
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.dns.types import ReturnRecordT
from app.main import app
from app.models import UserPublic, UserRole


@pytest.fixture
def client():
    """Create test client"""
    # Mock settings to set up master token
    with patch("app.dependencies.settings") as mock_settings:
        mock_settings.master_token = "test_master_token"
        yield TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def mock_admin_user():
    """Mock admin user"""
    user = Mock(spec=UserPublic)
    user.id = 1
    user.username = "admin"
    user.role = UserRole.ADMIN
    return user


@pytest.mark.asyncio
async def test_update_dns_endpoint_success(client, mock_admin_user):
    """Test successful DNS update"""
    from app.routers.dns import update_dns

    with (
        patch("app.routers.dns.simple_dns_manager") as dns_manager_mock,
        patch("app.routers.dns.config") as mock_config,
    ):
        # Mock DNS config as enabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = True
        mock_config.dns = mock_dns_config

        # Mock DNS manager
        dns_manager_mock.is_initialized = True
        dns_manager_mock.update = AsyncMock()

        # Call the endpoint function directly, bypassing auth
        result = await update_dns(mock_admin_user)

        assert result.success is True
        assert "successfully" in result.message
        dns_manager_mock.update.assert_called_once()


@pytest.mark.asyncio
async def test_update_dns_endpoint_not_initialized(client, mock_admin_user):
    """Test DNS update when manager is not initialized"""
    from app.routers.dns import update_dns

    with (
        patch("app.routers.dns.simple_dns_manager") as dns_manager_mock,
        patch("app.routers.dns.config") as mock_config,
    ):
        # Mock DNS config as enabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = True
        mock_config.dns = mock_dns_config

        # Mock DNS manager - not initialized
        dns_manager_mock.is_initialized = False
        dns_manager_mock.initialize = AsyncMock()
        dns_manager_mock.update = AsyncMock()

        result = await update_dns(mock_admin_user)

        assert result.success is True

        dns_manager_mock.initialize.assert_not_called()
        dns_manager_mock.update.assert_called_once()


@pytest.mark.asyncio
async def test_update_dns_endpoint_initialization_fails(client, mock_admin_user):
    """Initialization failures from the manager propagate through the route."""

    from app.routers.dns import update_dns

    with (
        patch("app.routers.dns.simple_dns_manager") as dns_manager_mock,
        patch("app.routers.dns.config") as mock_config,
    ):
        # Mock DNS config as enabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = True
        mock_config.dns = mock_dns_config

        # Mock DNS manager - initialization fails
        dns_manager_mock.is_initialized = False
        dns_manager_mock.update = AsyncMock(side_effect=RuntimeError("Init failed"))

        with pytest.raises(RuntimeError, match="Init failed"):
            await update_dns(mock_admin_user)
        dns_manager_mock.update.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_dns_endpoint_update_fails(client, mock_admin_user):
    """Test DNS update when update operation fails - raises Exception"""
    from app.routers.dns import update_dns

    with (
        patch("app.routers.dns.simple_dns_manager") as dns_manager_mock,
        patch("app.routers.dns.config") as mock_config,
    ):
        # Mock DNS config as enabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = True
        mock_config.dns = mock_dns_config

        # Mock DNS manager - update fails
        dns_manager_mock.is_initialized = True
        dns_manager_mock.update = AsyncMock(side_effect=Exception("Update failed"))

        # Update failure is not wrapped in HTTPException, so original exception is raised
        with pytest.raises(Exception, match="Update failed"):
            await update_dns(mock_admin_user)


@pytest.mark.asyncio
async def test_get_dns_status_success(client, mock_admin_user):
    """Test getting DNS status"""
    from app.dns.utils import RecordDiff
    from app.routers.dns import get_dns_status

    with (
        patch("app.routers.dns.simple_dns_manager") as dns_manager_mock,
        patch("app.routers.dns.config") as mock_config,
    ):
        # Mock DNS config as enabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = True
        mock_config.dns = mock_dns_config

        # Mock DNS manager
        dns_manager_mock.is_initialized = True

        # Mock get_current_diff to return tuple (dns_diff, router_diff)
        mock_dns_diff = RecordDiff(
            records_to_add=[], records_to_remove=[], records_to_update=[]
        )
        mock_router_diff = {
            "routes_to_add": {},
            "routes_to_remove": {},
            "routes_to_update": {},
        }
        dns_manager_mock.get_current_diff = AsyncMock(
            return_value=(mock_dns_diff, mock_router_diff)
        )

        result = await get_dns_status(mock_admin_user)

        # Now result is a DNSStatusResponse object
        assert result.initialized is True
        assert result.dns_diff is not None
        assert result.router_diff is not None


@pytest.mark.asyncio
async def test_get_dns_status_not_initialized(client, mock_admin_user):
    """Status delegates initialization and preserves manager errors."""

    from app.routers.dns import get_dns_status

    with (
        patch("app.routers.dns.simple_dns_manager") as dns_manager_mock,
        patch("app.routers.dns.config") as mock_config,
    ):
        # Mock DNS config as enabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = True
        mock_config.dns = mock_dns_config

        # Mock DNS manager - not initialized
        dns_manager_mock.is_initialized = False
        dns_manager_mock.get_current_diff = AsyncMock(
            side_effect=RuntimeError("DNS manager not initialized")
        )

        with pytest.raises(RuntimeError, match="DNS manager not initialized"):
            await get_dns_status(mock_admin_user)
        dns_manager_mock.get_current_diff.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_dns_endpoint_disabled(client, mock_admin_user):
    """Test DNS update when DNS is disabled in config"""
    from fastapi import HTTPException

    from app.routers.dns import update_dns

    with patch("app.routers.dns.config") as mock_config:
        # Mock DNS config as disabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = False
        mock_config.dns = mock_dns_config

        # Should raise HTTPException 503 when DNS is disabled
        with pytest.raises(HTTPException) as exc_info:
            await update_dns(mock_admin_user)

        assert exc_info.value.status_code == 503
        assert "disabled" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_dns_enabled_true(client, mock_admin_user):
    """Test getting DNS enabled status when enabled"""
    from app.routers.dns import get_dns_enabled

    with patch("app.routers.dns.config") as mock_config:
        # Mock DNS config as enabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = True
        mock_config.dns = mock_dns_config

        result = await get_dns_enabled(mock_admin_user)

        assert result.enabled is True


@pytest.mark.asyncio
async def test_get_dns_enabled_false(client, mock_admin_user):
    """Test getting DNS enabled status when disabled"""
    from app.routers.dns import get_dns_enabled

    with patch("app.routers.dns.config") as mock_config:
        # Mock DNS config as disabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = False
        mock_config.dns = mock_dns_config

        result = await get_dns_enabled(mock_admin_user)

        assert result.enabled is False


@pytest.mark.asyncio
async def test_dns_update_response_model():
    """Test DNSUpdateResponse model"""
    from app.routers.dns import DNSUpdateResponse

    # Test successful response
    response = DNSUpdateResponse(success=True, message="DNS updated successfully")
    assert response.success is True
    assert response.message == "DNS updated successfully"

    # Test error response
    response = DNSUpdateResponse(success=False, message="Update failed")
    assert response.success is False
    assert response.message == "Update failed"


def test_dns_router_authentication_required():
    """Test that DNS endpoints require authentication"""
    # This test would need more complex setup to properly test authentication
    # For now, we verify that the endpoints are decorated with auth requirements
    from app.routers.dns import router

    # Find the update endpoint
    update_route = None
    for route in router.routes:
        if isinstance(route, APIRoute) and "/update" in route.path:
            update_route = route
            break

    assert update_route is not None
    # The route should have dependencies (authentication)
    assert hasattr(update_route, "dependant")
    # This is a basic check - more detailed auth testing would require
    # integration tests with the full FastAPI dependency system


def test_get_dns_records_success(client):
    """Test DNS records endpoint success"""
    with (
        patch("app.routers.dns.simple_dns_manager") as mock_manager,
        patch("app.routers.dns.config") as mock_config,
    ):
        # Mock manager as initialized
        mock_manager.is_initialized = True

        # Mock DNS config
        mock_dns_config = Mock()
        mock_dns_config.managed_sub_domain = "mc"
        mock_config.dns = mock_dns_config

        mock_manager.get_dns_records = AsyncMock(
            return_value=[
                ReturnRecordT(
                    sub_domain="*.mc",
                    value="192.168.1.100",
                    record_id="12345",
                    record_type="A",
                    ttl=300,
                ),
                ReturnRecordT(
                    sub_domain="_minecraft._tcp.server1.mc",
                    value="0 5 25565 server1.mc.example.com",
                    record_id="12346",
                    record_type="SRV",
                    ttl=300,
                ),
            ]
        )

        response = client.get(
            "/api/dns/records", headers={"Authorization": "Bearer test_master_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert len(data) == 2
        assert data[0]["sub_domain"] == "*.mc"
        assert data[0]["value"] == "192.168.1.100"
        assert data[0]["record_id"] == "12345"
        assert data[0]["record_type"] == "A"
        assert data[0]["ttl"] == 300

        assert data[1]["sub_domain"] == "_minecraft._tcp.server1.mc"
        assert data[1]["value"] == "0 5 25565 server1.mc.example.com"
        assert data[1]["record_id"] == "12346"
        assert data[1]["record_type"] == "SRV"
        assert data[1]["ttl"] == 300


def test_get_dns_records_not_initialized(client):
    """Test DNS records endpoint when manager not initialized"""
    with (
        patch("app.routers.dns.simple_dns_manager") as mock_manager,
        patch("app.routers.dns.config") as mock_config,
    ):
        # Mock manager as not initialized
        mock_manager.is_initialized = False
        mock_manager.initialize = AsyncMock()

        # Mock DNS config
        mock_dns_config = Mock()
        mock_dns_config.managed_sub_domain = "mc"
        mock_config.dns = mock_dns_config

        mock_manager.get_dns_records = AsyncMock(return_value=[])

        response = client.get(
            "/api/dns/records", headers={"Authorization": "Bearer test_master_token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []

        mock_manager.initialize.assert_not_called()
        mock_manager.get_dns_records.assert_awaited_once()



def test_get_router_routes_success(client):
    """Test router routes endpoint success"""
    with (
        patch("app.routers.dns.simple_dns_manager") as mock_manager,
        patch("app.routers.dns.config") as mock_config,
    ):
        # Mock DNS config as enabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = True
        mock_config.dns = mock_dns_config

        # Mock manager as initialized
        mock_manager.is_initialized = True

        mock_manager.get_router_routes = AsyncMock(
            return_value={
                "server1.example.com": "192.168.1.100:25565",
                "server2.example.com": "192.168.1.101:25566",
            }
        )

        response = client.get(
            "/api/dns/routes", headers={"Authorization": "Bearer test_master_token"}
        )

        assert response.status_code == 200
        data = response.json()

        assert "server1.example.com" in data
        assert "server2.example.com" in data
        assert data["server1.example.com"] == "192.168.1.100:25565"
        assert data["server2.example.com"] == "192.168.1.101:25566"


def test_get_router_routes_not_initialized(client):
    """Test router routes endpoint when manager not initialized"""
    with (
        patch("app.routers.dns.simple_dns_manager") as mock_manager,
        patch("app.routers.dns.config") as mock_config,
    ):
        # Mock DNS config as enabled
        mock_dns_config = Mock()
        mock_dns_config.enabled = True
        mock_config.dns = mock_dns_config

        # Mock manager as not initialized
        mock_manager.is_initialized = False
        mock_manager.initialize = AsyncMock()

        mock_manager.get_router_routes = AsyncMock(return_value={})

        response = client.get(
            "/api/dns/routes", headers={"Authorization": "Bearer test_master_token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data == {}

        mock_manager.initialize.assert_not_called()
        mock_manager.get_router_routes.assert_awaited_once()


@pytest.mark.parametrize(
    ("path", "method"),
    [("records", "get_dns_records"), ("routes", "get_router_routes")],
)
def test_dns_read_failure_returns_500(client, path, method):
    with (
        patch("app.routers.dns.simple_dns_manager") as manager,
        patch("app.routers.dns.config") as settings,
    ):
        settings.dns.enabled = True
        operation = AsyncMock(side_effect=RuntimeError("Provider unavailable"))
        setattr(manager, method, operation)
        response = client.get(
            f"/api/dns/{path}",
            headers={"Authorization": "Bearer test_master_token"},
        )
        assert response.status_code == 500
        assert "Provider unavailable" in response.json()["detail"]
        operation.assert_awaited_once()


@pytest.mark.parametrize("path", ["status", "records", "routes"])
def test_disabled_dns_reads_return_503_without_initialization(client, path):
    with (
        patch("app.routers.dns.simple_dns_manager") as manager,
        patch("app.routers.dns.config") as settings,
    ):
        settings.dns.enabled = False
        response = client.get(
            f"/api/dns/{path}",
            headers={"Authorization": "Bearer test_master_token"},
        )
        assert response.status_code == 503
        assert "disabled" in response.json()["detail"]
        assert manager.mock_calls == []


def test_dns_endpoints_authentication_required(client):
    """Test that new DNS endpoints require authentication"""
    # Test DNS records endpoint
    response = client.get("/api/dns/records")
    assert response.status_code == 401

    # Test router routes endpoint
    response = client.get("/api/dns/routes")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_relevant_records_filtering():
    """Test that list_relevant_records properly filters DNS records"""
    from app.dns.dns import DNSClient
    from app.dns.types import ReturnRecordT

    # Create a mock DNS client that implements list_records
    class MockDNSClient(DNSClient):
        def get_domain(self) -> str:
            return "example.com"

        def is_initialized(self) -> bool:
            return True

        async def init(self):
            pass

        async def list_records(self):
            # Return a mix of relevant and irrelevant records
            return [
                # Relevant: Wildcard A record for managed subdomain
                ReturnRecordT("*.mc", "192.168.1.100", "1", "A", 300),
                # Relevant: SRV record for minecraft
                ReturnRecordT(
                    "_minecraft._tcp.server1.mc",
                    "0 5 25565 server1.mc.example.com",
                    "2",
                    "SRV",
                    300,
                ),
                # Irrelevant: Regular A record outside managed subdomain
                ReturnRecordT("www", "192.168.1.200", "3", "A", 300),
                # Irrelevant: Wildcard but wrong subdomain
                ReturnRecordT("*.api", "192.168.1.300", "4", "A", 300),
                # Irrelevant: SRV but not minecraft
                ReturnRecordT(
                    "_http._tcp.web.mc", "0 5 80 web.mc.example.com", "5", "SRV", 300
                ),
                # Relevant: Another minecraft SRV record
                ReturnRecordT(
                    "_minecraft._tcp.server2.backup.mc",
                    "0 5 25566 server2.backup.mc.example.com",
                    "6",
                    "SRV",
                    300,
                ),
            ]

        def has_update_capability(self) -> bool:
            return False

        async def remove_records(self, record_ids):
            pass

        async def add_records(self, records):
            pass

    client = MockDNSClient()

    # Test filtering
    relevant_records = await client.list_relevant_records("mc")

    # Should only return 3 relevant records
    assert len(relevant_records) == 3

    # Check that we got the right records
    relevant_subdomains = [record.sub_domain for record in relevant_records]
    assert "*.mc" in relevant_subdomains
    assert "_minecraft._tcp.server1.mc" in relevant_subdomains
    assert "_minecraft._tcp.server2.backup.mc" in relevant_subdomains

    # Check that irrelevant records are filtered out
    assert "www" not in relevant_subdomains
    assert "*.api" not in relevant_subdomains
    assert "_http._tcp.web.mc" not in relevant_subdomains
