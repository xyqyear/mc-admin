import asyncio
import json
from typing import Callable, Literal, Protocol, TypedDict, cast

from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import (
    TencentCloudSDKException,
)
from tencentcloud.common.profile.client_profile import ClientProfile
from tencentcloud.common.profile.http_profile import HttpProfile
from tencentcloud.dnspod.v20210323 import dnspod_client, models

from .dns import DNSClient
from .types import AddRecordListT, RecordIdListT, RecordListT, ReturnRecordT


class DNSPodSDKRequestT(Protocol):
    def from_json_string(self, jsonStr: str) -> None: ...


class DNSPodSDKResponseT(Protocol):
    def to_json_string(self) -> str: ...


DNSPodSDKCallFuncT = Callable[[DNSPodSDKRequestT], DNSPodSDKResponseT]


class DNSPodRequestInfoT:
    constructor: type[DNSPodSDKRequestT]
    api_call: DNSPodSDKCallFuncT

    def __init__(
        self, constructor: type[DNSPodSDKRequestT], api_call: DNSPodSDKCallFuncT
    ):
        self.constructor = constructor
        self.api_call = api_call


# --- DescribeDomainList ---
class DNSPodDomainInfoT(TypedDict):
    Name: str
    DomainId: int


class DescribeDomainListResponseT(TypedDict):
    DomainList: list[DNSPodDomainInfoT]


# --- DescribeRecordList ---
class DNSPodRecordInfoT(TypedDict):
    Name: str
    RecordId: int
    Type: str
    TTL: int
    Value: str


class DescribeRecordListResponseT(TypedDict):
    RecordList: list[DNSPodRecordInfoT]


# --- CreateRecordBatch ---
class DNSPodAddRecordT(TypedDict):
    SubDomain: str
    RecordType: str
    Value: str
    TTL: int


# --- DNSPOD api request param types ---
class DNSPodDescribeDomainListRequestT(TypedDict):
    Domain: str


class DNSPodDescribeRecordListRequestT(TypedDict):
    Domain: str


class DNSPodModifyRecordBatchRequestT(TypedDict):
    RecordIdList: RecordIdListT
    Change: str
    ChangeTo: str


class DNSPodDeleteRecordBatchRequestT(TypedDict):
    RecordIdList: RecordIdListT


class DNSPodCreateRecordBatchRequestT(TypedDict):
    DomainIdList: list[str]
    RecordList: list[DNSPodAddRecordT]


DNSPodAPIResponseT = DescribeDomainListResponseT | DescribeRecordListResponseT
DNSPodAPIRequestParamsT = (
    DNSPodDescribeDomainListRequestT
    | DNSPodDescribeRecordListRequestT
    | DNSPodModifyRecordBatchRequestT
    | DNSPodDeleteRecordBatchRequestT
    | DNSPodCreateRecordBatchRequestT
)

DNSPodAPIRequestNameT = Literal[
    "DescribeDomainList",
    "DescribeRecordList",
    "ModifyRecordBatch",
    "DeleteRecordBatch",
    "CreateRecordBatch",
]


class DNSPodClient(DNSClient):
    """
    dnspod client
    """

    def __init__(self, domain: str, secret_id: str, secret_key: str):
        self._domain = domain

        cred = credential.Credential(secret_id, secret_key)
        httpProfile = HttpProfile(endpoint="dnspod.tencentcloudapi.com", reqTimeout=10)
        clientProfile = ClientProfile(httpProfile=httpProfile)

        self._client = dnspod_client.DnspodClient(cred, "", clientProfile)

        # don't know how to type client.xxx
        self._request_mapping = {
            "DescribeDomainList": DNSPodRequestInfoT(
                constructor=models.DescribeDomainListRequest,
                api_call=self._client.DescribeDomainList,
            ),
            "DescribeRecordList": DNSPodRequestInfoT(
                constructor=models.DescribeRecordListRequest,
                api_call=self._client.DescribeRecordList,
            ),
            "ModifyRecordBatch": DNSPodRequestInfoT(
                constructor=models.ModifyRecordBatchRequest,
                api_call=self._client.ModifyRecordBatch,
            ),
            "DeleteRecordBatch": DNSPodRequestInfoT(
                constructor=models.DeleteRecordBatchRequest,
                api_call=self._client.DeleteRecordBatch,
            ),
            "CreateRecordBatch": DNSPodRequestInfoT(
                constructor=models.CreateRecordBatchRequest,
                api_call=self._client.CreateRecordBatch,
            ),
        }

        self._domain_id: int

    def get_domain(self) -> str:
        return self._domain

    def is_initialized(self) -> bool:
        return hasattr(self, "_domain_id")

    async def init(self):
        """
        This function must be called since some apis need domain id

        :raises Exception: if there is no domain in this account or there is no domain named self._domain
        :raises Exception: if failed to call DescribeDomainList api
        """
        response = await self._try_request(
            "DescribeDomainList",
            {
                "Domain": self._domain,
            },
        )
        response = cast(DescribeDomainListResponseT, response)

        domain_list = response["DomainList"]
        if len(domain_list) == 0:
            raise Exception("There is no domain in this account.")

        for domain in domain_list:
            if domain["Name"] == self._domain:
                self._domain_id = domain["DomainId"]
                return

        raise Exception(f"There is no domain named {self._domain} in this account.")

    async def _send_request(
        self, request_name: DNSPodAPIRequestNameT, params: DNSPodAPIRequestParamsT
    ) -> DNSPodAPIResponseT:
        request_info = self._request_mapping[request_name]

        req = request_info.constructor()
        req.from_json_string(json.dumps(params))

        loop = asyncio.get_running_loop()
        response_object = await loop.run_in_executor(None, request_info.api_call, req)

        response_json = response_object.to_json_string()
        response = json.loads(response_json)

        return response

    async def _try_request(
        self,
        request_name: DNSPodAPIRequestNameT,
        params: DNSPodAPIRequestParamsT,
        retry_times: int = 3,
    ) -> DNSPodAPIResponseT:
        """
        try to call api for retry_times times
        :raises TencentCloudSDKException: if failed to call api for retry_times times
        """
        for i in range(retry_times):
            try:
                return await self._send_request(request_name, params)
            except TencentCloudSDKException as e:
                if i == retry_times - 1:
                    raise e
                await asyncio.sleep(1)

        # not actually reachable
        # just to make pylance happy
        raise Exception(f"Failed to call {request_name} api")

    async def list_records(self) -> RecordListT:
        """
        list all records in this domain
        :raises TencentCloudSDKException: if failed to call DescribeRecordList api
        """
        response = await self._try_request(
            "DescribeRecordList",
            {
                "Domain": self._domain,
            },
        )
        response = cast(DescribeRecordListResponseT, response)
        record_list = response["RecordList"]

        sanitized_record_list = RecordListT()
        for record in record_list:
            value = record["Value"]
            if record["Type"] in ("SRV", "CNAME") and value.endswith("."):
                value = value[:-1]
            sanitized_record_list.append(
                ReturnRecordT(
                    sub_domain=record["Name"],
                    value=value,
                    record_id=record["RecordId"],
                    record_type=record["Type"],
                    ttl=record["TTL"],
                )
            )

        return sanitized_record_list

    def has_update_capability(self) -> bool:
        return False

    async def remove_records(self, record_ids: RecordIdListT):
        """
        remove records
        :raises TencentCloudSDKException: if failed to call DeleteRecordBatch api
        """
        if not record_ids:
            return

        await self._try_request(
            "DeleteRecordBatch",
            {
                "RecordIdList": record_ids,
            },
        )
        # add a delay before adding any records
        await asyncio.sleep(2)

    async def add_records(self, records: AddRecordListT):
        """
        add records
        :raises TencentCloudSDKException: if failed to call CreateRecordBatch api
        """
        if not records:
            return

        dnspod_add_records = [
            DNSPodAddRecordT(
                SubDomain=record.sub_domain,
                RecordType=record.record_type,
                Value=record.value,
                TTL=record.ttl,
            )
            for record in records
        ]

        await self._try_request(
            "CreateRecordBatch",
            {
                "DomainIdList": [str(self._domain_id)],
                "RecordList": dnspod_add_records,
            },
        )
