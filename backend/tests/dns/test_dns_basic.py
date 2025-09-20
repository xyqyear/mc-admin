from typing import NamedTuple

import pytest

from app.dns import ReturnRecordT
from app.dns.dns import (
    AddRecordListT,
    AddRecordT,
    DNSClient,
    RecordIdListT,
    RecordListT,
)


class DummyDNSClient(DNSClient):
    def __init__(self, domain: str, has_update_capability: bool = True):
        self._domain = domain
        self._records = dict[int | str, AddRecordT]()
        self._next_id = 0
        self._has_update_capability_value = has_update_capability

    def is_initialized(self) -> bool:
        return True

    def _get_next_id(self) -> int:
        self._next_id += 1
        return self._next_id

    def get_domain(self) -> str:
        return self._domain

    def has_update_capability(self) -> bool:
        return self._has_update_capability_value

    async def init(self):
        pass

    async def list_records(self) -> RecordListT:
        return [
            ReturnRecordT(
                sub_domain=record.sub_domain,
                value=record.value,
                record_id=record_id,
                record_type=record.record_type,
                ttl=record.ttl,
            )
            for record_id, record in self._records.items()
        ]

    async def update_records(self, target_records: AddRecordListT):
        # Get current records and calculate diff
        current_records = await self.list_records()
        from app.dns.utils import diff_dns_records

        diff = diff_dns_records(current_records, target_records)

        # Apply changes
        if diff.records_to_remove:
            await self.remove_records(diff.records_to_remove)
        if diff.records_to_add:
            await self.add_records(diff.records_to_add)
        # Handle updates by removing and re-adding
        if diff.records_to_update:
            await self.remove_records([r.record_id for r in diff.records_to_update])
            update_adds = [
                AddRecordT(r.sub_domain, r.value, r.record_type, r.ttl)
                for r in diff.records_to_update
            ]
            await self.add_records(update_adds)

    async def remove_records(self, record_ids: RecordIdListT):
        for record_id in record_ids:
            del self._records[record_id]

    async def add_records(self, records: AddRecordListT):
        for record in records:
            record_id = self._get_next_id()
            self._records[record_id] = record


def test_dummy_dns_client():
    """Test the dummy DNS client for basic functionality"""
    client = DummyDNSClient("example.com")
    assert client.get_domain() == "example.com"
    assert client.is_initialized() is True
    assert client.has_update_capability() is True


@pytest.mark.asyncio
async def test_dns_client_basic_operations():
    """Test basic DNS client operations"""
    client = DummyDNSClient("example.com")

    # Test adding records
    records = [
        AddRecordT(
            sub_domain="test",
            value="1.1.1.1",
            record_type="A",
            ttl=300,
        )
    ]

    await client.add_records(records)
    listed_records = await client.list_records()

    assert len(listed_records) == 1
    assert listed_records[0].sub_domain == "test"
    assert listed_records[0].value == "1.1.1.1"
    assert listed_records[0].record_type == "A"
    assert listed_records[0].ttl == 300


@pytest.mark.asyncio
async def test_dns_client_remove_records():
    """Test removing DNS records"""
    client = DummyDNSClient("example.com")

    # Add a record
    records = [
        AddRecordT(
            sub_domain="test",
            value="1.1.1.1",
            record_type="A",
            ttl=300,
        )
    ]

    await client.add_records(records)
    listed_records = await client.list_records()
    assert len(listed_records) == 1

    # Remove the record
    record_id = listed_records[0].record_id
    await client.remove_records([record_id])

    listed_records = await client.list_records()
    assert len(listed_records) == 0


@pytest.mark.asyncio
async def test_dns_client_update_records():
    """Test updating DNS records"""
    client = DummyDNSClient("example.com")

    # Add a record
    records = [
        AddRecordT(
            sub_domain="test",
            value="1.1.1.1",
            record_type="A",
            ttl=300,
        )
    ]

    await client.add_records(records)
    listed_records = await client.list_records()
    assert len(listed_records) == 1

    # Update the record
    record_to_update = listed_records[0]
    updated_record = AddRecordT(
        sub_domain=record_to_update.sub_domain,
        value="2.2.2.2",
        record_type=record_to_update.record_type,
        ttl=600,
    )

    await client.update_records([updated_record])

    listed_records = await client.list_records()
    assert len(listed_records) == 1
    assert listed_records[0].value == "2.2.2.2"
    assert listed_records[0].ttl == 600
