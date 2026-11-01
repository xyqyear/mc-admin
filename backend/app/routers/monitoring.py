from fastapi import APIRouter, Depends

from ..dependencies import get_current_user
from ..monitoring.models import MonitoringSnapshot, ServerSamples
from ..runtime_resources import current_runtime
from ..servers.queries import get_server_maintenance

router = APIRouter(prefix="/monitoring", tags=["monitoring"], dependencies=[Depends(get_current_user)])


@router.get("", response_model=MonitoringSnapshot)
async def get_monitoring() -> MonitoringSnapshot:
    runtime = current_runtime()
    monitor = runtime.monitor
    identities = await monitor.identities()
    maintenance = get_server_maintenance(
        list(identities), runtime.server_write_admission, runtime.task_manager, runtime.server_operation_lock,
    )
    return MonitoringSnapshot(
        system=monitor.system.view(),
        servers={server_id: monitor.servers.get(generation, ServerSamples(generation=generation)).view(maintenance[server_id])
                 for server_id, generation in identities.items()},
    )
