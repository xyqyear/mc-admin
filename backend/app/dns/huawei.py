import asyncio
from typing import (
    Any,
    Callable,
    Coroutine,
    Protocol,
    cast,
)

from huaweicloudsdkcore.auth.credentials import BasicCredentials
from huaweicloudsdkcore.exceptions import exceptions
from huaweicloudsdkdns.v2 import (
    BatchDeleteRecordSetWithLineRequest,
    BatchDeleteRecordSetWithLineRequestBody,
    BatchUpdateRecordSet,
    BatchUpdateRecordSetWithLineRequest,
    BatchUpdateRecordSetWithLineRequestBody,
    CreateRecordSetRequest,
    CreateRecordSetRequestBody,
    DnsClient,
    ListPublicZonesRequest,
    ListRecordSetsByZoneRequest,
)
from huaweicloudsdkdns.v2.region.dns_region import DnsRegion

from ..logger import logger
from .dns import DNSClient
from .types import AddRecordListT, RecordIdListT, RecordListT, ReturnRecordT


class ZoneInfoT:
    id: str
    name: str


class ListPublicZonesResponseT:
    zones: list[ZoneInfoT]


class RecordSetT:
    id: str
    name: str
    type: str
    ttl: int
    records: list[str]


class ListRecordSetsByZoneResponseT:
    recordsets: list[RecordSetT]


class HuaweiApiClient(Protocol):
    def list_public_zones(
        self, request: ListPublicZonesRequest
    ) -> ListPublicZonesResponseT: ...

    def list_record_sets_by_zone(
        self, request: ListRecordSetsByZoneRequest
    ) -> ListRecordSetsByZoneResponseT: ...

    def batch_update_record_set_with_line(
        self, request: BatchUpdateRecordSetWithLineRequest
    ) -> None: ...

    def batch_delete_record_set_with_line(
        self, request: BatchDeleteRecordSetWithLineRequest
    ) -> None: ...

    def create_record_set(self, request: CreateRecordSetRequest) -> None: ...


class HuaweiDNSClient(DNSClient):
    def __init__(
        self, domain: str, ak: str, sk: str, region: str | None = None
    ) -> None:
        """ """
        if region is None:
            region = "cn-south-1"
        credentials = BasicCredentials(ak, sk)
        huawei_client = (
            DnsClient.new_builder()
            .with_credentials(credentials)
            .with_region(DnsRegion.value_of(region))
            .build()
        )
        self._huawei_client = cast(HuaweiApiClient, huawei_client)
        self._domain = domain
        self._lock = asyncio.Lock()

    @property
    def lock(self) -> asyncio.Lock:
        return self._lock

    def get_domain(self) -> str:
        return self._domain

    def is_initialized(self) -> bool:
        return hasattr(self, "_zone_id")

    async def _try_request[*Ts, T](
        self,
        request_callable: Callable[[*Ts], T],
        *args: *Ts,
        retry_times: int = 3,
    ) -> T:
        """
        try to call api for retry_times times
        :raises TencentCloudSDKException: if failed to call api for retry_times times
        """
        loop = asyncio.get_running_loop()
        for i in range(retry_times):
            try:
                return await loop.run_in_executor(None, request_callable, *args)
            except exceptions.ClientRequestException as e:
                logger.debug(f"Failed to call {request_callable.__name__} api")
                if i == retry_times - 1:
                    raise e
                await asyncio.sleep(1)

        # not actually reachable
        # just to make pylance happy
        raise Exception("How did you get here?")

    async def init(self):
        request = ListPublicZonesRequest()
        response = await self._try_request(
            self._huawei_client.list_public_zones, request
        )

        for zone_info in response.zones:
            if zone_info.name == self.get_domain() + ".":
                self._zone_id = zone_info.id
                return

        raise Exception(
            f"There is no domain named {self.get_domain()} in this account."
        )

    async def list_records(self):
        request = ListRecordSetsByZoneRequest(zone_id=self._zone_id)
        response = await self._try_request(
            self._huawei_client.list_record_sets_by_zone, request
        )

        sanitized_record_list = RecordListT()
        for record_set in response.recordsets:
            # we extract subdomain from the name
            name = record_set.name
            sub_domain_suffix = f".{self.get_domain()}."
            if not name.endswith(sub_domain_suffix):
                continue
            sub_domain = name[: -len(sub_domain_suffix)]

            value = record_set.records[0]
            record_type = record_set.type
            if record_type in ("SRV", "CNAME") and value.endswith("."):
                value = value[:-1]
            sanitized_record_list.append(
                ReturnRecordT(
                    sub_domain=sub_domain,
                    value=value,
                    record_id=record_set.id,
                    record_type=record_type,
                    ttl=record_set.ttl,
                )
            )

        return sanitized_record_list

    async def _update_records_batch(self, records: RecordListT):
        """Update records using Huawei's batch update API"""
        if not records:
            return

        recordsets = [
            BatchUpdateRecordSet(
                id=record.record_id,
                records=[record.value],
            )
            for record in records
        ]
        request_body = BatchUpdateRecordSetWithLineRequestBody(recordsets=recordsets)
        request = BatchUpdateRecordSetWithLineRequest(
            zone_id=self._zone_id, body=request_body
        )
        await self._try_request(
            self._huawei_client.batch_update_record_set_with_line, request
        )

    def has_update_capability(self) -> bool:
        return True

    async def remove_records(self, record_ids: RecordIdListT):
        if not record_ids:
            return

        request_body = BatchDeleteRecordSetWithLineRequestBody(recordset_ids=record_ids)
        request = BatchDeleteRecordSetWithLineRequest(
            zone_id=self._zone_id, body=request_body
        )
        await self._try_request(
            self._huawei_client.batch_delete_record_set_with_line, request
        )

    async def add_records(self, records: AddRecordListT):
        if not records:
            return

        task_list = list[Coroutine[Any, Any, None]]()
        for record in records:
            request_body = CreateRecordSetRequestBody(
                name=f"{record.sub_domain}.{self.get_domain()}.",
                type=record.record_type,
                ttl=record.ttl,
                records=[record.value],
            )
            request = CreateRecordSetRequest(zone_id=self._zone_id, body=request_body)
            task_list.append(
                self._try_request(self._huawei_client.create_record_set, request)
            )

        await asyncio.gather(*task_list)
