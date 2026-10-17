import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.upload_guard import download_headers, validate_upload
from app.core.database import get_async_session
from app.core.workspace_context import (
    WorkspaceContext,
    current_workspace,
    require_permission,
)
from app.schemas.attachment import AttachmentRead, AttachmentRename
from app.services import attachment_service

_write_gate = require_permission("transactions.write")

router = APIRouter(
    prefix="/api/transactions/{transaction_id}/attachments",
    tags=["attachments"],
)


@router.post("", response_model=AttachmentRead, status_code=status.HTTP_201_CREATED)
async def upload_attachment(
    transaction_id: uuid.UUID,
    file: UploadFile,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    data, detected_type = await validate_upload(file, category="attachment")
    try:
        attachment = await attachment_service.upload_attachment(
            session=session,
            workspace_id=ctx.workspace.id,
            user_id=ctx.user_id,
            transaction_id=transaction_id,
            filename=file.filename or "unnamed",
            content_type=detected_type,
            data=data,
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return attachment


@router.get("", response_model=list[AttachmentRead])
async def list_attachments(
    transaction_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await attachment_service.list_attachments(session, ctx.workspace.id, transaction_id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")


@router.get("/{attachment_id}")
async def download_attachment(
    transaction_id: uuid.UUID,
    attachment_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        attachment, data = await attachment_service.download_attachment(
            session, attachment_id, ctx.workspace.id
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers=download_headers(attachment.filename, attachment.content_type),
    )


@router.patch("/{attachment_id}", response_model=AttachmentRead)
async def rename_attachment(
    transaction_id: uuid.UUID,
    attachment_id: uuid.UUID,
    body: AttachmentRename,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        return await attachment_service.rename_attachment(
            session, attachment_id, ctx.workspace.id, body.filename
        )
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{attachment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_attachment(
    transaction_id: uuid.UUID,
    attachment_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    try:
        await attachment_service.delete_attachment(session, attachment_id, ctx.workspace.id)
    except LookupError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
