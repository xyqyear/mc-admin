"""
Tests for DNS client diff functionality
"""

import pytest
from unittest.mock import AsyncMock

from app.dns.dns import DNSClient
from app.dns.types import AddRecordT, ReturnRecordT
from app.dns.utils import RecordDiff


class MockDNSClient(DNSClient):
    """Mock DNS client for testing diff functionality"""

    def __init__(self):
        self.domain = "example.com"
        self.initialized = True
        self._records = []

    def get_domain(self) -> str:
        return self.domain

    def is_initialized(self) -> bool:
        return self.initialized

    async def init(self):
        self.initialized = True

    async def list_records(self):
        return self._records

    def has_update_capability(self) -> bool:
        return True

    async def _update_records_batch(self, records):
        pass

    async def remove_records(self, record_ids):
        pass

    async def add_records(self, records):
        pass

    def set_current_records(self, records):
        """Helper method to set current records for testing"""
        self._records = records


class TestDNSClientDiff:
    """Test DNS client diff functionality"""

    @pytest.fixture
    def dns_client(self):
        """Create a mock DNS client"""
        return MockDNSClient()

    @pytest.mark.asyncio
    async def test_get_records_diff_empty_current_and_target(self, dns_client):
        """Test diff with no current records and no target records"""
        dns_client.set_current_records([])
        target_records = []

        diff = await dns_client.get_records_diff(target_records)

        assert len(diff.records_to_add) == 0
        assert len(diff.records_to_remove) == 0
        assert len(diff.records_to_update) == 0

    @pytest.mark.asyncio
    async def test_get_records_diff_add_new_records(self, dns_client):
        """Test diff when adding new records"""
        dns_client.set_current_records([])
        target_records = [
            AddRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",
                record_type="A",
                ttl=300
            ),
            AddRecordT(
                sub_domain="_minecraft._tcp.server1.mc",
                value="0 5 25565 server1.mc.example.com",
                record_type="SRV",
                ttl=300
            )
        ]

        diff = await dns_client.get_records_diff(target_records)

        assert len(diff.records_to_add) == 2
        assert len(diff.records_to_remove) == 0
        assert len(diff.records_to_update) == 0

        # Check first record to add
        assert diff.records_to_add[0].sub_domain == "*.mc"
        assert diff.records_to_add[0].value == "192.168.1.100"
        assert diff.records_to_add[0].record_type == "A"

        # Check second record to add
        assert diff.records_to_add[1].sub_domain == "_minecraft._tcp.server1.mc"
        assert diff.records_to_add[1].record_type == "SRV"

    @pytest.mark.asyncio
    async def test_get_records_diff_remove_old_records(self, dns_client):
        """Test diff when removing old records"""
        current_records = [
            ReturnRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",
                record_id="record123",
                record_type="A",
                ttl=300
            ),
            ReturnRecordT(
                sub_domain="old.mc",
                value="192.168.1.200",
                record_id="record456",
                record_type="A",
                ttl=300
            )
        ]
        dns_client.set_current_records(current_records)
        target_records = []

        diff = await dns_client.get_records_diff(target_records)

        assert len(diff.records_to_add) == 0
        assert len(diff.records_to_remove) == 2
        assert len(diff.records_to_update) == 0

        assert "record123" in diff.records_to_remove
        assert "record456" in diff.records_to_remove

    @pytest.mark.asyncio
    async def test_get_records_diff_update_existing_records(self, dns_client):
        """Test diff when updating existing records"""
        current_records = [
            ReturnRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",
                record_id="record123",
                record_type="A",
                ttl=300
            )
        ]
        dns_client.set_current_records(current_records)

        target_records = [
            AddRecordT(
                sub_domain="*.mc",
                value="192.168.1.200",  # Different IP
                record_type="A",
                ttl=600  # Different TTL
            )
        ]

        diff = await dns_client.get_records_diff(target_records)

        assert len(diff.records_to_add) == 0
        assert len(diff.records_to_remove) == 0
        assert len(diff.records_to_update) == 1

        update_record = diff.records_to_update[0]
        assert update_record.sub_domain == "*.mc"
        assert update_record.value == "192.168.1.200"
        assert update_record.record_id == "record123"
        assert update_record.ttl == 600

    @pytest.mark.asyncio
    async def test_get_records_diff_no_changes_needed(self, dns_client):
        """Test diff when no changes are needed"""
        current_records = [
            ReturnRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",
                record_id="record123",
                record_type="A",
                ttl=300
            )
        ]
        dns_client.set_current_records(current_records)

        target_records = [
            AddRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",  # Same IP
                record_type="A",
                ttl=300  # Same TTL
            )
        ]

        diff = await dns_client.get_records_diff(target_records)

        assert len(diff.records_to_add) == 0
        assert len(diff.records_to_remove) == 0
        assert len(diff.records_to_update) == 0

    @pytest.mark.asyncio
    async def test_get_records_diff_mixed_operations(self, dns_client):
        """Test diff with mixed add, remove, and update operations"""
        current_records = [
            ReturnRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",
                record_id="record123",
                record_type="A",
                ttl=300
            ),
            ReturnRecordT(
                sub_domain="old.mc",
                value="192.168.1.200",
                record_id="record456",
                record_type="A",
                ttl=300
            ),
            ReturnRecordT(
                sub_domain="update.mc",
                value="192.168.1.300",
                record_id="record789",
                record_type="A",
                ttl=300
            )
        ]
        dns_client.set_current_records(current_records)

        target_records = [
            # Keep this one unchanged
            AddRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",
                record_type="A",
                ttl=300
            ),
            # Update this one
            AddRecordT(
                sub_domain="update.mc",
                value="192.168.1.400",  # Different IP
                record_type="A",
                ttl=300
            ),
            # Add this new one
            AddRecordT(
                sub_domain="new.mc",
                value="192.168.1.500",
                record_type="A",
                ttl=300
            )
            # old.mc is removed (not in target)
        ]

        diff = await dns_client.get_records_diff(target_records)

        # Should add new.mc
        assert len(diff.records_to_add) == 1
        assert diff.records_to_add[0].sub_domain == "new.mc"

        # Should remove old.mc
        assert len(diff.records_to_remove) == 1
        assert "record456" in diff.records_to_remove

        # Should update update.mc
        assert len(diff.records_to_update) == 1
        assert diff.records_to_update[0].sub_domain == "update.mc"
        assert diff.records_to_update[0].value == "192.168.1.400"

    @pytest.mark.asyncio
    async def test_get_records_diff_with_managed_subdomain(self, dns_client):
        """Test diff with managed subdomain filtering"""
        # Add some records that should be filtered out
        all_records = [
            ReturnRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",
                record_id="record123",
                record_type="A",
                ttl=300
            ),
            ReturnRecordT(
                sub_domain="www",  # This should be filtered out
                value="192.168.1.200",
                record_id="record456",
                record_type="A",
                ttl=300
            ),
            ReturnRecordT(
                sub_domain="_minecraft._tcp.server1.mc",
                value="0 5 25565 server1.mc.example.com",
                record_id="record789",
                record_type="SRV",
                ttl=300
            )
        ]
        dns_client.set_current_records(all_records)

        target_records = [
            AddRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",
                record_type="A",
                ttl=300
            )
        ]

        # Test with managed subdomain - should filter records
        diff = await dns_client.get_records_diff(target_records, managed_sub_domain="mc")

        # Should not try to remove the "www" record since it's not managed
        # Should only try to remove the SRV record since it's managed but not in target
        assert len(diff.records_to_add) == 0
        assert len(diff.records_to_remove) == 1
        assert "record789" in diff.records_to_remove  # SRV record should be removed
        assert len(diff.records_to_update) == 0

    @pytest.mark.asyncio
    async def test_get_records_diff_empty_target_records(self, dns_client):
        """Test diff with empty target records - should remove all current records"""
        current_records = [
            ReturnRecordT(
                sub_domain="*.mc",
                value="192.168.1.100",
                record_id="record123",
                record_type="A",
                ttl=300
            )
        ]
        dns_client.set_current_records(current_records)

        # Empty target records should result in removing all current records
        diff = await dns_client.get_records_diff([])

        assert len(diff.records_to_add) == 0
        assert len(diff.records_to_remove) == 1
        assert "record123" in diff.records_to_remove
        assert len(diff.records_to_update) == 0