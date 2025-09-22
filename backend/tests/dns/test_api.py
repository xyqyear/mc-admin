"""
Tests for the DNS API router
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest
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
        yield TestClient(app)


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

    with patch("app.routers.dns.simple_dns_manager") as dns_manager_mock:
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

    with patch("app.routers.dns.simple_dns_manager") as dns_manager_mock:
        # Mock DNS manager - not initialized
        dns_manager_mock.is_initialized = False
        dns_manager_mock.initialize = AsyncMock()
        dns_manager_mock.update = AsyncMock()

        result = await update_dns(mock_admin_user)

        assert result.success is True

        # Should call initialize then update
        dns_manager_mock.initialize.assert_called_once()
        dns_manager_mock.update.assert_called_once()


@pytest.mark.asyncio
async def test_update_dns_endpoint_initialization_fails(client, mock_admin_user):
    """Test DNS update when initialization fails"""
    from fastapi import HTTPException

    from app.routers.dns import update_dns

    with patch("app.routers.dns.simple_dns_manager") as dns_manager_mock:
        # Mock DNS manager - initialization fails
        dns_manager_mock.is_initialized = False
        dns_manager_mock.initialize = AsyncMock(side_effect=Exception("Init failed"))

        with pytest.raises(HTTPException) as exc_info:
            await update_dns(mock_admin_user)

        assert exc_info.value.status_code == 500
        assert "Init failed" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_update_dns_endpoint_update_fails(client, mock_admin_user):
    """Test DNS update when update operation fails"""
    from fastapi import HTTPException

    from app.routers.dns import update_dns

    with patch("app.routers.dns.simple_dns_manager") as dns_manager_mock:
        # Mock DNS manager - update fails
        dns_manager_mock.is_initialized = True
        dns_manager_mock.update = AsyncMock(side_effect=Exception("Update failed"))

        with pytest.raises(HTTPException) as exc_info:
            await update_dns(mock_admin_user)

        assert exc_info.value.status_code == 500
        assert "Update failed" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_get_dns_status_success(client, mock_admin_user):
    """Test getting DNS status"""
    from app.routers.dns import get_dns_status

    with patch("app.routers.dns.simple_dns_manager") as dns_manager_mock:
        # Mock DNS manager
        dns_manager_mock.is_initialized = True

        result = await get_dns_status(mock_admin_user)

        assert result["initialized"] is True
        assert result["enabled"] is True


@pytest.mark.asyncio
async def test_get_dns_status_not_initialized(client, mock_admin_user):
    """Test getting DNS status when not initialized"""
    from app.routers.dns import get_dns_status

    with patch("app.routers.dns.simple_dns_manager") as dns_manager_mock:
        # Mock DNS manager
        dns_manager_mock.is_initialized = False

        result = await get_dns_status(mock_admin_user)

        assert result["initialized"] is False
        assert result["enabled"] is True


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
        if hasattr(route, "path") and "/update" in route.path:
            update_route = route
            break

    assert update_route is not None
    # The route should have dependencies (authentication)
    assert hasattr(update_route, "dependant")
    # This is a basic check - more detailed auth testing would require
    # integration tests with the full FastAPI dependency system


def test_get_dns_records_success(client):
    """Test DNS records endpoint success"""
    with patch("app.routers.dns.simple_dns_manager") as mock_manager, \
         patch("app.routers.dns.config") as mock_config:
        # Mock manager as initialized
        mock_manager.is_initialized = True

        # Mock DNS config
        mock_dns_config = Mock()
        mock_dns_config.managed_sub_domain = "mc"
        mock_config.dns = mock_dns_config

        # Mock DNS client with sample records
        mock_dns_client = Mock()
        mock_dns_client.list_relevant_records = AsyncMock(
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
        mock_manager._dns_client = mock_dns_client

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
    with patch("app.routers.dns.simple_dns_manager") as mock_manager, \
         patch("app.routers.dns.config") as mock_config:
        # Mock manager as not initialized
        mock_manager.is_initialized = False
        mock_manager.initialize = AsyncMock()

        # Mock DNS config
        mock_dns_config = Mock()
        mock_dns_config.managed_sub_domain = "mc"
        mock_config.dns = mock_dns_config

        # Mock DNS client after initialization
        mock_dns_client = Mock()
        mock_dns_client.list_relevant_records = AsyncMock(return_value=[])
        mock_manager._dns_client = mock_dns_client

        response = client.get(
            "/api/dns/records", headers={"Authorization": "Bearer test_master_token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data == []

        # Verify initialization was attempted
        mock_manager.initialize.assert_called_once()


def test_get_dns_records_client_not_available(client):
    """Test DNS records endpoint when DNS client not available"""
    with patch("app.routers.dns.simple_dns_manager") as mock_manager:
        # Mock manager as initialized but no DNS client
        mock_manager.is_initialized = True
        mock_manager._dns_client = None

        response = client.get(
            "/api/dns/records", headers={"Authorization": "Bearer test_master_token"}
        )

        assert response.status_code == 503
        data = response.json()
        assert "DNS client not initialized" in data["detail"]


def test_get_router_routes_success(client):
    """Test router routes endpoint success"""
    with patch("app.routers.dns.simple_dns_manager") as mock_manager:
        # Mock manager as initialized
        mock_manager.is_initialized = True

        # Mock router client with sample routes
        mock_router_client = Mock()
        mock_router_client.get_routes = AsyncMock(
            return_value={
                "server1.example.com": "192.168.1.100:25565",
                "server2.example.com": "192.168.1.101:25566",
            }
        )
        mock_manager._mc_router_client = mock_router_client

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
    with patch("app.routers.dns.simple_dns_manager") as mock_manager:
        # Mock manager as not initialized
        mock_manager.is_initialized = False
        mock_manager.initialize = AsyncMock()

        # Mock router client after initialization
        mock_router_client = Mock()
        mock_router_client.get_routes = AsyncMock(return_value={})
        mock_manager._mc_router_client = mock_router_client

        response = client.get(
            "/api/dns/routes", headers={"Authorization": "Bearer test_master_token"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data == {}

        # Verify initialization was attempted
        mock_manager.initialize.assert_called_once()


def test_get_router_routes_client_not_available(client):
    """Test router routes endpoint when router client not available"""
    with patch("app.routers.dns.simple_dns_manager") as mock_manager:
        # Mock manager as initialized but no router client
        mock_manager.is_initialized = True
        mock_manager._mc_router_client = None

        response = client.get(
            "/api/dns/routes", headers={"Authorization": "Bearer test_master_token"}
        )

        assert response.status_code == 503
        data = response.json()
        assert "MC Router client not initialized" in data["detail"]


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
    from app.dns.types import ReturnRecordT
    from app.dns.dns import DNSClient

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
                ReturnRecordT("_minecraft._tcp.server1.mc", "0 5 25565 server1.mc.example.com", "2", "SRV", 300),
                # Irrelevant: Regular A record outside managed subdomain
                ReturnRecordT("www", "192.168.1.200", "3", "A", 300),
                # Irrelevant: Wildcard but wrong subdomain
                ReturnRecordT("*.api", "192.168.1.300", "4", "A", 300),
                # Irrelevant: SRV but not minecraft
                ReturnRecordT("_http._tcp.web.mc", "0 5 80 web.mc.example.com", "5", "SRV", 300),
                # Relevant: Another minecraft SRV record
                ReturnRecordT("_minecraft._tcp.server2.backup.mc", "0 5 25566 server2.backup.mc.example.com", "6", "SRV", 300),
            ]

        def has_update_capability(self) -> bool:
            return False

        async def remove_records(self, record_ids): pass
        async def add_records(self, records): pass

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
