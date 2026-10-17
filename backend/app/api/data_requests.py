"""The D1 channel: a person's own access/portability/correction/erasure requests, and the admin's queue."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import current_active_user, current_superuser, get_user_manager
from app.core.database import get_async_session
from app.core.rate_limit import erasure_rate_limit
from app.models.data_subject_request import KINDS, STATUSES, DataSubjectRequest
from app.models.user import User
from app.services import data_subject_request_service as svc

router = APIRouter(tags=["data-requests"])


class DataRequestRead(BaseModel):
    id: UUID
    protocol: str
    kind: str
    status: str
    created_at: datetime
    due_at: datetime
    resolved_at: Optional[datetime] = None
    detail: Optional[str] = None
    resolution_note: Optional[str] = None
    #: Populated only for a self-service correction — where the person can already fix it themselves.
    #: None/absent for every other kind, and for a non-self-service correction.
    self_service_links: Optional[dict[str, str]] = None

    model_config = {"from_attributes": True}


class DataRequestPage(BaseModel):
    items: list[DataRequestRead]


class AdminDataRequestRead(DataRequestRead):
    """The admin queue's own shape: who filed the request. Never used for the person's own view
    (`list_my_requests`/`create_request`) — it's their own data, the field is redundant there."""

    user_id: UUID
    actor_email: Optional[str] = None


class AdminDataRequestPage(BaseModel):
    items: list[AdminDataRequestRead]


def _admin_read(row: DataSubjectRequest, email: Optional[str]) -> AdminDataRequestRead:
    data = AdminDataRequestRead.model_validate(row, from_attributes=True)
    data.actor_email = email
    return data


class CreateDataRequest(BaseModel):
    kind: str
    self_service: Optional[bool] = None
    detail: Optional[str] = None


class ErasureBody(BaseModel):
    password: str


class AdminResolve(BaseModel):
    status: str = Field(pattern="^(resolved_manual|rejected)$")
    resolution_note: Optional[str] = None


def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


BASE_PATH = "/api/data-requests"


@router.post(BASE_PATH)
async def create_request(
    body: CreateDataRequest,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    if body.kind not in KINDS:
        raise HTTPException(status_code=422, detail="UNKNOWN_REQUEST_KIND")

    if body.kind in ("access", "portability"):
        row, archive = await svc.create_access_or_portability(session, user, body.kind)
        return StreamingResponse(
            iter([archive]),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="syncrofin-dados-{_today()}.zip"'},
        )

    if body.kind == "correction":
        if body.self_service is None:
            raise HTTPException(status_code=422, detail="SELF_SERVICE_REQUIRED")
        try:
            row = await svc.create_correction(
                session, user, self_service=body.self_service, detail=body.detail
            )
        except ValueError:
            raise HTTPException(status_code=422, detail="DETAIL_REQUIRED")
        data = DataRequestRead.model_validate(row)
        if body.self_service:
            data.self_service_links = svc.SELF_SERVICE_LINKS
        return data

    raise HTTPException(status_code=422, detail="USE_THE_ERASURE_ROUTE_FOR_ERASURE")


@router.get(BASE_PATH, response_model=DataRequestPage)
async def list_my_requests(
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
):
    rows = await svc.list_own(session, user)
    return DataRequestPage(items=[DataRequestRead.model_validate(r) for r in rows])


@router.post(f"{BASE_PATH}/erasure", dependencies=[Depends(erasure_rate_limit)])
async def erasure(
    body: ErasureBody,
    user: User = Depends(current_active_user),
    session: AsyncSession = Depends(get_async_session),
    user_manager=Depends(get_user_manager),
):
    try:
        row = await svc.request_erasure(session, user_manager, user, body.password)
    except svc.WrongPassword:
        raise HTTPException(status_code=401, detail="WRONG_PASSWORD")
    except svc.WorkspacesBlockErasure as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "WORKSPACES_BLOCK_ERASURE",
                "workspaces": exc.workspace_names,
                "protocol": exc.protocol,
            },
        )
    return DataRequestRead.model_validate(row)


@router.get("/api/admin/data-requests", response_model=AdminDataRequestPage)
async def admin_list(
    status: Optional[str] = Query(None),
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    if status is not None and status not in STATUSES:
        raise HTTPException(status_code=422, detail="UNKNOWN_STATUS")
    conditions = [DataSubjectRequest.status == status] if status else []
    rows = (
        await session.execute(
            select(DataSubjectRequest, User.email)
            .outerjoin(User, User.id == DataSubjectRequest.user_id)
            .where(*conditions)
            .order_by(DataSubjectRequest.created_at.desc(), DataSubjectRequest.id.desc())
        )
    ).all()
    return AdminDataRequestPage(items=[_admin_read(row, email) for row, email in rows])


@router.patch("/api/admin/data-requests/{request_id}", response_model=AdminDataRequestRead)
async def admin_resolve(
    request_id: UUID,
    body: AdminResolve,
    _: User = Depends(current_superuser),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        row = await svc.resolve(session, request_id, body.status, body.resolution_note)
    except svc.AlreadyResolved:
        raise HTTPException(status_code=409, detail="ALREADY_RESOLVED")
    if row is None:
        raise HTTPException(status_code=404)
    email = (await session.execute(select(User.email).where(User.id == row.user_id))).scalar_one_or_none()
    return _admin_read(row, email)
