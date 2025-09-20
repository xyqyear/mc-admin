from .types import AddRecordListT, AddRecordT, RecordIdListT, RecordListT
from .utils import diff_dns_records


class DNSClient:
    """
    abstract class for dns client
    """

    def get_domain(self) -> str: ...

    def is_initialized(self) -> bool: ...

    async def init(self): ...

    async def list_records(self) -> RecordListT: ...

    async def update_records(self, target_records: AddRecordListT):
        """
        Update DNS records to match target state by comparing current and target records.

        This is the common implementation that works for both providers.
        Individual providers can override this if they need custom behavior.

        Args:
            target_records: Target state for DNS records
        """
        if not target_records:
            return

        # Get current records from DNS provider
        current_records = await self.list_records()

        # Calculate differences
        diff = diff_dns_records(current_records, target_records)

        if diff.records_to_remove:
            await self.remove_records(diff.records_to_remove)

        if diff.records_to_add:
            await self.add_records(diff.records_to_add)

        if not diff.records_to_update:
            return

        if self.has_update_capability():
            await self._update_records_batch(diff.records_to_update)
        else:
            update_ids = [record.record_id for record in diff.records_to_update]
            await self.remove_records(update_ids)

            # Convert update records back to add records
            add_records = [
                AddRecordT(
                    sub_domain=record.sub_domain,
                    value=record.value,
                    record_type=record.record_type,
                    ttl=record.ttl,
                )
                for record in diff.records_to_update
            ]
            await self.add_records(add_records)

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
