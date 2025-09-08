import asyncio

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..config import settings
from ..dependencies import get_current_user
from ..system.resources import (
    get_cpu_load,
    get_cpu_percent,
    get_disk_info,
    get_memory_info,
)

router = APIRouter(
    prefix="/system",
    tags=["system"],
)


class ServerInfo(BaseModel):
    cpuLoad1Min: float
    cpuLoad5Min: float
    cpuLoad15Min: float
    ramUsedGB: float
    ramTotalGB: float


class DiskUsageInfo(BaseModel):
    diskUsedGB: float
    diskTotalGB: float
    diskAvailableGB: float


class CpuPercent(BaseModel):
    cpuPercentage: float


class HealthCheck(BaseModel):
    status: str


@router.get(
    "/info", dependencies=[Depends(get_current_user)], response_model=ServerInfo
)
async def get_server_info():
    (
        cpu_load,
        memory_info,
    ) = await asyncio.gather(
        get_cpu_load(),
        get_memory_info(),
    )

    return ServerInfo(
        cpuLoad1Min=cpu_load.one_minute,
        cpuLoad5Min=cpu_load.five_minutes,
        cpuLoad15Min=cpu_load.fifteen_minutes,
        ramUsedGB=memory_info.used / 1024**3,
        ramTotalGB=memory_info.total / 1024**3,
    )


@router.get(
    "/disk-usage", dependencies=[Depends(get_current_user)], response_model=DiskUsageInfo
)
async def get_system_disk_usage():
    """Get system disk usage information for server path"""
    disk_info = await get_disk_info(settings.server_path)
    
    return DiskUsageInfo(
        diskUsedGB=disk_info.used / 1024**3,
        diskTotalGB=disk_info.total / 1024**3,
        diskAvailableGB=(disk_info.total - disk_info.used) / 1024**3,
    )


@router.get(
    "/cpu_percent", dependencies=[Depends(get_current_user)], response_model=CpuPercent
)
async def get_cpu_percent_endpoint():
    """Get system CPU percentage (takes 1-2 seconds to calculate)"""
    cpu_percent = await get_cpu_percent()

    return CpuPercent(
        cpuPercentage=cpu_percent,
    )


@router.get("/health", response_model=HealthCheck)
async def get_health():
    """Simple healthcheck endpoint for Docker"""
    return HealthCheck(status="healthy")
