import csv
import io
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.upload_guard import validate_upload
from app.core.database import get_async_session
from app.core.workspace_context import (
    WorkspaceContext,
    current_workspace,
    require_permission,
)
from app.schemas.payee import PayeeCreate, PayeeMergeRequest, PayeeRead, PayeeSummary, PayeeUpdate, PayeeBulkDeleteRequest
from app.schemas.category import CategoryRead
from app.services import payee_service

_write_gate = require_permission("payees.write")

router = APIRouter(prefix="/api/payees", tags=["payees"])


def _payee_in_use(error: ValueError) -> HTTPException:
    """Turn "this counterparty is still referenced" into an answer.

    Invoices hold their payee under a RESTRICT foreign key on purpose:
    deleting a client must never silently delete the record of money they
    owed. Without this the constraint surfaces as a 500, which tells the
    user nothing and tells the operator that something crashed.

    409 rather than 400: the request is well formed and the refusal is
    about the state of the data, which is exactly what Conflict means.
    """
    reason = str(error)
    if reason.startswith("payee_has_invoices:"):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "payee_has_invoices",
                "count": int(reason.split(":", 1)[1] or 0),
                # The way out, named: merging keeps the history, which is
                # what someone deleting a duplicate actually wants.
                "message": "This client has invoices. Merge it into another client instead.",
            },
        )
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=reason)


@router.get("", response_model=list[PayeeRead])
async def list_payees(
    q: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    is_favorite: Optional[bool] = Query(None),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await payee_service.get_payees(
        session, ctx.workspace.id, q=q, type=type, is_favorite=is_favorite
    )


@router.get("/{payee_id}", response_model=PayeeRead)
async def get_payee(
    payee_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    payee = await payee_service.get_payee(session, payee_id, ctx.workspace.id)
    if not payee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payee not found")
    return payee


@router.get("/{payee_id}/summary", response_model=PayeeSummary)
async def get_payee_summary(
    payee_id: uuid.UUID,
    start_date: Optional[date] = Query(None, alias="from"),
    end_date: Optional[date] = Query(None, alias="to"),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        result = await payee_service.get_payee_summary(session, payee_id, ctx.workspace.id, start_date, end_date)
        return PayeeSummary(
            payee=PayeeRead.model_validate(result["payee"], from_attributes=True),
            total_spent=result["total_spent"],
            total_received=result["total_received"],
            transaction_count=result["transaction_count"],
            most_common_category=CategoryRead.model_validate(result["most_common_category"], from_attributes=True) if result["most_common_category"] else None,
            last_transaction_date=result["last_transaction_date"],
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("", response_model=PayeeRead, status_code=status.HTTP_201_CREATED)
async def create_payee(
    data: PayeeCreate,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await payee_service.create_payee(session, ctx.workspace.id, ctx.user_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.patch("/{payee_id}", response_model=PayeeRead)
async def update_payee(
    payee_id: uuid.UUID,
    data: PayeeUpdate,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        payee = await payee_service.update_payee(session, payee_id, ctx.workspace.id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    if not payee:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payee not found")
    return payee


@router.delete("/{payee_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_payee(
    payee_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        deleted = await payee_service.delete_payee(session, payee_id, ctx.workspace.id)
    except ValueError as exc:
        raise _payee_in_use(exc)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payee not found")


@router.post("/merge")
async def merge_payees(
    data: PayeeMergeRequest,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        reassigned = await payee_service.merge_payees(session, ctx.workspace.id, data.target_id, data.source_ids)
        return {"merged": len(data.source_ids), "transactions_reassigned": reassigned}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/bulk-delete", status_code=status.HTTP_200_OK)
async def bulk_delete_payees(
    data: PayeeBulkDeleteRequest,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        deleted_count = await payee_service.bulk_delete_payees(
            session, ctx.workspace.id, data.ids
        )
    except ValueError as exc:
        raise _payee_in_use(exc)
    return {"deleted": deleted_count}


@router.post("/import", status_code=status.HTTP_200_OK)
async def import_payees(
    file: UploadFile = File(...),
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Bulk-import payees from a CSV file.

    Required column: ``name``. Optional: ``type`` (person|company), ``email``,
    ``phone``, ``address``, ``notes``. Rows with a name that already exists in
    the workspace are skipped (case-insensitive match). Returns counts of
    created, skipped and failed rows.
    """
    content, _ = await validate_upload(file, category="import")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "name" not in [f.lower().strip() for f in reader.fieldnames]:
        raise HTTPException(status_code=422, detail="CSV must have a 'name' column")

    # Normalise header names
    def _col(row: dict, *candidates: str) -> str | None:
        for c in candidates:
            for k, v in row.items():
                if k.lower().strip() == c:
                    return (v or "").strip() or None
        return None

    created = skipped = failed = 0
    errors: list[str] = []

    existing_names = {
        name.lower()
        for name in await payee_service.list_payee_names(session, ctx.workspace.id)
    }

    for i, row in enumerate(reader, start=2):
        name = _col(row, "name", "nome")
        if not name:
            failed += 1
            errors.append(f"row {i}: missing name")
            continue
        if name.lower() in existing_names:
            skipped += 1
            continue
        ptype = _col(row, "type", "tipo")
        if ptype and ptype.lower() not in ("person", "company", "pessoa", "empresa"):
            ptype = None
        elif ptype:
            ptype = "person" if ptype.lower() in ("person", "pessoa") else "company"
        try:
            data = PayeeCreate(
                name=name,
                type=ptype,  # type: ignore[arg-type]
                email=_col(row, "email"),
                phone=_col(row, "phone", "telefone"),
                address=_col(row, "address", "endereço", "endereco"),
                notes=_col(row, "notes", "observações", "observacoes"),
            )
            await payee_service.create_payee(session, ctx.workspace.id, ctx.user_id, data)
            existing_names.add(name.lower())
            created += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append(f"row {i}: {exc}")

    await session.commit()
    return {"created": created, "skipped": skipped, "failed": failed, "errors": errors[:20]}
