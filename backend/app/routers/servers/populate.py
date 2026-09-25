from fastapi import APIRouter, Depends

from app.auth.schemas import UserPublic
from app.files.api_models import PopulateServerRequest, PopulateServerResponse

from ...background_tasks import get_task_manager
from ...background_tasks.types import TaskType
from ...config import get_settings
from ...dependencies import get_current_user
from ...files.paths import resolve_file_path
from ...files.population import check_population_status, populate, prepare_population
from ...minecraft import get_docker_mc_manager
from ...runtime_resources import spawn_background
from ...self_check.constants import SERVER_POPULATED_TRIGGER
from ...self_check.events import schedule_self_check_event
from .admission import admit_server_write

router = APIRouter(
    prefix="/servers",
    tags=["server-populate"],
    dependencies=[Depends(admit_server_write)],
)


@router.post("/{server_id}/populate", response_model=PopulateServerResponse)
async def populate_server(
    server_id: str,
    populate_request: PopulateServerRequest,
    user: UserPublic = Depends(get_current_user),
):
    """Populate server data directory from an archive file (background task)"""
    settings = get_settings()
    instance = get_docker_mc_manager().get_instance(server_id)

    await check_population_status(instance)

    # Get archive path
    archive_path = await resolve_file_path(
        settings.archive_path, populate_request.archive_filename
    )

    # Submit as background task
    task_name = f"填充 {server_id}"
    plan = await prepare_population(instance, archive_path, archive_root=settings.archive_path)
    result = await get_task_manager().submit_durable(
        task_type=TaskType.ARCHIVE_EXTRACT,
        name=task_name,
        task_generator=populate(plan, actor_id=user.id),
        claims=plan.claims,
        server_id=server_id,
        actor_id=user.id,
        cancellable=False,  # Extraction shouldn't be cancelled mid-way
    )

    async def _schedule_after_completion() -> None:
        task_result = await result.awaitable
        if task_result.success:
            schedule_self_check_event(SERVER_POPULATED_TRIGGER, user.id)

    spawn_background(_schedule_after_completion(), name="populate-self-check")

    return PopulateServerResponse(task_id=result.task_id)
