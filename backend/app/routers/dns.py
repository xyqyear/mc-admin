"""
DNS Management API Router

Provides a simple API endpoint for triggering DNS updates.
"""

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..dependencies import RequireRole, get_current_user
from ..dns.manager import simple_dns_manager
from ..dynamic_config import config
from ..logger import logger
from ..models import UserPublic, UserRole

router = APIRouter(prefix="/dns", tags=["dns"])


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

    records: List[DNSRecord]


class RouterRoutesResponse(BaseModel):
    """Response for MC Router routes"""

    routes: Dict[str, str]


class DNSRecordDiff(BaseModel):
    """DNS record differences for status checks"""

    records_to_add: List[DNSRecord]
    records_to_remove: List[str]  # Record IDs
    records_to_update: List[DNSRecord]


class RouterDiff(BaseModel):
    """Router route differences for status checks"""

    routes_to_add: Dict[str, str]
    routes_to_remove: Dict[str, str]
    routes_to_update: Dict[str, Dict[str, str]]


class DNSStatusResponse(BaseModel):
    """Response for DNS status including diff information"""

    initialized: bool
    dns_diff: DNSRecordDiff | None
    router_diff: RouterDiff | None


class DNSEnabledResponse(BaseModel):
    """Response for DNS enabled status"""

    enabled: bool


async def _ensure_dns_manager_initialized() -> None:
    """
    Ensure DNS manager is initialized, attempting initialization if needed.

    Raises:
        HTTPException: If initialization fails
    """
    if not config.dns.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DNS manager is disabled in configuration",
        )
    if not simple_dns_manager.is_initialized:
        logger.warning("DNS manager not initialized, attempting to initialize...")
        try:
            await simple_dns_manager.initialize()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Failed to initialize DNS manager: {str(e)}",
            ) from e


@router.post("/update", response_model=DNSUpdateResponse)
async def update_dns(
    _: UserPublic = Depends(RequireRole((UserRole.ADMIN, UserRole.OWNER))),
) -> DNSUpdateResponse:
    """
    Trigger a DNS and MC Router update.

    This endpoint:
    1. Gets current server list from DockerMCManager
    2. Combines with configuration to generate DNS records and routes
    3. Updates DNS provider and MC Router with complete lists

    Requires ADMIN role or higher.
    """
    await _ensure_dns_manager_initialized()
    await simple_dns_manager.update()

    return DNSUpdateResponse(
        success=True, message="DNS and MC Router updated successfully"
    )


@router.get("/status", response_model=DNSStatusResponse)
async def get_dns_status(
    _: UserPublic = Depends(get_current_user),
) -> DNSStatusResponse:
    """
    Get DNS manager status including current differences between expected and actual state.

    Returns information about whether the DNS manager is initialized, current differences
    in DNS records and router routes.

    Raises:
        HTTPException: If there's an error getting DNS status
    """
    await _ensure_dns_manager_initialized()
    dns_diff, router_diff = await simple_dns_manager.get_current_diff()

    # Convert DNS diff to response format
    dns_diff = DNSRecordDiff(
        records_to_add=[
            DNSRecord(
                sub_domain=record.sub_domain,
                value=record.value,
                record_id="",  # Not applicable for records to add
                record_type=record.record_type,
                ttl=record.ttl,
            )
            for record in dns_diff.records_to_add
        ],
        records_to_remove=[str(record_id) for record_id in dns_diff.records_to_remove],
        records_to_update=[
            DNSRecord(
                sub_domain=record.sub_domain,
                value=record.value,
                record_id=str(record.record_id),
                record_type=record.record_type,
                ttl=record.ttl,
            )
            for record in dns_diff.records_to_update
        ],
    )

    router_diff = RouterDiff(**router_diff)

    return DNSStatusResponse(
        initialized=simple_dns_manager.is_initialized,
        dns_diff=dns_diff,
        router_diff=router_diff,
    )


@router.get("/enabled", response_model=DNSEnabledResponse)
async def get_dns_enabled(
    _: UserPublic = Depends(get_current_user),
) -> DNSEnabledResponse:
    """
    Get DNS manager enabled status from configuration.

    Returns whether the DNS manager is enabled in the dynamic configuration.
    This is separate from the initialization status.
    """
    return DNSEnabledResponse(enabled=config.dns.enabled)


@router.get("/records", response_model=List[DNSRecord])
async def get_dns_records(
    _: UserPublic = Depends(get_current_user),
) -> List[DNSRecord]:
    """
    Get current DNS records from DNS provider.

    Returns the actual DNS records currently configured in the DNS provider.
    Each record includes subdomain, value, record type, TTL, and record ID.
    """
    await _ensure_dns_manager_initialized()
    assert simple_dns_manager._dns_client is not None

    # Get current DNS records from the provider
    # Only get records relevant to our Minecraft management
    dns_config = config.dns
    records = await simple_dns_manager._dns_client.list_relevant_records(
        dns_config.managed_sub_domain
    )

    # Convert records to DNSRecord models for JSON response
    return [
        DNSRecord(
            sub_domain=record.sub_domain,
            value=record.value,
            record_id=record.record_id,
            record_type=record.record_type,
            ttl=record.ttl,
        )
        for record in records
    ]


@router.get("/routes", response_model=Dict[str, str])
async def get_router_routes(
    _: UserPublic = Depends(get_current_user),
) -> Dict[str, str]:
    """
    Get current routes from MC Router.

    Returns the actual routes currently configured in the MC Router service.
    Each route maps a server address to a backend server address.
    """
    await _ensure_dns_manager_initialized()
    assert simple_dns_manager._mc_router_client is not None

    # Get current routes from MC Router
    return await simple_dns_manager._mc_router_client.get_routes()
