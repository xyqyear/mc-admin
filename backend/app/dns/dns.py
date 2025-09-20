from typing import NamedTuple

RecordIdT = int | str
RecordIdListT = list[RecordIdT]


class ReturnRecordT(NamedTuple):
    sub_domain: str
    value: str
    record_id: RecordIdT
    record_type: str
    ttl: int


class AddRecordT(NamedTuple):
    sub_domain: str
    value: str
    record_type: str
    ttl: int


RecordListT = list[ReturnRecordT]
AddRecordListT = list[AddRecordT]


class DNSClient:
    """
    abstract class for dns client
    """

    def get_domain(self) -> str: ...

    def is_initialized(self) -> bool: ...

    def has_update_capability(self) -> bool: ...

    async def init(self): ...

    async def list_records(self) -> RecordListT: ...

    async def update_records(self, records: RecordListT): ...

    async def remove_records(self, record_ids: RecordIdListT): ...

    async def add_records(self, records: AddRecordListT): ...
