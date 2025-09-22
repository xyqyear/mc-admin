"""
Basic tests for DNS functionality without complex fixtures
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.dns.types import AddRecordT, ReturnRecordT
from app.dns.utils import RecordDiff, diff_dns_records


class TestDNSBasicFunctionality:
    """Test basic DNS functionality"""

    def test_dns_diff_basic(self):
        """Test basic DNS diff functionality"""
        old_records = [
            ReturnRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",
                record_id="record123",
                record_type="A",
                ttl=300
            )
        ]

        new_records = [
            AddRecordT(
                sub_domain="*.mc",
                value="192.168.1.200",  # Changed IP
                record_type="A",
                ttl=300
            )
        ]

        diff = diff_dns_records(old_records, new_records)

        assert len(diff.records_to_add) == 0
        assert len(diff.records_to_remove) == 0
        assert len(diff.records_to_update) == 1
        assert diff.records_to_update[0].value == "192.168.1.200"

    @pytest.mark.asyncio
    async def test_dns_manager_get_current_diff_not_initialized(self):
        """Test DNS manager get_current_diff when not initialized"""
        from app.dns.manager import SimpleDNSManager

        manager = SimpleDNSManager()

        # Mock the config access to avoid initialization issues
        mock_config = MagicMock()
        mock_config.dns.enabled = True

        with patch("app.dns.manager.config", mock_config):
            with patch.object(manager, "_ensure_up_to_date_config", new_callable=AsyncMock):
                result = await manager.get_current_diff()

        assert result["dns_diff"] is None
        assert result["router_diff"] is None
        assert len(result["errors"]) == 1
        assert "DNS manager not initialized" in result["errors"]

    def test_record_diff_structure(self):
        """Test RecordDiff structure"""
        diff = RecordDiff(
            records_to_add=[],
            records_to_remove=[],
            records_to_update=[]
        )

        assert hasattr(diff, 'records_to_add')
        assert hasattr(diff, 'records_to_remove')
        assert hasattr(diff, 'records_to_update')

    @pytest.mark.asyncio
    async def test_dns_status_models(self):
        """Test DNS status response models"""
        from app.routers.dns import DNSStatusResponse, DNSRecordDiff, RouterDiff

        # Test creating DNS status response
        dns_diff = DNSRecordDiff(
            records_to_add=[],
            records_to_remove=[],
            records_to_update=[]
        )

        router_diff = RouterDiff(
            routes_to_add={},
            routes_to_remove={},
            routes_to_update={}
        )

        status = DNSStatusResponse(
            initialized=True,
            dns_diff=dns_diff,
            router_diff=router_diff,
            errors=[]
        )

        assert status.initialized is True
        assert status.dns_diff is not None
        assert status.router_diff is not None
        assert len(status.errors) == 0

    def test_dns_enabled_model(self):
        """Test DNS enabled response model"""
        from app.routers.dns import DNSEnabledResponse

        response = DNSEnabledResponse(enabled=True)
        assert response.enabled is True

        response = DNSEnabledResponse(enabled=False)
        assert response.enabled is False