from unittest.mock import MagicMock, patch

import pytest

from app.dns.dns import AddRecordT
from app.dns.huawei import HuaweiDNSClient


class MockZoneInfo:
    def __init__(self, id: str, name: str):
        self.id = id
        self.name = name


class MockRecordSet:
    def __init__(self, id: str, name: str, type: str, ttl: int, records: list[str]):
        self.id = id
        self.name = name
        self.type = type
        self.ttl = ttl
        self.records = records


class MockListPublicZonesResponse:
    def __init__(self, zones: list[MockZoneInfo]):
        self.zones = zones


class MockListRecordSetsByZoneResponse:
    def __init__(self, recordsets: list[MockRecordSet]):
        self.recordsets = recordsets


@pytest.fixture
def mock_huawei_client():
    with patch("app.dns.huawei.DnsClient") as mock_dns_client_class:
        mock_builder = MagicMock()
        mock_dns_client_class.new_builder.return_value = mock_builder
        mock_builder.with_credentials.return_value = mock_builder
        mock_builder.with_region.return_value = mock_builder

        mock_client_instance = MagicMock()
        mock_builder.build.return_value = mock_client_instance

        with patch("app.dns.huawei.DnsRegion") as mock_region:
            mock_region.value_of.return_value = "cn-south-1"

            client = HuaweiDNSClient("example.com", "test_ak", "test_sk", "cn-south-1")

            yield client, mock_client_instance


@pytest.mark.asyncio
async def test_huawei_client_initialization():
    with patch("app.dns.huawei.DnsClient") as mock_dns_client_class:
        mock_builder = MagicMock()
        mock_dns_client_class.new_builder.return_value = mock_builder
        mock_builder.with_credentials.return_value = mock_builder
        mock_builder.with_region.return_value = mock_builder
        mock_builder.build.return_value = MagicMock()

        with patch("app.dns.huawei.DnsRegion") as mock_region:
            mock_region.value_of.return_value = "cn-south-1"

            client = HuaweiDNSClient("example.com", "test_ak", "test_sk")

            assert client.get_domain() == "example.com"
            assert not client.is_initialized()


@pytest.mark.asyncio
async def test_huawei_client_init_success(mock_huawei_client):
    client, mock_instance = mock_huawei_client

    zones = [MockZoneInfo("zone123", "example.com.")]
    mock_response = MockListPublicZonesResponse(zones)
    mock_instance.list_public_zones.return_value = mock_response

    await client.init()

    assert client.is_initialized()
    assert client._zone_id == "zone123"


@pytest.mark.asyncio
async def test_huawei_client_init_zone_not_found(mock_huawei_client):
    client, mock_instance = mock_huawei_client

    zones = [MockZoneInfo("zone123", "other.com.")]
    mock_response = MockListPublicZonesResponse(zones)
    mock_instance.list_public_zones.return_value = mock_response

    with pytest.raises(Exception, match="There is no domain named example.com"):
        await client.init()


@pytest.mark.asyncio
async def test_huawei_client_list_records(mock_huawei_client):
    client, mock_instance = mock_huawei_client
    client._zone_id = "zone123"

    recordsets = [
        MockRecordSet("rec1", "test.example.com.", "A", 600, ["1.1.1.1"]),
        MockRecordSet(
            "rec2", "srv.example.com.", "SRV", 300, ["0 5 25565 target.example.com."]
        ),
        MockRecordSet(
            "rec3", "cname.example.com.", "CNAME", 600, ["target.example.com."]
        ),
        MockRecordSet("rec4", "external.other.com.", "A", 600, ["2.2.2.2"]),
    ]
    mock_response = MockListRecordSetsByZoneResponse(recordsets)
    mock_instance.list_record_sets_by_zone.return_value = mock_response

    records = await client.list_records()

    assert len(records) == 3

    a_record = next(r for r in records if r.record_type == "A")
    assert a_record.sub_domain == "test"
    assert a_record.value == "1.1.1.1"
    assert a_record.record_id == "rec1"

    srv_record = next(r for r in records if r.record_type == "SRV")
    assert srv_record.value == "0 5 25565 target.example.com"

    cname_record = next(r for r in records if r.record_type == "CNAME")
    assert cname_record.value == "target.example.com"


@pytest.mark.asyncio
async def test_huawei_client_has_update_capability():
    with patch("app.dns.huawei.DnsClient") as mock_dns_client_class:
        mock_builder = MagicMock()
        mock_dns_client_class.new_builder.return_value = mock_builder
        mock_builder.with_credentials.return_value = mock_builder
        mock_builder.with_region.return_value = mock_builder
        mock_builder.build.return_value = MagicMock()

        with patch("app.dns.huawei.DnsRegion") as mock_region:
            mock_region.value_of.return_value = "cn-south-1"

            client = HuaweiDNSClient("example.com", "test_ak", "test_sk")
            assert client.has_update_capability()


@pytest.mark.asyncio
async def test_huawei_client_update_records(mock_huawei_client):
    client, mock_instance = mock_huawei_client
    client._zone_id = "zone123"

    from app.dns.dns import AddRecordT

    target_records = [
        AddRecordT("test", "2.2.2.2", "A", 600),
        AddRecordT("srv", "0 5 25566 target.example.com", "SRV", 300),
    ]

    from unittest.mock import AsyncMock

    client.list_records = AsyncMock(return_value=[])

    await client.update_records(target_records)

    assert mock_instance.create_record_set.call_count >= 1


@pytest.mark.asyncio
async def test_huawei_client_remove_records(mock_huawei_client):
    client, mock_instance = mock_huawei_client
    client._zone_id = "zone123"

    record_ids = ["rec1", "rec2", "rec3"]

    await client.remove_records(record_ids)

    mock_instance.batch_delete_record_set_with_line.assert_called_once()


@pytest.mark.asyncio
async def test_huawei_client_add_records(mock_huawei_client):
    client, mock_instance = mock_huawei_client
    client._zone_id = "zone123"

    records = [
        AddRecordT(sub_domain="test", value="1.1.1.1", record_type="A", ttl=600),
        AddRecordT(
            sub_domain="srv",
            value="0 5 25565 target.example.com",
            record_type="SRV",
            ttl=300,
        ),
    ]

    await client.add_records(records)

    assert mock_instance.create_record_set.call_count == 2


@pytest.mark.asyncio
async def test_huawei_client_empty_operations(mock_huawei_client):
    client, mock_instance = mock_huawei_client
    client._zone_id = "zone123"

    await client.update_records([])
    mock_instance.batch_update_record_set_with_line.assert_not_called()

    await client.remove_records([])
    mock_instance.batch_delete_record_set_with_line.assert_not_called()

    await client.add_records([])
    mock_instance.create_record_set.assert_not_called()


@pytest.mark.asyncio
async def test_huawei_client_default_region():
    with patch("app.dns.huawei.DnsClient") as mock_dns_client_class:
        mock_builder = MagicMock()
        mock_dns_client_class.new_builder.return_value = mock_builder
        mock_builder.with_credentials.return_value = mock_builder
        mock_builder.with_region.return_value = mock_builder
        mock_builder.build.return_value = MagicMock()

        with patch("app.dns.huawei.DnsRegion") as mock_region:
            mock_region.value_of.return_value = "cn-south-1"

            HuaweiDNSClient("example.com", "test_ak", "test_sk", None)

            mock_region.value_of.assert_called_with("cn-south-1")


@pytest.mark.asyncio
async def test_huawei_client_lock_property(mock_huawei_client):
    client, _ = mock_huawei_client

    lock = client.lock
    assert lock is not None
    assert hasattr(lock, "acquire")
    assert hasattr(lock, "release")


@pytest.mark.asyncio
async def test_huawei_client_record_filtering(mock_huawei_client):
    """Filter recordsets to only those whose name ends with the configured domain."""
    client, mock_instance = mock_huawei_client
    client._zone_id = "zone123"

    recordsets = [
        MockRecordSet("rec1", "test.example.com.", "A", 600, ["1.1.1.1"]),
        MockRecordSet("rec2", "external.other.com.", "A", 600, ["2.2.2.2"]),
        MockRecordSet("rec3", "another.example.com.", "A", 600, ["3.3.3.3"]),
        MockRecordSet("rec4", "unrelated.different.org.", "A", 600, ["4.4.4.4"]),
    ]
    mock_response = MockListRecordSetsByZoneResponse(recordsets)
    mock_instance.list_record_sets_by_zone.return_value = mock_response

    records = await client.list_records()

    assert len(records) == 2
    subdomains = [r.sub_domain for r in records]
    assert "test" in subdomains
    assert "another" in subdomains
