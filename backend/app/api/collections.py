import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_async_session
from app.core.workspace_context import (
    WorkspaceContext,
    current_workspace,
    require_permission,
)
from app.schemas.collection import CollectionCreate, CollectionRead, CollectionUpdate
from app.services import collection_service

_write_gate = require_permission("collections.write")

router = APIRouter(prefix="/api/collections", tags=["collections"])


@router.get("", response_model=list[CollectionRead])
async def list_collections(
    ctx: WorkspaceContext = Depends(current_workspace),
    session: AsyncSession = Depends(get_async_session),
):
    return await collection_service.get_collections(session, ctx.workspace.id)


@router.post("", response_model=CollectionRead, status_code=status.HTTP_201_CREATED)
async def create_collection(
    data: CollectionCreate,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    return await collection_service.create_collection(session, ctx.workspace.id, ctx.user_id, data)


@router.patch("/{collection_id}", response_model=CollectionRead)
async def update_collection(
    collection_id: uuid.UUID,
    data: CollectionUpdate,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    collection = await collection_service.update_collection(
        session, collection_id, ctx.workspace.id, data
    )
    if not collection:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
    return collection


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_collection(
    collection_id: uuid.UUID,
    ctx: WorkspaceContext = Depends(_write_gate),
    session: AsyncSession = Depends(get_async_session),
):
    deleted = await collection_service.delete_collection(session, collection_id, ctx.workspace.id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Collection not found")
