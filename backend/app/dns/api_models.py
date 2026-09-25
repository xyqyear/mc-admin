from typing import Literal

from pydantic import BaseModel, Field


class DNSUpdateResponse(BaseModel):
    """Response for DNS update operations"""

    success: bool
    message: str


class DNSRecord(BaseModel):
    """DNS record information"""

    sub_domain: str
    value: str
    record_id: str | int
    record_type: str
    ttl: int


class DNSRecordsResponse(BaseModel):
    """Response for DNS records list"""

    records: list[DNSRecord]


class RouterRoutesResponse(BaseModel):
    """Response for MC Router routes"""

    routes: dict[str, str]


class DNSRecordDiff(BaseModel):
    """DNS record differences for status checks"""

    records_to_add: list[DNSRecord]
    records_to_remove: list[str]  # Record IDs
    records_to_update: list[DNSRecord]


class RouterDiff(BaseModel):
    """Router route differences for status checks"""

    routes_to_add: dict[str, str]
    routes_to_remove: dict[str, str]
    routes_to_update: dict[str, dict[str, str]]


class DNSStatusResponse(BaseModel):
    """Response for DNS status including diff information"""

    initialized: bool
    dns_diff: DNSRecordDiff | None
    router_diff: RouterDiff | None
    state: Literal["ready", "pending", "degraded", "empty"] = "ready"
    dns_known: bool = True
    router_known: bool = True
    unknown_servers: list[str] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    empty_desired: bool = False


class DNSEnabledResponse(BaseModel):
    """Response for DNS enabled status"""

    enabled: bool
