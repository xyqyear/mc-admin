"""
DNS Management API Router

Provides a simple API endpoint for triggering DNS updates.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from ..dependencies import RequireRole, get_current_user
from ..dns.manager import simple_dns_manager
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
    try:
        if not simple_dns_manager.is_initialized:
            logger.warning("DNS manager not initialized, attempting to initialize...")
            await simple_dns_manager.initialize()

        await simple_dns_manager.update()

        return DNSUpdateResponse(
            success=True, message="DNS and MC Router updated successfully"
        )

    except Exception as e:
        error_msg = f"Failed to update DNS: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        ) from e


@router.get("/status")
async def get_dns_status(_: UserPublic = Depends(get_current_user)) -> dict:
    """
    Get DNS manager status.

    Returns information about whether the DNS manager is initialized
    and available for updates.
    """
    return {
        "initialized": simple_dns_manager.is_initialized,
        "enabled": True,  # We'll check config when needed
    }


@router.get("/records", response_model=List[DNSRecord])
async def get_dns_records(
    _: UserPublic = Depends(get_current_user),
) -> List[DNSRecord]:
    """
    Get current DNS records from DNS provider.

    Returns the actual DNS records currently configured in the DNS provider.
    Each record includes subdomain, value, record type, TTL, and record ID.
    """
    try:
        if not simple_dns_manager.is_initialized:
            logger.warning("DNS manager not initialized, attempting to initialize...")
            await simple_dns_manager.initialize()

        # Check if DNS client is available
        if not simple_dns_manager._dns_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="DNS client not initialized",
            )

        # Get current DNS records from the provider
        # Only get records relevant to our Minecraft management
        from ..dynamic_config import config
        dns_config = config.dns
        records = await simple_dns_manager._dns_client.list_relevant_records(dns_config.managed_sub_domain)

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
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        error_msg = f"Failed to get DNS records: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        ) from e


@router.get("/routes", response_model=Dict[str, str])
async def get_router_routes(
    _: UserPublic = Depends(get_current_user),
) -> Dict[str, str]:
    """
    Get current routes from MC Router.

    Returns the actual routes currently configured in the MC Router service.
    Each route maps a server address to a backend server address.
    """
    try:
        if not simple_dns_manager.is_initialized:
            logger.warning("DNS manager not initialized, attempting to initialize...")
            await simple_dns_manager.initialize()

        # Check if MC Router client is available
        if not simple_dns_manager._mc_router_client:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="MC Router client not initialized",
            )

        # Get current routes from MC Router
        routes = await simple_dns_manager._mc_router_client.get_routes()

        return routes
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except Exception as e:
        error_msg = f"Failed to get router routes: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        ) from e


@router.post("/refresh", response_model=DNSUpdateResponse)
async def refresh_dns_manager(
    _: UserPublic = Depends(RequireRole((UserRole.ADMIN, UserRole.OWNER))),
) -> DNSUpdateResponse:
    """
    Refresh DNS manager by reinitializing with current configuration.

    This endpoint will reinitialize the DNS manager with the latest configuration
    from the dynamic config system, which is useful when DNS settings have been
    updated and need to be applied without restarting the application.

    Requires ADMIN role or higher.
    """
    try:
        logger.info("Refreshing DNS manager with current configuration...")
        await simple_dns_manager.initialize()

        return DNSUpdateResponse(
            success=True, message="DNS manager refreshed successfully"
        )

    except Exception as e:
        error_msg = f"Failed to refresh DNS manager: {str(e)}"
        logger.error(error_msg)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=error_msg
        ) from e
