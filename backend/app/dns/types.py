"""
DNS type definitions for the DNS module
"""

from typing import NamedTuple

# Basic types
RecordIdT = int | str
RecordIdListT = list[RecordIdT]


class ReturnRecordT(NamedTuple):
    """DNS record returned from DNS provider"""

    sub_domain: str
    value: str
    record_id: RecordIdT
    record_type: str
    ttl: int


class AddRecordT(NamedTuple):
    """DNS record to be added to DNS provider"""

    sub_domain: str
    value: str
    record_type: str
    ttl: int


# List types
RecordListT = list[ReturnRecordT]
AddRecordListT = list[AddRecordT]
