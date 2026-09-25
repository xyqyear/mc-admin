"""
DNS Management API Router

Provides a simple API endpoint for triggering DNS updates.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import UserRole
from app.auth.schemas import UserPublic
from app.dns.api_models import (
    DNSEnabledResponse,
    DNSRecord,
    DNSRecordDiff,
    DNSStatusResponse,
    DNSUpdateResponse,
    RouterDiff,
)

from ..db.database import get_db
from ..dependencies import RequireRole, get_current_user
from ..dns.manager import get_dns_manager
from ..dynamic_config import get_config

router = APIRouter(prefix="/dns", tags=["dns"])


def _require_dns_enabled() -> None:
    if not get_config().dns.enabled:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DNS manager is disabled in configuration",
        )

@router.post("/update", response_model=DNSUpdateResponse)
async def update_dns(
    _: UserPublic = Depends(RequireRole((UserRole.ADMIN, UserRole.OWNER))),
    db: AsyncSession = Depends(get_db),
) -> DNSUpdateResponse:
    """
    Trigger a DNS and MC Router update.

    This endpoint:
    1. Enumerates active servers from the database
    2. Reads each server's compose to extract its port
    3. Combines with address configuration to generate records
    4. Applies independently observed DNS and MC Router differences

    Requires ADMIN role or higher.
    """
    _require_dns_enabled()
    await get_dns_manager().update(db)

    return DNSUpdateResponse(
        success=True, message="DNS and MC Router updated successfully"
    )

@router.get("/status", response_model=DNSStatusResponse)
async def get_dns_status(
    _: UserPublic = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> DNSStatusResponse:
    """
    Get DNS manager status including current differences between expected and actual state.

    Returns information about whether the DNS manager is initialized, current differences
    in DNS records and router routes.

    Raises:
        HTTPException: If there's an error getting DNS status
    """
    _require_dns_enabled()
    observed = await get_dns_manager().observe(db)
    dns_diff = observed.dns_diff

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
    ) if dns_diff is not None else None

    router_diff = RouterDiff(**observed.router_diff.as_dict()) if observed.router_diff is not None else None

    return DNSStatusResponse(
        initialized=get_dns_manager().is_initialized,
        dns_diff=dns_diff,
        router_diff=router_diff,
        state=observed.state,
        dns_known=observed.dns_known,
        router_known=observed.router_known,
        unknown_servers=list(observed.unknown_servers),
        issues=list(observed.issues),
        empty_desired=observed.empty_desired,
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
    return DNSEnabledResponse(enabled=get_config().dns.enabled)

@router.get("/records", response_model=list[DNSRecord])
async def get_dns_records(
    _: UserPublic = Depends(get_current_user),
) -> list[DNSRecord]:
    """
    Get current DNS records from DNS provider.

    Returns the actual DNS records currently configured in the DNS provider.
    Each record includes subdomain, value, record type, TTL, and record ID.
    """
    _require_dns_enabled()
    records = await get_dns_manager().get_dns_records()

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

@router.get("/routes", response_model=dict[str, str])
async def get_router_routes(
    _: UserPublic = Depends(get_current_user),
) -> dict[str, str]:
    """
    Get current routes from MC Router.

    Returns the actual routes currently configured in the MC Router service.
    Each route maps a server address to a backend server address.
    """
    _require_dns_enabled()
    return await get_dns_manager().get_router_routes()
