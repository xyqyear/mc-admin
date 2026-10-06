import asyncio

from .types import AddRecordListT, AddRecordT, RecordIdListT, RecordListT
from .utils import RecordDiff


class DNSClient:
    """
    abstract class for dns client
    """

    def get_domain(self) -> str: ...

    def is_initialized(self) -> bool: ...

    async def init(self): ...

    async def close(self) -> None:
        pass

    async def list_records(self) -> RecordListT: ...

    async def list_relevant_records(self, managed_sub_domain: str) -> RecordListT:
        """
        Get only DNS records that are relevant to our Minecraft management.

        This method filters records to only include:
        - Wildcard address records (A/AAAA/CNAME) that end with the managed subdomain
        - SRV records for Minecraft services under the managed subdomain

        Args:
            managed_sub_domain: The subdomain we manage (e.g., "mc" for "*.mc.example.com")

        Returns:
            List of relevant DNS records only
        """
        all_records = await self.list_records()
        relevant_records = RecordListT()

        for record in all_records:
            # Check if this is a wildcard address record we manage
            is_wildcard_address = (
                record.record_type in ("A", "AAAA", "CNAME")
                and record.sub_domain.startswith("*")
                and record.sub_domain.endswith(f".{managed_sub_domain}")
            )

            # Check if this is a Minecraft SRV record we manage
            is_srv_record = (
                record.record_type == "SRV"
                and record.sub_domain.startswith("_minecraft._tcp.")
                and record.sub_domain.endswith(f".{managed_sub_domain}")
            )

            if is_wildcard_address or is_srv_record:
                relevant_records.append(record)

        return relevant_records


    async def apply_diff(self, diff: RecordDiff) -> None:
        limit = asyncio.Semaphore(4)
        conflicting_ids = {record.record_id for record in diff.conflicting_records}
        replacements: dict[str, AddRecordListT] = {}
        for record in diff.records_to_add:
            if any(old.sub_domain == record.sub_domain for old in diff.conflicting_records):
                replacements.setdefault(record.sub_domain, []).append(record)

        async def add(record: AddRecordT) -> None:
            async with limit:
                await self.add_records([record])

        async def remove(record_id) -> None:
            async with limit:
                await self.remove_records([record_id])

        async def update(record) -> None:
            async with limit:
                if self.has_update_capability():
                    await self._update_records_batch([record])
                else:
                    await self.remove_records([record.record_id])
                    await self.add_records([AddRecordT(sub_domain=record.sub_domain, value=record.value, record_type=record.record_type, ttl=record.ttl)])

        async def replace(name: str, records: AddRecordListT) -> None:
            conflicts = [old for old in diff.conflicting_records if old.sub_domain == name]
            if any(old.record_id not in diff.records_to_remove for old in conflicts):
                raise RuntimeError("Conflicting DNS records cannot be removed while inventory is unknown")
            for old in conflicts:
                await remove(old.record_id)
            for record in records:
                await add(record)

        failures: list[Exception] = []
        for writing in (True, False):
            jobs = (
                [
                    *(add(record) for record in diff.records_to_add if record.sub_domain not in replacements),
                    *(replace(name, records) for name, records in replacements.items()),
                    *(update(record) for record in diff.records_to_update),
                ]
                if writing else [remove(record_id) for record_id in diff.records_to_remove if record_id not in conflicting_ids]
            )
            results = await asyncio.gather(*jobs, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception):
                    failures.append(result)
                elif isinstance(result, BaseException):
                    raise result
        if failures:
            raise ExceptionGroup("DNS 部分记录更新失败，请重试", failures)

    def has_update_capability(self) -> bool: ...

    async def _update_records_batch(self, records: RecordListT):
        """
        Update records using provider's batch update API.
        Only called for providers that have update capability.
        Must be implemented by providers that return True for has_update_capability().
        """
        raise NotImplementedError(
            "Provider with update capability must implement _update_records_batch"
        )

    async def remove_records(self, record_ids: RecordIdListT): ...

    async def add_records(self, records: AddRecordListT): ...
