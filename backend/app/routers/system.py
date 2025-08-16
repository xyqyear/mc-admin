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
    return ServerInfo(
        cpuPercentage=get_cpu_percent(),
        cpuLoad1Min=get_cpu_load().one_minute,
        cpuLoad5Min=get_cpu_load().five_minutes,
        cpuLoad15Min=get_cpu_load().fifteen_minutes,
        ramUsedGB=get_memory_info().used / 1024**3,
        ramTotalGB=get_memory_info().total / 1024**3,
        diskUsedGB=get_disk_info(settings.server_path).used / 1024**3,
        diskTotalGB=get_disk_info(settings.server_path).total / 1024**3,
        backupUsedGB=get_disk_info(settings.backup_path).used / 1024**3,
        backupTotalGB=get_disk_info(settings.backup_path).total / 1024**3,
    )
