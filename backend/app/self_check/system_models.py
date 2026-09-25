from pydantic import BaseModel


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
