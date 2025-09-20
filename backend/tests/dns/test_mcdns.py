from typing import NamedTuple

import pytest

from app.dns.dns import (
    AddRecordListT,
    AddRecordT,
    DNSClient,
    RecordIdListT,
    RecordListT,
    ReturnRecordT,
)
from app.dns.mcdns import (
    MCDNS,
    AddressesT,
    AddressInfoT,
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

    async def update_records(self, records: RecordListT):
        for record in records:
            self._records[record.record_id] = AddRecordT(
                sub_domain=record.sub_domain,
                value=record.value,
                record_type=record.record_type,
                ttl=record.ttl,
            )

    async def remove_records(self, record_ids: RecordIdListT):
        for record_id in record_ids:
            del self._records[record_id]

    async def add_records(self, records: AddRecordListT):
        for record in records:
            record_id = self._get_next_id()
            self._records[record_id] = record


class MCDNSPullTestPairT(NamedTuple):
    record_list: AddRecordListT
    expected_addresses: AddressesT
    expected_server_list: list[str]


class MCDNSPushTestPairT(NamedTuple):
    original_record_list: AddRecordListT
    addresses: AddressesT
    server_list: list[str]
    expected_record_list: AddRecordListT


common_test_pairs = [
    MCDNSPullTestPairT(
        record_list=[],
        expected_addresses=AddressesT({}),
        expected_server_list=[],
    ),
    MCDNSPullTestPairT(
        record_list=[
            AddRecordT(
                sub_domain="*.mc",
                value="1.1.1.1",
                record_type="A",
                ttl=600,
            ),
            AddRecordT(
                sub_domain="_minecraft._tcp.vanilla.mc",
                value="0 5 25565 vanilla.mc.example.com",
                record_type="SRV",
                ttl=600,
            ),
        ],
        expected_addresses=AddressesT(
            {
                "*": AddressInfoT(
                    type="A",
                    host="1.1.1.1",
                    port=25565,
                )
            }
        ),
        expected_server_list=["vanilla"],
    ),
    MCDNSPullTestPairT(
        record_list=[
            AddRecordT(
                sub_domain="*.mc",
                value="1.1.1.1",
                record_type="A",
                ttl=600,
            ),
            AddRecordT(
                sub_domain="*.backup.mc",
                value="domain2.com",
                record_type="CNAME",
                ttl=600,
            ),
            AddRecordT(
                sub_domain="*.hk.mc",
                value="domain3.com",
                record_type="CNAME",
                ttl=600,
            ),
            AddRecordT(
                sub_domain="_minecraft._tcp.vanilla.mc",
                value="0 5 11111 vanilla.mc.example.com",
                record_type="SRV",
                ttl=600,
            ),
            AddRecordT(
                sub_domain="_minecraft._tcp.vanilla.backup.mc",
                value="0 5 22222 vanilla.backup.mc.example.com",
                record_type="SRV",
                ttl=600,
            ),
            AddRecordT(
                sub_domain="_minecraft._tcp.vanilla.hk.mc",
                value="0 5 33333 vanilla.hk.mc.example.com",
                record_type="SRV",
                ttl=600,
            ),
            AddRecordT(
                sub_domain="_minecraft._tcp.gtnh.mc",
                value="0 5 11111 gtnh.mc.example.com",
                record_type="SRV",
                ttl=600,
            ),
            AddRecordT(
                sub_domain="_minecraft._tcp.gtnh.backup.mc",
                value="0 5 22222 gtnh.backup.mc.example.com",
                record_type="SRV",
                ttl=600,
            ),
            AddRecordT(
                sub_domain="_minecraft._tcp.gtnh.hk.mc",
                value="0 5 33333 gtnh.hk.mc.example.com",
                record_type="SRV",
                ttl=600,
            ),
        ],
        expected_addresses=AddressesT(
            {
                "*": AddressInfoT(
                    type="A",
                    host="1.1.1.1",
                    port=11111,
                ),
                "backup": AddressInfoT(
                    type="CNAME",
                    host="domain2.com",
                    port=22222,
                ),
                "hk": AddressInfoT(
                    type="CNAME",
                    host="domain3.com",
                    port=33333,
                ),
            }
        ),
        expected_server_list=["vanilla", "gtnh"],
    ),
]


@pytest.mark.parametrize(
    "record_list, expected_addresses, expected_server_list", common_test_pairs
)
async def test_mcdns_pull(
    record_list: AddRecordListT,
    expected_addresses: AddressesT,
    expected_server_list: list[str],
):
    dns_client = DummyDNSClient("example.com")
    await dns_client.add_records(record_list)

    mcdns = MCDNS(dns_client, "mc")

    pull_result = await mcdns.pull()
    if not pull_result:
        assert expected_addresses == {}
        return

    pulled_addresses, pulled_server_list = pull_result

    assert pulled_addresses == expected_addresses
    assert set(pulled_server_list) == set(expected_server_list)


@pytest.mark.asyncio
async def test_mcdns_push_basic():
    """Test basic MCDNS push functionality"""
    dns_client = DummyDNSClient("example.com")
    mcdns = MCDNS(dns_client, "mc")

    addresses = AddressesT(
        {
            "*": AddressInfoT(
                type="A",
                host="1.1.1.1",
                port=25565,
            )
        }
    )
    server_list = ["vanilla"]

    await mcdns.push(addresses, server_list)

    records = await dns_client.list_records()

    # Should have created 2 records: 1 A record and 1 SRV record
    assert len(records) == 2

    # Check A record
    a_records = [r for r in records if r.record_type == "A"]
    assert len(a_records) == 1
    assert a_records[0].sub_domain == "*.mc"
    assert a_records[0].value == "1.1.1.1"

    # Check SRV record
    srv_records = [r for r in records if r.record_type == "SRV"]
    assert len(srv_records) == 1
    assert srv_records[0].sub_domain == "_minecraft._tcp.vanilla.mc"
    assert srv_records[0].value == "0 5 25565 vanilla.mc.example.com"


@pytest.mark.asyncio
async def test_mcdns_diff_update_records():
    """Test the _diff_update_records static method"""
    old_records = [
        ReturnRecordT(
            sub_domain="*.mc",
            value="1.1.1.1",
            record_id=1,
            record_type="A",
            ttl=600,
        ),
    ]

    new_records = [
        AddRecordT(
            sub_domain="*.mc",
            value="2.2.2.2",
            record_type="A",
            ttl=600,
        ),
    ]

    result = MCDNS._diff_update_records(old_records, new_records)

    # Should have one update and no adds/removes
    assert len(result.records_to_add) == 0
    assert len(result.records_to_remove) == 0
    assert len(result.records_to_update) == 1
    assert result.records_to_update[0].value == "2.2.2.2"
