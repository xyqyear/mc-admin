"""
DNS utility functions for record management
"""

from typing import NamedTuple

from .types import AddRecordListT, RecordIdListT, RecordListT, ReturnRecordT


class RecordKey(NamedTuple):
    """Key for identifying unique DNS records"""

    sub_domain: str
    record_type: str


class RecordDiff(NamedTuple):
    """Result of comparing old and new DNS records"""

    records_to_add: AddRecordListT
    records_to_remove: RecordIdListT
    records_to_update: RecordListT


def diff_dns_records(
    old_records: RecordListT, new_records: AddRecordListT
) -> RecordDiff:
    """
    Compare old and new DNS records to determine what needs to be added, removed, or updated.

    Args:
        old_records: Current DNS records
        new_records: Target DNS records

    Returns:
        RecordDiff with lists of records to add, remove, and update
    """
    old_records_dict = {}
    new_records_dict = {}

    for record in old_records:
        old_records_dict[RecordKey(record.sub_domain, record.record_type)] = record

    for record in new_records:
        new_records_dict[RecordKey(record.sub_domain, record.record_type)] = record

    records_to_add = AddRecordListT()
    records_to_remove = RecordIdListT()
    records_to_update = RecordListT()

    # Find records to add or update
    for new_record in new_records:
        key = RecordKey(new_record.sub_domain, new_record.record_type)
        if key in old_records_dict:
            old_record = old_records_dict[key]
            if old_record.value != new_record.value or old_record.ttl != new_record.ttl:
                updated_record = ReturnRecordT(
                    sub_domain=new_record.sub_domain,
                    value=new_record.value,
                    record_id=old_record.record_id,
                    record_type=new_record.record_type,
                    ttl=new_record.ttl,
                )
                records_to_update.append(updated_record)
        else:
            records_to_add.append(new_record)

    # Find records to remove
    for old_record in old_records:
        key = RecordKey(old_record.sub_domain, old_record.record_type)
        if key not in new_records_dict:
            records_to_remove.append(old_record.record_id)

    return RecordDiff(
        records_to_add=records_to_add,
        records_to_remove=records_to_remove,
        records_to_update=records_to_update,
    )
