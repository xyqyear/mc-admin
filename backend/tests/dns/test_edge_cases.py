import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.dns.dns import AddRecordT, DNSClient, ReturnRecordT
from app.dns.manager import DNSManager
from app.dns.mcdns import MCDNS, AddressesT, AddressInfoT
from app.dns.router import MCRouter


class DummyDNSClient(DNSClient):
    def __init__(self, domain: str, should_fail: bool = False):
        self._domain = domain
        self._should_fail = should_fail
        self._records = {}
        self._next_id = 0

    def get_domain(self) -> str:
        return self._domain

    def is_initialized(self) -> bool:
        return True

    def has_update_capability(self) -> bool:
        return True

    async def init(self):
        if self._should_fail:
            raise Exception("DNS client initialization failed")

    async def list_records(self):
        if self._should_fail:
            raise Exception("Failed to list records")
        return list(self._records.values())

    async def add_records(self, records):
        if self._should_fail:
            raise Exception("Failed to add records")
        for record in records:
            self._next_id += 1
            self._records[self._next_id] = ReturnRecordT(
                sub_domain=record.sub_domain,
                value=record.value,
                record_id=self._next_id,
                record_type=record.record_type,
                ttl=record.ttl,
            )

    async def remove_records(self, record_ids):
        if self._should_fail:
            raise Exception("Failed to remove records")
        for record_id in record_ids:
            self._records.pop(record_id, None)

    async def update_records(self, records):
        if self._should_fail:
            raise Exception("Failed to update records")
        for record in records:
            self._records[record.record_id] = record


@pytest.mark.asyncio
async def test_mcdns_pull_inconsistent_srv_records():
    """Test MCDNS.pull with inconsistent SRV records"""
    dns_client = DummyDNSClient("example.com")

    # Add inconsistent records: addresses for *, backup but SRV only for *
    await dns_client.add_records(
        [
            AddRecordT(sub_domain="*.mc", value="1.1.1.1", record_type="A", ttl=600),
            AddRecordT(
                sub_domain="*.backup.mc", value="2.2.2.2", record_type="A", ttl=600
            ),
            AddRecordT(
                sub_domain="_minecraft._tcp.vanilla.mc",
                value="0 5 25565 vanilla.mc.example.com",
                record_type="SRV",
                ttl=600,
            ),
            # Missing SRV record for backup address
        ]
    )

    mcdns = MCDNS(dns_client, "mc")

    with patch("app.dns.mcdns.logger") as mock_logger:
        result = await mcdns.pull()

        # Should return None due to inconsistency
        assert result is None

        # Should log inconsistency warning
        mock_logger.info.assert_called_once()


@pytest.mark.asyncio
async def test_mcdns_pull_missing_port_mapping():
    """Test MCDNS.pull when address exists but no port mapping"""
    dns_client = DummyDNSClient("example.com")

    # Add address record but no corresponding SRV record
    await dns_client.add_records(
        [
            AddRecordT(sub_domain="*.mc", value="1.1.1.1", record_type="A", ttl=600),
            # Missing SRV record for port mapping
        ]
    )

    mcdns = MCDNS(dns_client, "mc")
    result = await mcdns.pull()

    # Should return None due to missing port mapping
    assert result is None


@pytest.mark.asyncio
async def test_mcdns_pull_malformed_subdomain():
    """Test MCDNS.pull with malformed subdomain"""
    dns_client = DummyDNSClient("example.com")

    # Add record with malformed subdomain (too few parts)
    await dns_client.add_records(
        [
            AddRecordT(
                sub_domain="mc", value="1.1.1.1", record_type="A", ttl=600
            ),  # Should be *.mc
        ]
    )

    mcdns = MCDNS(dns_client, "mc")
    result = await mcdns.pull()

    # Should return empty result since no valid records found
    assert result is not None
    assert result.addresses == {}
    assert result.server_list == []


@pytest.mark.asyncio
async def test_mcdns_push_empty_data():
    """Test MCDNS.push with empty addresses and servers"""
    dns_client = DummyDNSClient("example.com")
    mcdns = MCDNS(dns_client, "mc")

    with patch("app.dns.mcdns.logger") as mock_logger:
        # Test empty addresses
        await mcdns.push(AddressesT({}), ["vanilla"])
        mock_logger.warning.assert_called_with(
            "addresses or server_list is empty, skipping dns update"
        )

        mock_logger.reset_mock()

        # Test empty servers
        await mcdns.push(
            AddressesT({"*": AddressInfoT(type="A", host="1.1.1.1", port=25565)}), []
        )
        mock_logger.warning.assert_called_with(
            "addresses or server_list is empty, skipping dns update"
        )


@pytest.mark.asyncio
async def test_mcdns_push_dns_client_failure():
    """Test MCDNS.push when DNS client operations fail"""
    dns_client = DummyDNSClient("example.com", should_fail=True)
    mcdns = MCDNS(dns_client, "mc")

    addresses = AddressesT({"*": AddressInfoT(type="A", host="1.1.1.1", port=25565)})
    servers = ["vanilla"]

    # Should propagate the exception
    with pytest.raises(Exception, match="Failed to list records"):
        await mcdns.push(addresses, servers)


@pytest.mark.asyncio
async def test_mcdns_concurrent_push_operations():
    """Test MCDNS.push with concurrent operations using lock"""
    dns_client = DummyDNSClient("example.com")
    mcdns = MCDNS(dns_client, "mc")

    addresses = AddressesT({"*": AddressInfoT(type="A", host="1.1.1.1", port=25565)})
    servers = ["vanilla"]

    # Test that concurrent push operations are serialized
    tasks = []
    for _ in range(3):
        task = asyncio.create_task(mcdns.push(addresses, servers))
        tasks.append(task)

    # All should complete successfully
    await asyncio.gather(*tasks)

    # DNS should have the final state
    records = await dns_client.list_records()
    assert len(records) == 2  # 1 A record + 1 SRV record


@pytest.mark.asyncio
async def test_mcrouter_pull_malformed_backend():
    """Test MCRouter.pull with malformed backend addresses"""
    mock_client = AsyncMock()
    mock_client.get_routes.return_value = {
        "vanilla.mc.example.com": "malformed_backend",  # No port
        "creative.mc.example.com": "localhost:25566",  # Valid
    }

    router = MCRouter(mock_client, "example.com", "mc")
    _, servers = await router.pull()

    # Should handle malformed backend gracefully, using default port
    assert "vanilla" in servers
    assert servers["vanilla"] == 25565  # Default port
    assert "creative" in servers
    assert servers["creative"] == 25566


@pytest.mark.asyncio
async def test_mcrouter_pull_malformed_server_address():
    """Test MCRouter.pull with malformed server addresses"""
    mock_client = AsyncMock()
    mock_client.get_routes.return_value = {
        "invalid_format": "localhost:25565",  # Doesn't match expected pattern
        "vanilla.mc.example.com": "localhost:25566",  # Valid
    }

    router = MCRouter(mock_client, "example.com", "mc")

    # Should handle malformed addresses by skipping them
    _, servers = await router.pull()

    # Should only include the valid route
    assert "vanilla" in servers
    assert servers["vanilla"] == 25566


@pytest.mark.asyncio
async def test_mcrouter_push_large_dataset():
    """Test MCRouter.push with large number of servers and addresses"""
    mock_client = AsyncMock()
    router = MCRouter(mock_client, "example.com", "mc")

    # Generate large dataset
    address_list = [f"addr_{i}" for i in range(100)]
    servers = {f"server_{i}": 25565 + i for i in range(100)}

    await router.push(address_list, servers)

    mock_client.override_routes.assert_called_once()

    # Check that all combinations were generated
    call_args = mock_client.override_routes.call_args[0][0]
    expected_routes = len(address_list) * len(servers)
    assert len(call_args) == expected_routes


@pytest.mark.asyncio
async def test_dns_manager_rapid_queue_updates():
    """Test DNSManager with rapid successive queue updates"""
    manager = DNSManager()

    # Queue many updates rapidly
    for _ in range(10):
        manager._queue_update()

    assert manager._update_queue == 10

    # Test queue processing
    manager._running = True
    processed_count = 0

    async def mock_try_update():
        nonlocal processed_count
        processed_count += 1
        if processed_count >= 10:
            manager._running = False

    with patch.object(manager, "_try_update", side_effect=mock_try_update):
        with patch("asyncio.sleep"):
            await manager._check_queue_loop()

    assert manager._update_queue == 0
    assert processed_count == 10


@pytest.mark.asyncio
async def test_dns_manager_background_task_exception():
    """Test DNSManager background task exception handling"""
    manager = DNSManager()

    # Simulate background task failure during stop
    mock_task = AsyncMock()
    mock_task.done.return_value = False

    manager._background_tasks = [mock_task]
    manager._running = True

    async def mock_gather(*args, **kwargs):
        return None

    with patch("asyncio.gather", side_effect=mock_gather):
        with patch("app.dns.manager.logger"):
            # Should handle gracefully
            await manager.stop()

            # Should still set running to False
            assert not manager._running
            assert manager._background_tasks == []


@pytest.mark.asyncio
async def test_mcdns_set_dns_client_and_ttl():
    """Test MCDNS utility methods for testing and migration"""
    dns_client1 = DummyDNSClient("example.com")
    dns_client2 = DummyDNSClient("other.com")

    mcdns = MCDNS(dns_client1, "mc", 600)

    # Test set_dns_client
    mcdns.set_dns_client(dns_client2)
    assert mcdns._dns_client.get_domain() == "other.com"

    # Test set_ttl
    mcdns.set_ttl(300)
    assert mcdns._dns_ttl == 300


@pytest.mark.asyncio
async def test_mcdns_parse_srv_record_edge_cases():
    """Test MCDNS._parse_srv_record with various formats"""
    dns_client = DummyDNSClient("example.com")
    mcdns = MCDNS(dns_client, "mc")

    # Test single server name (no address)
    record1 = ReturnRecordT(
        sub_domain="_minecraft._tcp.vanilla.mc",
        value="0 5 25565 vanilla.mc.example.com",
        record_id=1,
        record_type="SRV",
        ttl=600,
    )
    result1 = mcdns._parse_srv_record(record1)
    assert result1.server_name == "vanilla"
    assert result1.address_name == "*"
    assert result1.port == 25565

    # Test with address name
    record2 = ReturnRecordT(
        sub_domain="_minecraft._tcp.vanilla.backup.mc",
        value="0 5 25566 vanilla.backup.mc.example.com",
        record_id=2,
        record_type="SRV",
        ttl=600,
    )
    result2 = mcdns._parse_srv_record(record2)
    assert result2.server_name == "vanilla"
    assert result2.address_name == "backup"
    assert result2.port == 25566


@pytest.mark.asyncio
async def test_dns_client_not_initialized():
    """Test MCDNS operations when DNS client is not initialized"""

    class UninitializedDNSClient(DummyDNSClient):
        def __init__(self):
            super().__init__("example.com")
            self._initialized = False

        def is_initialized(self) -> bool:
            return self._initialized

        async def init(self):
            self._initialized = True

    dns_client = UninitializedDNSClient()
    mcdns = MCDNS(dns_client, "mc")

    # Should automatically initialize when pulling
    await mcdns.pull()
    assert dns_client.is_initialized()


@pytest.mark.asyncio
async def test_mcdns_diff_update_records_comprehensive():
    """Test MCDNS._diff_update_records with complex scenarios"""
    # Test comprehensive record diff scenarios
    old_records = [
        ReturnRecordT("test1.mc", "1.1.1.1", 1, "A", 600),  # Will be updated
        ReturnRecordT("test2.mc", "2.2.2.2", 2, "A", 600),  # Will be removed
        ReturnRecordT("test3.mc", "3.3.3.3", 3, "A", 600),  # Will stay same
    ]

    new_records = [
        AddRecordT("test1.mc", "1.1.1.2", "A", 300),  # Updated value and TTL
        AddRecordT("test3.mc", "3.3.3.3", "A", 600),  # Same
        AddRecordT("test4.mc", "4.4.4.4", "A", 600),  # New
    ]

    result = MCDNS._diff_update_records(old_records, new_records)

    # Should have 1 add, 1 remove, 1 update
    assert len(result.records_to_add) == 1
    assert result.records_to_add[0].sub_domain == "test4.mc"

    assert len(result.records_to_remove) == 1
    assert 2 in result.records_to_remove

    assert len(result.records_to_update) == 1
    assert result.records_to_update[0].sub_domain == "test1.mc"
    assert result.records_to_update[0].value == "1.1.1.2"
