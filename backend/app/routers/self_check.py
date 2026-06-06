"""Self-check API endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from fastapi.responses import StreamingResponse

from ..db.database import get_async_session
from ..dependencies import get_current_user
from ..dynamic_config import config
from ..models import UserPublic
from ..self_check import crud
from ..self_check.constants import MANUAL_TRIGGER
from ..self_check.runner import (
    get_catalog,
    iter_self_check_events,
    run_self_check,
    validate_check_id,
)
from ..self_check.types import (
    SelfCheckCatalogItem,
    SelfCheckCurrentState,
    SelfCheckRunDetail,
    SelfCheckRunResult,
    SelfCheckRunsResponse,
)
from ..utils.sse import sse_response

router = APIRouter(prefix="/self-check", tags=["self-check"])


class SelfCheckStatusResponse(SelfCheckRunsResponse):
    catalog: list[SelfCheckCatalogItem]
    current_state: SelfCheckCurrentState | None = None
    retention_runs_keep_days: int


@router.get("/catalog", response_model=list[SelfCheckCatalogItem])
async def list_self_check_catalog(
    _: UserPublic = Depends(get_current_user),
) -> list[SelfCheckCatalogItem]:
    return get_catalog()


@router.post("/run", response_model=SelfCheckRunResult)
async def run_manual_self_check(
    user: UserPublic = Depends(get_current_user),
) -> SelfCheckRunResult:
    return await run_self_check(trigger=MANUAL_TRIGGER, requested_by_user_id=user.id)


@router.post("/run/stream", response_class=StreamingResponse)
async def stream_manual_self_check(
    user: UserPublic = Depends(get_current_user),
) -> StreamingResponse:
    return sse_response(
        iter_self_check_events(
            trigger=MANUAL_TRIGGER,
            requested_by_user_id=user.id,
        )
    )


@router.post("/checks/{check_id}/run", response_model=SelfCheckRunResult)
async def run_manual_self_check_item(
    check_id: str,
    user: UserPublic = Depends(get_current_user),
) -> SelfCheckRunResult:
    try:
        validate_check_id(check_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    return await run_self_check(
        trigger=MANUAL_TRIGGER,
        requested_by_user_id=user.id,
        check_ids=(check_id,),
        scope="check",
    )


@router.get("/runs", response_model=SelfCheckRunsResponse)
async def list_self_check_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _: UserPublic = Depends(get_current_user),
) -> SelfCheckRunsResponse:
    async with get_async_session() as session:
        total = await crud.count_runs(session)
        runs = await crud.list_runs(session, limit=limit, offset=offset)
    return SelfCheckRunsResponse(runs=runs, total=total)


@router.get("/status", response_model=SelfCheckStatusResponse)
async def get_self_check_status(
    _: UserPublic = Depends(get_current_user),
) -> SelfCheckStatusResponse:
    async with get_async_session() as session:
        total = await crud.count_runs(session)
        runs = await crud.list_runs(session, limit=10, offset=0)
        current_state = await crud.get_current_state(
            session,
            enabled_check_ids=config.self_check.enabled_check_ids(),
        )
    return SelfCheckStatusResponse(
        runs=runs,
        total=total,
        catalog=get_catalog(),
        current_state=current_state,
        retention_runs_keep_days=config.self_check.retention_runs_keep_days,
    )


@router.get("/runs/{run_id}", response_model=SelfCheckRunDetail)
async def get_self_check_run(
    run_id: str,
    _: UserPublic = Depends(get_current_user),
) -> SelfCheckRunDetail:
    async with get_async_session() as session:
        run = await crud.get_run(session, run_id)
    if run is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail="自检运行记录不存在",
        )
    return run
