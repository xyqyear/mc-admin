import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)

from app.dns.dns import AddRecordT
from app.dns.dnspod import DNSPodClient
from app.dns.utils import diff_dns_records


class MockDNSPodResponse:
    def __init__(self, response_data: dict):
        self._response_data = response_data

    def to_json_string(self) -> str:
        return json.dumps(self._response_data)


@pytest.fixture
def mock_dnspod_client():
    with patch("app.dns.dnspod.dnspod_client.DnspodClient") as mock_client:
        mock_instance = MagicMock()
        mock_client.return_value = mock_instance

        client = DNSPodClient("example.com", "test_id", "test_key")
        yield client, mock_instance


@pytest.mark.asyncio
async def test_dnspod_client_initialization():
    with patch("app.dns.dnspod.dnspod_client.DnspodClient"):
        client = DNSPodClient("example.com", "test_id", "test_key")

        assert client.get_domain() == "example.com"
        assert not client.is_initialized()


@pytest.mark.asyncio
async def test_dnspod_client_init_success(mock_dnspod_client):
    client, mock_instance = mock_dnspod_client

    domain_list_response = {"DomainList": [{"Name": "example.com", "DomainId": 12345}]}
    mock_instance.DescribeDomainList.return_value = MockDNSPodResponse(
        domain_list_response
    )

    await client.init()

    assert client.is_initialized()
    assert client._domain_id == 12345


@pytest.mark.asyncio
async def test_dnspod_client_init_no_domains(mock_dnspod_client):
    client, mock_instance = mock_dnspod_client

    domain_list_response = {"DomainList": []}
    mock_instance.DescribeDomainList.return_value = MockDNSPodResponse(
        domain_list_response
    )

    with pytest.raises(Exception, match="There is no domain in this account"):
        await client.init()


@pytest.mark.asyncio
async def test_dnspod_client_init_domain_not_found(mock_dnspod_client):
    client, mock_instance = mock_dnspod_client

    domain_list_response = {"DomainList": [{"Name": "other.com", "DomainId": 54321}]}
    mock_instance.DescribeDomainList.return_value = MockDNSPodResponse(
        domain_list_response
    )

    with pytest.raises(Exception, match="There is no domain named example.com"):
        await client.init()


@pytest.mark.asyncio
async def test_dnspod_client_list_records(mock_dnspod_client):
    client, mock_instance = mock_dnspod_client
    client._domain_id = 12345

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

    # SRV record value strips trailing dot.
    assert records[1].value == "0 5 25565 target.example.com"


@pytest.mark.asyncio
async def test_dnspod_client_add_records(mock_dnspod_client):
    client, mock_instance = mock_dnspod_client
    client._domain_id = 12345

    mock_instance.CreateRecordBatch.return_value = MockDNSPodResponse({})

    records = [
        AddRecordT(sub_domain="test", value="1.1.1.1", record_type="A", ttl=600),
        AddRecordT(sub_domain="_minecraft._tcp.survival", value="0 5 25566 target.example.com", record_type="SRV", ttl=300),
    ]

    await client.add_records(records)

    requests = mock_instance.CreateRecordBatch.call_args_list
    assert len(requests) == 1
    assert json.loads(requests[0].args[0].to_json_string()) == {
        "DomainIdList": ["12345"],
        "RecordList": [
            {"SubDomain": "test", "RecordType": "A", "Value": "1.1.1.1", "TTL": 600, "RecordLine": None, "RecordLineId": None, "MX": None},
            {"SubDomain": "_minecraft._tcp.survival", "RecordType": "SRV", "Value": "0 5 25566 target.example.com", "TTL": 300, "RecordLine": None, "RecordLineId": None, "MX": None},
        ],
    }


@pytest.mark.asyncio
async def test_dnspod_client_remove_records(mock_dnspod_client):
    client, mock_instance = mock_dnspod_client

    mock_instance.DeleteRecordBatch.return_value = MockDNSPodResponse({})

    record_ids = [1, 2, 3]

    await client.remove_records(record_ids)

    requests = mock_instance.DeleteRecordBatch.call_args_list
    assert len(requests) == 1
    assert json.loads(requests[0].args[0].to_json_string()) == {"RecordIdList": [1, 2, 3]}


@pytest.mark.asyncio
async def test_dnspod_client_retry_logic(mock_dnspod_client):
    client, mock_instance = mock_dnspod_client

    domain_list_response = {"DomainList": [{"Name": "example.com", "DomainId": 12345}]}

    mock_instance.DescribeDomainList.side_effect = [
        TencentCloudSDKException("error1"),
        TencentCloudSDKException("error2"),
        MockDNSPodResponse(domain_list_response),
    ]

    await client.init()
    assert client.is_initialized()

    assert mock_instance.DescribeDomainList.call_count == 3


@pytest.mark.asyncio
async def test_dnspod_client_retry_exhausted(mock_dnspod_client):
    client, mock_instance = mock_dnspod_client

    error = TencentCloudSDKException("persistent error")
    mock_instance.DescribeDomainList.side_effect = error

    with pytest.raises(TencentCloudSDKException, match="persistent error"):
        await client.init()


@pytest.mark.asyncio
async def test_dnspod_client_empty_records(mock_dnspod_client):
    client, mock_instance = mock_dnspod_client
    client._domain_id = 12345

    await client.add_records([])
    mock_instance.CreateRecordBatch.assert_not_called()

    await client.remove_records([])
    mock_instance.DeleteRecordBatch.assert_not_called()


@pytest.mark.asyncio
async def test_dnspod_client_cname_value_processing(mock_dnspod_client):
    """CNAME and SRV values get trailing dot stripped; A record passes through."""
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

    cname_record = next(r for r in records if r.record_type == "CNAME")
    assert cname_record.value == "target.example.com"

    a_record = next(r for r in records if r.record_type == "A")
    assert a_record.value == "1.1.1.1"


@pytest.mark.asyncio
async def test_dnspod_client_sleep_after_remove(mock_dnspod_client):
    client, mock_instance = mock_dnspod_client

    mock_instance.DeleteRecordBatch.return_value = MockDNSPodResponse({})

    with patch("asyncio.sleep") as mock_sleep:
        await client.remove_records([1, 2])

        mock_sleep.assert_called_once_with(2)


async def test_changed_record_replacement_waits_for_delete_propagation(mock_dnspod_client, monkeypatch):
    client, sdk = mock_dnspod_client
    client._domain_id = 12345
    sdk.DescribeRecordList.return_value = MockDNSPodResponse({"RecordList": [
        {"Name": "*.mc", "RecordId": 17, "Type": "A", "TTL": 120, "Value": "192.0.2.1"},
    ]})
    sdk.DeleteRecordBatch.return_value = MockDNSPodResponse({})
    sdk.CreateRecordBatch.return_value = MockDNSPodResponse({})
    propagation_started = asyncio.Event()
    release_propagation = asyncio.Event()

    async def propagation_delay(seconds):
        assert seconds == 2
        propagation_started.set()
        await release_propagation.wait()

    monkeypatch.setattr("app.dns.dnspod.asyncio.sleep", propagation_delay)
    current = await client.list_records()
    target = [AddRecordT(sub_domain="*.mc", value="192.0.2.2", record_type="A", ttl=600)]
    writing = asyncio.create_task(client.apply_diff(diff_dns_records(current, target)))
    try:
        await asyncio.wait_for(propagation_started.wait(), 2)
        assert not writing.done()
        sdk.CreateRecordBatch.assert_not_called()
        assert json.loads(sdk.DeleteRecordBatch.call_args.args[0].to_json_string()) == {"RecordIdList": [17]}
        release_propagation.set()
        await asyncio.wait_for(writing, 2)
        assert json.loads(sdk.CreateRecordBatch.call_args.args[0].to_json_string()) == {
            "DomainIdList": ["12345"],
            "RecordList": [{"SubDomain": "*.mc", "RecordType": "A", "Value": "192.0.2.2", "TTL": 600, "RecordLine": None, "RecordLineId": None, "MX": None}],
        }
        assert sdk.DeleteRecordBatch.call_count == sdk.CreateRecordBatch.call_count == 1
    finally:
        release_propagation.set()
        await asyncio.gather(writing, return_exceptions=True)
