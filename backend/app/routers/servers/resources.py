import asyncio
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...config import settings
from ...dependencies import get_current_user
from ...minecraft import DockerMCManager, MCServerStatus
from ...models import UserPublic

router = APIRouter(
    prefix="/servers",
    tags=["server-resources"],
)

# Initialize the Docker MC Manager
mc_manager = DockerMCManager(settings.server_path)


class ServerCpuPercent(BaseModel):
    cpuPercentage: float


class ServerMemory(BaseModel):
    memoryUsageBytes: int


class ServerIOStats(BaseModel):
    # Disk I/O statistics
    diskReadBytes: int
    diskWriteBytes: int
    # Network I/O statistics
    networkReceiveBytes: int
    networkSendBytes: int


class ServerDiskUsage(BaseModel):
    # Disk usage and space information
    diskUsageBytes: int
    diskTotalBytes: int
    diskAvailableBytes: int


@router.get("/{server_id}/cpu_percent", response_model=ServerCpuPercent)
async def get_server_cpu_percent(
    server_id: str, _: UserPublic = Depends(get_current_user)
):
    """Get CPU percentage for a specific server (available when running/starting/healthy)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is in a state where CPU monitoring is available
        status = await instance.get_status()
        if status not in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' CPU monitoring not available (status: {status})",
            )

        # Get CPU percentage
        cpu_percentage = await instance.get_cpu_percentage()

        return ServerCpuPercent(
            cpuPercentage=cpu_percentage,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server CPU percentage: {str(e)}"
        )


@router.get("/{server_id}/memory", response_model=ServerMemory)
async def get_server_memory(
    server_id: str, _: UserPublic = Depends(get_current_user)
):
    """Get memory usage for a specific server (available when running/starting/healthy)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is in a state where memory monitoring is available
        status = await instance.get_status()
        if status not in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' memory monitoring not available (status: {status})",
            )

        # Get memory usage
        memory_stats = await instance.get_memory_usage()

        # Calculate actual memory usage from memory stats (anon + file is commonly used memory)
        memory_usage_bytes = memory_stats.anon + memory_stats.file

        return ServerMemory(
            memoryUsageBytes=memory_usage_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server memory usage: {str(e)}"
        )


@router.get("/{server_id}/iostats", response_model=ServerIOStats)
async def get_server_iostats(server_id: str, _: UserPublic = Depends(get_current_user)):
    """Get comprehensive I/O statistics for a specific server (disk I/O, network I/O, disk usage)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server is in a state where I/O monitoring is available
        status = await instance.get_status()
        if status not in [
            MCServerStatus.RUNNING,
            MCServerStatus.STARTING,
            MCServerStatus.HEALTHY,
        ]:
            raise HTTPException(
                status_code=409,
                detail=f"Server '{server_id}' I/O stats not available (status: {status})",
            )

        # Get I/O statistics concurrently (disk I/O and network I/O only)
        disk_io_task = instance.get_disk_io()
        network_io_task = instance.get_network_io()

        disk_io, network_io = await asyncio.gather(disk_io_task, network_io_task)

        return ServerIOStats(
            diskReadBytes=disk_io.total_read_bytes,
            diskWriteBytes=disk_io.total_write_bytes,
            networkReceiveBytes=network_io.total_rx_bytes,
            networkSendBytes=network_io.total_tx_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server I/O stats: {str(e)}"
        )


@router.get("/{server_id}/disk-usage", response_model=ServerDiskUsage)
async def get_server_disk_usage(
    server_id: str, _: UserPublic = Depends(get_current_user)
):
    """Get disk usage information for a specific server (always available regardless of server status)"""
    try:
        instance = mc_manager.get_instance(server_id)

        # Check if server exists
        if not await instance.exists():
            raise HTTPException(
                status_code=404, detail=f"Server '{server_id}' not found"
            )

        # Get disk space information - this is always available regardless of server status
        disk_space = await instance.get_disk_space_info()

        return ServerDiskUsage(
            diskUsageBytes=disk_space.used_bytes,
            diskTotalBytes=disk_space.total_bytes,
            diskAvailableBytes=disk_space.available_bytes,
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get server disk usage: {str(e)}"
        )