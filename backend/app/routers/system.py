from config import settings
from dependencies import get_current_user
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from system.resources import (
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
    cpuPercentage: float
    cpuLoad1Min: float
    cpuLoad5Min: float
    cpuLoad15Min: float
    ramUsedGB: float
    ramTotalGB: float
    diskUsedGB: float
    diskTotalGB: float
    backupUsedGB: float
    backupTotalGB: float


@router.get(
    "/info", dependencies=[Depends(get_current_user)], response_model=ServerInfo
)
def get_server_info():
    cpu_percent = get_cpu_percent()
    cpu_load = get_cpu_load()
    memory_info = get_memory_info()
    server_disk_info = get_disk_info(settings.server_path)
    backup_disk_info = get_disk_info(settings.backup_path)

    return ServerInfo(
        cpuPercentage=cpu_percent,
        cpuLoad1Min=cpu_load.one_minute,
        cpuLoad5Min=cpu_load.five_minutes,
        cpuLoad15Min=cpu_load.fifteen_minutes,
        ramUsedGB=memory_info.used / 1024**3,
        ramTotalGB=memory_info.total / 1024**3,
        diskUsedGB=server_disk_info.used / 1024**3,
        diskTotalGB=server_disk_info.total / 1024**3,
        backupUsedGB=backup_disk_info.used / 1024**3,
        backupTotalGB=backup_disk_info.total / 1024**3,
    )
