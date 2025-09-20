"""
Tests for DNS utility functions
"""

import pytest

from app.dns.dns import AddRecordT, ReturnRecordT
from app.dns.utils import RecordDiff, RecordKey, diff_dns_records


def test_record_key():
    """Test RecordKey named tuple"""
    key = RecordKey("test.example.com", "A")
    assert key.sub_domain == "test.example.com"
    assert key.record_type == "A"

    # Test equality
    key2 = RecordKey("test.example.com", "A")
    assert key == key2

    key3 = RecordKey("test.example.com", "AAAA")
    assert key != key3


def test_record_diff():
    """Test RecordDiff named tuple"""
    diff = RecordDiff(records_to_add=[], records_to_remove=[], records_to_update=[])
    assert diff.records_to_add == []
    assert diff.records_to_remove == []
    assert diff.records_to_update == []


def test_diff_dns_records_no_changes():
    """Test diff when old and new records are identical"""
    old_records = [ReturnRecordT("test.example.com", "1.2.3.4", "123", "A", 300)]

    new_records = [AddRecordT("test.example.com", "1.2.3.4", "A", 300)]

    diff = diff_dns_records(old_records, new_records)

    assert len(diff.records_to_add) == 0
    assert len(diff.records_to_remove) == 0
    assert len(diff.records_to_update) == 0


def test_diff_dns_records_add_new():
    """Test diff when adding new records"""
    old_records = []

    new_records = [
        AddRecordT("test.example.com", "1.2.3.4", "A", 300),
        AddRecordT("test2.example.com", "5.6.7.8", "A", 600),
    ]

    diff = diff_dns_records(old_records, new_records)

    assert len(diff.records_to_add) == 2
    assert len(diff.records_to_remove) == 0
    assert len(diff.records_to_update) == 0

    # Check added records
    add_subdomains = {r.sub_domain for r in diff.records_to_add}
    assert "test.example.com" in add_subdomains
    assert "test2.example.com" in add_subdomains


def test_diff_dns_records_remove_old():
    """Test diff when removing old records"""
    old_records = [
        ReturnRecordT("test.example.com", "1.2.3.4", "123", "A", 300),
        ReturnRecordT("test2.example.com", "5.6.7.8", "456", "A", 600),
    ]

    new_records = []

    diff = diff_dns_records(old_records, new_records)

    assert len(diff.records_to_add) == 0
    assert len(diff.records_to_remove) == 2
    assert len(diff.records_to_update) == 0

    # Check removed record IDs
    assert "123" in diff.records_to_remove
    assert "456" in diff.records_to_remove


def test_diff_dns_records_update_existing():
    """Test diff when updating existing records"""
    old_records = [ReturnRecordT("test.example.com", "1.2.3.4", "123", "A", 300)]

    new_records = [
        AddRecordT("test.example.com", "5.6.7.8", "A", 600)  # Different IP and TTL
    ]

    diff = diff_dns_records(old_records, new_records)

    assert len(diff.records_to_add) == 0
    assert len(diff.records_to_remove) == 0
    assert len(diff.records_to_update) == 1

    # Check updated record
    updated = diff.records_to_update[0]
    assert updated.sub_domain == "test.example.com"
    assert updated.value == "5.6.7.8"
    assert updated.record_id == "123"
    assert updated.record_type == "A"
    assert updated.ttl == 600


def test_diff_dns_records_update_value_only():
    """Test diff when updating only the value"""
    old_records = [ReturnRecordT("test.example.com", "1.2.3.4", "123", "A", 300)]

    new_records = [
        AddRecordT("test.example.com", "5.6.7.8", "A", 300)  # Same TTL, different IP
    ]

    diff = diff_dns_records(old_records, new_records)

    assert len(diff.records_to_update) == 1
    updated = diff.records_to_update[0]
    assert updated.value == "5.6.7.8"
    assert updated.ttl == 300


def test_diff_dns_records_update_ttl_only():
    """Test diff when updating only the TTL"""
    old_records = [ReturnRecordT("test.example.com", "1.2.3.4", "123", "A", 300)]

    new_records = [
        AddRecordT("test.example.com", "1.2.3.4", "A", 600)  # Same IP, different TTL
    ]

    diff = diff_dns_records(old_records, new_records)

    assert len(diff.records_to_update) == 1
    updated = diff.records_to_update[0]
    assert updated.value == "1.2.3.4"
    assert updated.ttl == 600


def test_diff_dns_records_mixed_operations():
    """Test diff with mixed add/update/remove operations"""
    old_records = [
        ReturnRecordT("keep.example.com", "1.1.1.1", "111", "A", 300),
        ReturnRecordT("update.example.com", "2.2.2.2", "222", "A", 300),
        ReturnRecordT("remove.example.com", "3.3.3.3", "333", "A", 300),
    ]

    new_records = [
        AddRecordT("keep.example.com", "1.1.1.1", "A", 300),  # No change
        AddRecordT("update.example.com", "2.2.2.9", "A", 600),  # Update value and TTL
        AddRecordT("add.example.com", "4.4.4.4", "A", 300),  # Add new
        # remove.example.com is not in new_records, so it will be removed
    ]

    diff = diff_dns_records(old_records, new_records)

    # Check add operations
    assert len(diff.records_to_add) == 1
    assert diff.records_to_add[0].sub_domain == "add.example.com"

    # Check remove operations
    assert len(diff.records_to_remove) == 1
    assert "333" in diff.records_to_remove

    # Check update operations
    assert len(diff.records_to_update) == 1
    updated = diff.records_to_update[0]
    assert updated.sub_domain == "update.example.com"
    assert updated.value == "2.2.2.9"
    assert updated.ttl == 600
    assert updated.record_id == "222"


def test_diff_dns_records_different_record_types():
    """Test diff with different record types for same subdomain"""
    old_records = [
        ReturnRecordT("test.example.com", "1.2.3.4", "123", "A", 300),
        ReturnRecordT("test.example.com", "test.example.com.", "456", "CNAME", 300),
    ]

    new_records = [
        AddRecordT("test.example.com", "5.6.7.8", "A", 300),  # Update A record
        AddRecordT("test.example.com", "test.example.com.", "CNAME", 300),  # Keep CNAME
    ]

    diff = diff_dns_records(old_records, new_records)

    # Should update A record but not touch CNAME
    assert len(diff.records_to_add) == 0
    assert len(diff.records_to_remove) == 0
    assert len(diff.records_to_update) == 1

    updated = diff.records_to_update[0]
    assert updated.record_type == "A"
    assert updated.value == "5.6.7.8"


def test_diff_dns_records_srv_records():
    """Test diff with SRV records (common in DNS management)"""
    old_records = [
        ReturnRecordT(
            "_minecraft._tcp.server1.mc.example.com",
            "0 5 25565 server1.mc.example.com",
            "123",
            "SRV",
            300,
        )
    ]

    new_records = [
        AddRecordT(
            "_minecraft._tcp.server1.mc.example.com",
            "0 5 25566 server1.mc.example.com",
            "SRV",
            300,
        )  # Different port
    ]

    diff = diff_dns_records(old_records, new_records)

    assert len(diff.records_to_update) == 1
    updated = diff.records_to_update[0]
    assert "25566" in updated.value
