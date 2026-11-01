from fastapi import APIRouter

from ..system.models import HealthCheck

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/health", response_model=HealthCheck)
async def get_health() -> HealthCheck:
    return HealthCheck(status="healthy")
