import asyncio

from ..operations.finalization import finalize
from .types import AddRecordListT, AddRecordT, RecordIdListT, RecordListT
from .utils import RecordDiff, diff_dns_records


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

    async def update_records(
        self, target_records: AddRecordListT, managed_sub_domain: str | None = None
    ):
        """
        Update DNS records to match target state by comparing current and target records.

        This is the common implementation that works for both providers.
        Individual providers can override this if they need custom behavior.

        Args:
            target_records: Target state for DNS records
            managed_sub_domain: The subdomain we manage. If provided, only relevant records will be compared.
        """
        if not target_records:
            return

        # Get current records from DNS provider
        # Use filtered records if managed_sub_domain is provided for safety
        if managed_sub_domain:
            current_records = await self.list_relevant_records(managed_sub_domain)
        else:
            current_records = await self.list_records()

        # Calculate differences
        diff = diff_dns_records(current_records, target_records)

        await finalize(self.apply_diff(diff))

    async def apply_diff(self, diff: RecordDiff) -> None:
        limit = asyncio.Semaphore(4)

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
                    await self.add_records([AddRecordT(record.sub_domain, record.value, record.record_type, record.ttl)])

        failures: list[Exception] = []
        for writing in (True, False):
            jobs = (
                [*(add(record) for record in diff.records_to_add), *(update(record) for record in diff.records_to_update)]
                if writing else [remove(record_id) for record_id in diff.records_to_remove]
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

    async def get_records_diff(
        self, target_records: AddRecordListT, managed_sub_domain: str | None = None
    ):
        """
        Get differences between current DNS records and target records without applying changes.

        This method provides a preview of what changes would be made during an update
        without actually performing the update operations.

        Args:
            target_records: Target state for DNS records
            managed_sub_domain: The subdomain we manage. If provided, only relevant records will be compared.

        Returns:
            RecordDiff with lists of records that would be added, removed, and updated
        """
        # Get current records from DNS provider
        # Use filtered records if managed_sub_domain is provided for safety
        if managed_sub_domain:
            current_records = await self.list_relevant_records(managed_sub_domain)
        else:
            current_records = await self.list_records()

        # Calculate and return differences without applying
        # Even if target_records is empty, we still need to check for removals
        return diff_dns_records(current_records, target_records)
