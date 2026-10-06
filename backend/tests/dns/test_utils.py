import pytest

from app.dns.types import AddRecordT, ReturnRecordT
from app.dns.utils import RecordDiff, RecordKey, diff_dns_records
from tests.dns.test_reconciliation import StatefulDNS


def test_record_key():
    key = RecordKey("test.example.com", "A")
    assert key.sub_domain == "test.example.com"
    assert key.record_type == "A"

    key2 = RecordKey("test.example.com", "A")
    assert key == key2

    key3 = RecordKey("test.example.com", "AAAA")
    assert key != key3


ADDRESS = ReturnRecordT(sub_domain="*.mc", value="192.0.2.1", record_id="address", record_type="A", ttl=300)
UNCHANGED = AddRecordT(sub_domain="*.mc", value="192.0.2.1", record_type="A", ttl=300)
NEW_ADDRESS = AddRecordT(sub_domain="*.mc", value="192.0.2.2", record_type="A", ttl=600)
UPDATED_ADDRESS = ReturnRecordT(sub_domain="*.mc", value="192.0.2.2", record_id="address", record_type="A", ttl=600)
SRV = AddRecordT(sub_domain="_minecraft._tcp.survival.mc", value="0 5 25565 survival.mc.example.com", record_type="SRV", ttl=300)
OLD = ReturnRecordT(sub_domain="*.old.mc", value="192.0.2.3", record_id="old", record_type="A", ttl=300)
NEW = AddRecordT(sub_domain="*.new.mc", value="192.0.2.4", record_type="A", ttl=300)


@pytest.mark.parametrize(
    "current,target,expected",
    [
        pytest.param([], [], RecordDiff([], [], []), id="empty"),
        pytest.param([], [UNCHANGED, SRV], RecordDiff([UNCHANGED, SRV], [], []), id="add-address-and-srv"),
        pytest.param([ADDRESS, OLD], [], RecordDiff([], ["address", "old"], []), id="remove-two"),
        pytest.param([ADDRESS], [NEW_ADDRESS], RecordDiff([], [], [UPDATED_ADDRESS]), id="update-value-and-ttl-keeps-id"),
        pytest.param([ADDRESS], [UNCHANGED], RecordDiff([], [], []), id="unchanged"),
        pytest.param([ADDRESS, OLD], [NEW_ADDRESS, NEW], RecordDiff([NEW], ["old"], [UPDATED_ADDRESS]), id="mixed"),
        pytest.param([ADDRESS], [], RecordDiff([], ["address"], []), id="empty-target-diff"),
        pytest.param(
            [ADDRESS], [NEW_ADDRESS._replace(ttl=300)],
            RecordDiff([], [], [UPDATED_ADDRESS._replace(ttl=300)]), id="update-value-only",
        ),
        pytest.param(
            [ADDRESS], [NEW_ADDRESS._replace(value="192.0.2.1")],
            RecordDiff([], [], [UPDATED_ADDRESS._replace(value="192.0.2.1")]), id="update-ttl-only",
        ),
        pytest.param(
            [ADDRESS, ReturnRecordT(sub_domain="*.mc", value="target.example.net", record_id="cname", record_type="CNAME", ttl=300)],
            [NEW_ADDRESS, AddRecordT(sub_domain="*.mc", value="target.example.net", record_type="CNAME", ttl=300)],
            RecordDiff([], [], [UPDATED_ADDRESS]), id="same-name-different-types",
        ),
        pytest.param(
            [ReturnRecordT(sub_domain="_minecraft._tcp.survival.mc", value="0 5 25565 survival.mc.example.com", record_id="srv", record_type="SRV", ttl=300)],
            [AddRecordT(sub_domain="_minecraft._tcp.survival.mc", value="0 5 25566 survival.mc.example.com", record_type="SRV", ttl=300)],
            RecordDiff([], [], [ReturnRecordT(sub_domain="_minecraft._tcp.survival.mc", value="0 5 25566 survival.mc.example.com", record_id="srv", record_type="SRV", ttl=300)]), id="srv-value-keeps-id",
        ),
    ],
)
def test_record_differences_are_pure_and_complete(current, target, expected):
    original_current = list(current)
    original_target = list(target)
    assert diff_dns_records(current, target) == expected
    assert current == original_current and target == original_target


async def test_managed_filtering_excludes_unrelated_records_without_writes():
    provider = StatefulDNS()
    unrelated = ReturnRecordT(sub_domain="www", value="192.0.2.5", record_id="unrelated", record_type="A", ttl=300)
    managed_srv = ReturnRecordT(sub_domain="_minecraft._tcp.survival.mc", value="0 5 25565 survival.mc.example.com", record_id="srv", record_type="SRV", ttl=300)
    provider.records = [ADDRESS, unrelated, managed_srv]
    observed = await provider.list_relevant_records("mc")
    assert observed == [ADDRESS, managed_srv]
    assert diff_dns_records(observed, [UNCHANGED]) == RecordDiff([], ["srv"], [])
    assert provider.records == [ADDRESS, unrelated, managed_srv]
    assert provider.calls == []
