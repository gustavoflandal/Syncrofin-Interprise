"""A role a workspace's owner made for that workspace.

The product's own roles (owner, editor, viewer, and the virtual manager) are not rows: they are fixed in
`core/permissions.py`. A row here is a *custom* role, a named set of permissions from the same catalog,
that members of this one workspace can be given.

A member holds a role by its `key` (`WorkspaceMember.role`): `owner`, `editor` or `viewer`, or the key of
a custom role (`c_` and eight hex digits). Keeping the key in the column that always held the role means
everything that read it, from the invitation flow to the sign-in role mapping, keeps working.
"""
import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

CUSTOM_KEY_PREFIX = "c_"


class WorkspaceRole(Base):
    __tablename__ = "workspace_roles"
    __table_args__ = (
        UniqueConstraint("workspace_id", "key", name="uq_workspace_role_key"),
        UniqueConstraint("workspace_id", "name", name="uq_workspace_role_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    #: What `WorkspaceMember.role` holds for a member with this role.
    key: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(80))
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    #: Keys from `core/permissions.py`. Unknown keys are refused on write; one that was later removed
    #: from the catalog is ignored on read, so a release that drops a permission cannot break a role.
    permissions: Mapped[list[str]] = mapped_column(JSONB, default=list)
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
