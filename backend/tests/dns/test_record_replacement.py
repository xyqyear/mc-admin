import pytest

from app.dns.dns import DNSClient
from app.dns.types import AddRecordT, ReturnRecordT
from app.dns.utils import diff_dns_records


class ConflictProvider(DNSClient):
    def __init__(self, records):
        self.records = {record.record_id: record for record in records}
        self.fail_delete = False
        self.fail_create = False

    async def remove_records(self, record_ids):
        if self.fail_delete:
            raise RuntimeError("deletion failed")
        for identity in record_ids:
            self.records.pop(identity)

    async def add_records(self, records):
        for record in records:
            if record.sub_domain == "*.primary.mc" and self.fail_create:
                raise RuntimeError("creation failed")
            for old in self.records.values():
                if old.sub_domain == record.sub_domain and "CNAME" in (old.record_type, record.record_type):
                    raise RuntimeError("conflicting records")
            identity = record.sub_domain + record.record_type
            self.records[identity] = ReturnRecordT(record.sub_domain, record.value, identity, record.record_type, record.ttl)


@pytest.mark.parametrize("before,after", [("A", "CNAME"), ("AAAA", "CNAME"), ("CNAME", "A"), ("CNAME", "AAAA")])
async def test_conflicting_address_type_converges(before, after):
    original = ReturnRecordT("*.primary.mc", "old", "old-id", before, 600)
    retained = ReturnRecordT("*.stable.mc", "stable", "stable-id", "A", 600)
    target = [AddRecordT(sub_domain="*.primary.mc", value="new", record_type=after, ttl=600), AddRecordT(sub_domain="*.stable.mc", value="stable", record_type="A", ttl=600)]
    provider = ConflictProvider([original, retained])
    await provider.apply_diff(diff_dns_records(list(provider.records.values()), target))
    assert {(r.sub_domain, r.record_type, r.value) for r in provider.records.values()} == {
        ("*.primary.mc", after, "new"), ("*.stable.mc", "A", "stable")
    }
    assert provider.records["stable-id"] == retained


@pytest.mark.parametrize("failure", ["delete", "create", "unknown_inventory"])
async def test_failed_replacement_preserves_failure_and_unrelated_progress(failure):
    original = ReturnRecordT("*.primary.mc", "192.0.2.1", "old-id", "A", 600)
    provider = ConflictProvider([original])
    target = [AddRecordT(sub_domain="*.primary.mc", value="target.example.com", record_type="CNAME", ttl=600), AddRecordT(sub_domain="*.other.mc", value="192.0.2.2", record_type="A", ttl=600)]
    diff = diff_dns_records([original], target)
    provider.fail_delete = failure == "delete"
    provider.fail_create = failure == "create"
    if failure == "unknown_inventory":
        diff = diff._replace(records_to_remove=[])
    with pytest.raises(ExceptionGroup):
        await provider.apply_diff(diff)
    assert "*.other.mcA" in provider.records
    assert ("old-id" in provider.records) == (failure != "create")
    assert "*.primary.mcCNAME" not in provider.records
    provider.fail_delete = provider.fail_create = False
    await provider.apply_diff(diff_dns_records(list(provider.records.values()), target))
    assert len(provider.records) == 2
    assert provider.records["*.primary.mcCNAME"].value == "target.example.com"


async def test_cname_replacement_can_create_both_address_families():
    original = ReturnRecordT("*.primary.mc", "target.example.com", "old-id", "CNAME", 600)
    provider = ConflictProvider([original])
    target = [AddRecordT(sub_domain="*.primary.mc", value="192.0.2.1", record_type="A", ttl=600), AddRecordT(sub_domain="*.primary.mc", value="2001:db8::1", record_type="AAAA", ttl=600)]
    await provider.apply_diff(diff_dns_records([original], target))
    assert {r.record_type for r in provider.records.values()} == {"A", "AAAA"}
