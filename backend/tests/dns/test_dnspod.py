import json
from unittest.mock import MagicMock, patch

import pytest
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)

from app.dns.dns import AddRecordT
from app.dns.dnspod import DNSPodClient


class MockDNSPodResponse:
    def __init__(self, response_data: dict):
        self._response_data = response_data

    def to_json_string(self) -> str:
        return json.dumps(self._response_data)


class MockDNSPodRequest:
    def from_json_string(self, json_str: str) -> None:
        pass


@pytest.fixture
def mock_dnspod_client():
    """Create a mock DNSPod client for testing"""
    with patch("app.dns.dnspod.dnspod_client.DnspodClient") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance

        # Mock request constructors
        with (
            patch("app.dns.dnspod.models.DescribeDomainListRequest") as mock_domain_req,
            patch("app.dns.dnspod.models.DescribeRecordListRequest") as mock_record_req,
            patch("app.dns.dnspod.models.ModifyRecordBatchRequest") as mock_modify_req,
            patch("app.dns.dnspod.models.DeleteRecordBatchRequest") as mock_delete_req,
            patch("app.dns.dnspod.models.CreateRecordBatchRequest") as mock_create_req,
        ):
            mock_domain_req.return_value = MockDNSPodRequest()
            mock_record_req.return_value = MockDNSPodRequest()
            mock_modify_req.return_value = MockDNSPodRequest()
            mock_delete_req.return_value = MockDNSPodRequest()
            mock_create_req.return_value = MockDNSPodRequest()

            client = DNSPodClient("example.com", "test_id", "test_key")
            client._client = mock_instance

            yield client, mock_instance


@pytest.mark.asyncio
async def test_dnspod_client_initialization():
    """Test DNSPod client initialization"""
    with patch("app.dns.dnspod.dnspod_client.DnspodClient"):
        client = DNSPodClient("example.com", "test_id", "test_key")

        assert client.get_domain() == "example.com"
        assert not client.is_initialized()


@pytest.mark.asyncio
async def test_dnspod_client_init_success(mock_dnspod_client):
    """Test successful initialization with domain lookup"""
    client, mock_instance = mock_dnspod_client

    # Mock successful domain list response
    domain_list_response = {"DomainList": [{"Name": "example.com", "DomainId": 12345}]}
    mock_instance.DescribeDomainList.return_value = MockDNSPodResponse(
        domain_list_response
    )

    await client.init()

    assert client.is_initialized()
    assert client._domain_id == 12345


@pytest.mark.asyncio
async def test_dnspod_client_init_no_domains(mock_dnspod_client):
    """Test initialization failure when no domains exist"""
    client, mock_instance = mock_dnspod_client

    # Mock empty domain list response
    domain_list_response = {"DomainList": []}
    mock_instance.DescribeDomainList.return_value = MockDNSPodResponse(
        domain_list_response
    )

    with pytest.raises(Exception, match="There is no domain in this account"):
        await client.init()


@pytest.mark.asyncio
async def test_dnspod_client_init_domain_not_found(mock_dnspod_client):
    """Test initialization failure when specific domain not found"""
    client, mock_instance = mock_dnspod_client

    # Mock domain list response with different domain
    domain_list_response = {"DomainList": [{"Name": "other.com", "DomainId": 54321}]}
    mock_instance.DescribeDomainList.return_value = MockDNSPodResponse(
        domain_list_response
    )

    with pytest.raises(Exception, match="There is no domain named example.com"):
        await client.init()


@pytest.mark.asyncio
async def test_dnspod_client_list_records(mock_dnspod_client):
    """Test listing DNS records"""
    client, mock_instance = mock_dnspod_client
    client._domain_id = 12345  # Simulate initialized state

    # Mock record list response
    record_list_response = {
        "RecordList": [
            {
                "Name": "test",
                "RecordId": 1,
                "Type": "A",
                "TTL": 600,
                "Value": "1.1.1.1",
            },
            {
                "Name": "srv",
                "RecordId": 2,
                "Type": "SRV",
                "TTL": 300,
                "Value": "0 5 25565 target.example.com.",
            },
        ]
    }
    mock_instance.DescribeRecordList.return_value = MockDNSPodResponse(
        record_list_response
    )

    records = await client.list_records()

    assert len(records) == 2
    assert records[0].sub_domain == "test"
    assert records[0].value == "1.1.1.1"
    assert records[0].record_type == "A"
    assert records[0].ttl == 600

    # Check SRV record value processing (remove trailing dot)
    assert records[1].value == "0 5 25565 target.example.com"


@pytest.mark.asyncio
async def test_dnspod_client_add_records(mock_dnspod_client):
    """Test adding DNS records"""
    client, mock_instance = mock_dnspod_client
    client._domain_id = 12345  # Simulate initialized state

    # Mock successful response
    mock_instance.CreateRecordBatch.return_value = MockDNSPodResponse({})

    records = [AddRecordT(sub_domain="test", value="1.1.1.1", record_type="A", ttl=600)]

    await client.add_records(records)

    # Verify the API was called
    mock_instance.CreateRecordBatch.assert_called_once()


@pytest.mark.asyncio
async def test_dnspod_client_remove_records(mock_dnspod_client):
    """Test removing DNS records"""
    client, mock_instance = mock_dnspod_client

    # Mock successful response
    mock_instance.DeleteRecordBatch.return_value = MockDNSPodResponse({})

    record_ids = [1, 2, 3]

    await client.remove_records(record_ids)

    # Verify the API was called
    mock_instance.DeleteRecordBatch.assert_called_once()


@pytest.mark.asyncio
async def test_dnspod_client_has_no_update_capability():
    """Test that DNSPod client doesn't support record updates"""
    with patch("app.dns.dnspod.dnspod_client.DnspodClient"):
        client = DNSPodClient("example.com", "test_id", "test_key")
        assert not client.has_update_capability()


@pytest.mark.asyncio
async def test_dnspod_client_retry_logic(mock_dnspod_client):
    """Test retry logic on API failures"""
    client, mock_instance = mock_dnspod_client

    # Mock first two calls to fail, third to succeed
    domain_list_response = {"DomainList": [{"Name": "example.com", "DomainId": 12345}]}

    mock_instance.DescribeDomainList.side_effect = [
        TencentCloudSDKException("error1"),
        TencentCloudSDKException("error2"),
        MockDNSPodResponse(domain_list_response),
    ]

    # Should succeed after retries
    await client.init()
    assert client.is_initialized()

    # Should have been called 3 times
    assert mock_instance.DescribeDomainList.call_count == 3


@pytest.mark.asyncio
async def test_dnspod_client_retry_exhausted(mock_dnspod_client):
    """Test retry logic when all retries are exhausted"""
    client, mock_instance = mock_dnspod_client

    # Mock all calls to fail
    error = TencentCloudSDKException("persistent error")
    mock_instance.DescribeDomainList.side_effect = error

    # Should raise the exception after retries are exhausted
    with pytest.raises(TencentCloudSDKException, match="persistent error"):
        await client.init()


@pytest.mark.asyncio
async def test_dnspod_client_empty_records(mock_dnspod_client):
    """Test handling empty record lists"""
    client, mock_instance = mock_dnspod_client
    client._domain_id = 12345  # Simulate initialized state

    # Test empty add_records
    await client.add_records([])
    mock_instance.CreateRecordBatch.assert_not_called()

    # Test empty remove_records
    await client.remove_records([])
    mock_instance.DeleteRecordBatch.assert_not_called()


@pytest.mark.asyncio
async def test_dnspod_client_cname_value_processing(mock_dnspod_client):
    """Test CNAME and SRV value processing removes trailing dots"""
    client, mock_instance = mock_dnspod_client
    client._domain_id = 12345

    record_list_response = {
        "RecordList": [
            {
                "Name": "cname-test",
                "RecordId": 1,
                "Type": "CNAME",
                "TTL": 600,
                "Value": "target.example.com.",
            },
            {
                "Name": "a-test",
                "RecordId": 2,
                "Type": "A",
                "TTL": 600,
                "Value": "1.1.1.1",
            },
        ]
    }
    mock_instance.DescribeRecordList.return_value = MockDNSPodResponse(
        record_list_response
    )

    records = await client.list_records()

    # CNAME should have trailing dot removed
    cname_record = next(r for r in records if r.record_type == "CNAME")
    assert cname_record.value == "target.example.com"

    # A record should be unchanged
    a_record = next(r for r in records if r.record_type == "A")
    assert a_record.value == "1.1.1.1"


@pytest.mark.asyncio
async def test_dnspod_client_sleep_after_remove(mock_dnspod_client):
    """Test that remove_records includes sleep delay"""
    client, mock_instance = mock_dnspod_client

    mock_instance.DeleteRecordBatch.return_value = MockDNSPodResponse({})

    with patch("asyncio.sleep") as mock_sleep:
        await client.remove_records([1, 2])

        # Should have called sleep after delete
        mock_sleep.assert_called_once_with(2)
