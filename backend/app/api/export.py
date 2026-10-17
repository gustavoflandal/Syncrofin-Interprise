from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import WorkspaceContext, require_permission
from app.schemas.export import AccountantExportRequest, BackupRequest
from app.services import accountant_export_service, backup_service
from app.services.backup_service import build_backup_archive

_export_gate = require_permission("export.read")

router = APIRouter(prefix="/api/export", tags=["export"])


def _as_download(archive: bytes) -> StreamingResponse:
    today = date.today().isoformat()
    return StreamingResponse(
        iter([archive]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="syncrofin-backup-{today}.zip"'},
    )


@router.get("/backup")
async def backup(
    ctx: WorkspaceContext = Depends(_export_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """Export every entity in the current workspace as a JSON zip.

    Backup is scoped to one workspace at a time — users with multiple
    workspaces back each one up separately. AssetValue inherits its
    workspace from its Asset and is filtered transitively.
    """
    return _as_download(build_backup_archive(await backup_service.collect_workspace(ctx.workspace, session)))


@router.post("/backup")
async def backup_protected(
    body: BackupRequest,
    ctx: WorkspaceContext = Depends(_export_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """The same archive, encrypted with AES-256 when a password is given.

    A POST because the password belongs in a body: a query string is written
    to browser history, proxy logs and server access logs. SyncroFin never stores
    the password and cannot recover the archive without it.
    """
    password = body.password.get_secret_value() if body.password else None
    return _as_download(build_backup_archive(await backup_service.collect_workspace(ctx.workspace, session), password))


async def _accountant_download(
    ctx: WorkspaceContext,
    session: AsyncSession,
    start: date,
    end: date,
    password: str | None,
) -> StreamingResponse:
    try:
        files = await accountant_export_service.build_files(session, ctx.workspace, start, end)
    except accountant_export_service.ExportPeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    archive = accountant_export_service.build_zip(files, password)
    return StreamingResponse(
        iter([archive]),
        media_type="application/zip",
        headers={
            "Content-Disposition": (
                f'attachment; filename="syncrofin-contador-{start.isoformat()}_{end.isoformat()}.zip"'
            )
        },
    )


@router.get("/accountant")
async def accountant_package(
    start: date = Query(...),
    end: date = Query(...),
    ctx: WorkspaceContext = Depends(_export_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """The period's movements and summaries as spreadsheet-ready CSVs in a zip.

    Open to every member, `viewer` included: this is exactly what the
    read-only accountant role is for. It only reads.
    """
    return await _accountant_download(ctx, session, start, end, None)


@router.post("/accountant")
async def accountant_package_protected(
    body: AccountantExportRequest,
    ctx: WorkspaceContext = Depends(_export_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """The same package, AES-256 encrypted when a password is given."""
    password = body.password.get_secret_value() if body.password else None
    return await _accountant_download(ctx, session, body.start, body.end, password)


@router.get("/accountant/xlsx")
async def accountant_xlsx(
    start: date = Query(...),
    end: date = Query(...),
    ctx: WorkspaceContext = Depends(_export_gate),
    session: AsyncSession = Depends(get_async_session),
):
    """The same package as a single XLSX workbook (one sheet per file).

    Handy for accountants who prefer everything in one Excel file that can be
    imported directly into Omie, Conta Azul, or any XLSX-aware accounting tool.
    """
    try:
        files = await accountant_export_service.build_files(session, ctx.workspace, start, end)
    except accountant_export_service.ExportPeriodError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    xlsx = accountant_export_service.build_xlsx(files)
    fname = f"syncrofin-contador-{start.isoformat()}_{end.isoformat()}.xlsx"
    return StreamingResponse(
        iter([xlsx]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
