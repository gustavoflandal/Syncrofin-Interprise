import csv
import io
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.upload_guard import validate_upload
from app.core.database import get_async_session
from app.core.workspace_context import (
    WorkspaceContext,
    current_workspace,
    require_permission,
)
from app.schemas.category import (
    CategoryCreate,
    CategoryRead,
    CategoryRuleUsage,
    CategoryUpdate,
    RuleSummary,
)
from app.services import category_service

_write_gate = require_permission("categories.write")

router = APIRouter(prefix="/api/categories", tags=["categories"])


@router.get("", response_model=list[CategoryRead])
async def list_categories(
    include_hidden: bool = Query(False),
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await category_service.get_categories(
        session,
        ctx.workspace.id,
        include_hidden=include_hidden,
    )


@router.post("", response_model=CategoryRead, status_code=status.HTTP_201_CREATED)
async def create_category(
    data: CategoryCreate,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    return await category_service.create_category(session, ctx.workspace.id, ctx.user_id, data)


@router.get("/{category_id}/rule-usage", response_model=CategoryRuleUsage)
async def category_rule_usage(
    category_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    """Active rules that assign this category, so hiding it can offer to retire them."""
    rules = await category_service.get_rules_assigning_category(
        session, ctx.workspace.id, category_id
    )
    return CategoryRuleUsage(rules=[RuleSummary(id=r.id, name=r.name) for r in rules])


@router.patch("/{category_id}", response_model=CategoryRead)
async def update_category(
    category_id: uuid.UUID,
    data: CategoryUpdate,
    deactivate_rules: bool = Query(False),
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        category = await category_service.update_category(
            session,
            category_id,
            ctx.workspace.id,
            data,
            deactivate_rules=deactivate_rules,
        )
    except category_service.CategoryVisibilityError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    if not category:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Category not found")
    return category


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_category(
    category_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        deleted = await category_service.delete_category(
            session, category_id, ctx.workspace.id
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Category not found or is a system category",
        )


@router.post("/import", status_code=status.HTTP_200_OK)
async def import_categories(
    file: UploadFile = File(...),
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Bulk-import categories from a CSV file.

    Required column: ``name``. Optional: ``icon``, ``color``,
    ``treat_as_transfer``, ``is_ignored``. Rows with a name that already
    exists in the workspace are skipped (case-insensitive). Returns counts
    of created, skipped and failed rows.
    """
    content, _ = await validate_upload(file, category="import")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "name" not in [f.lower().strip() for f in (reader.fieldnames or [])]:
        raise HTTPException(status_code=422, detail="CSV must have a 'name' column")

    def _col(row: dict, *candidates: str) -> str | None:
        for c in candidates:
            for k, v in row.items():
                if k.lower().strip() == c:
                    return (v or "").strip() or None
        return None

    def _bool_col(row: dict, *candidates: str) -> bool:
        val = _col(row, *candidates)
        return (val or "").lower() in ("true", "1", "yes", "sim", "s")

    existing = await category_service.get_categories(session, ctx.workspace.id, include_hidden=True)
    existing_names = {c.name.lower() for c in existing}

    created = skipped = failed = 0
    errors: list[str] = []

    for i, row in enumerate(reader, start=2):
        name = _col(row, "name", "nome")
        if not name:
            failed += 1
            errors.append(f"row {i}: missing name")
            continue
        if name.lower() in existing_names:
            skipped += 1
            continue
        try:
            data = CategoryCreate(
                name=name,
                icon=_col(row, "icon", "ícone", "icone") or "circle-help",
                color=_col(row, "color", "cor") or "#6B7280",
                treat_as_transfer=_bool_col(row, "treat_as_transfer", "transferência", "transferencia"),
                is_ignored=_bool_col(row, "is_ignored", "ignorar"),
            )
            await category_service.create_category(session, ctx.workspace.id, ctx.user_id, data)
            existing_names.add(name.lower())
            created += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append(f"row {i}: {exc}")

    await session.commit()
    return {"created": created, "skipped": skipped, "failed": failed, "errors": errors[:20]}
