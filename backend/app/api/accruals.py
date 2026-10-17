import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, current_workspace, require_permission
from app.schemas.accrual import (
    AccrualPostRequest,
    AccrualPostResult,
    AccrualScheduleCreate,
    AccrualScheduleDetail,
    AccrualScheduleRead,
)
from app.services import accrual_service

_write_gate = require_permission("transactions.write")

router = APIRouter(prefix="/api/accruals", tags=["accruals"])


def _read(schedule) -> AccrualScheduleRead:
    return AccrualScheduleRead.model_validate(schedule).model_copy(
        update=accrual_service.status_counts(schedule)
    )


def _detail(schedule) -> AccrualScheduleDetail:
    return AccrualScheduleDetail.model_validate(schedule).model_copy(
        update=accrual_service.status_counts(schedule)
    )


@router.get("", response_model=list[AccrualScheduleRead])
async def list_schedules(
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    schedules = await accrual_service.get_schedules(session, ctx.workspace.id)
    return [_read(s) for s in schedules]


@router.post("", response_model=AccrualScheduleDetail, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    data: AccrualScheduleCreate,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    schedule = await accrual_service.create_schedule(session, ctx.workspace.id, ctx.user.id, data)
    return _detail(schedule)


# Antes de `/{schedule_id}` para que "post" não seja lido como id.
@router.post("/post", response_model=AccrualPostResult)
async def post_now(
    data: AccrualPostRequest | None = None,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    up_to = (data.up_to_date if data else None) or date.today()
    return await accrual_service.post_entries(session, ctx.workspace.id, up_to)


@router.get("/{schedule_id}", response_model=AccrualScheduleDetail)
async def get_schedule(
    schedule_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    schedule = await accrual_service.get_schedule(session, schedule_id, ctx.workspace.id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="accrual_not_found")
    return _detail(schedule)


@router.delete("/{schedule_id}", response_model=AccrualScheduleDetail)
async def cancel_schedule(
    schedule_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    schedule = await accrual_service.cancel_schedule(session, schedule_id, ctx.workspace.id)
    if schedule is None:
        raise HTTPException(status_code=404, detail="accrual_not_found")
    return _detail(schedule)
