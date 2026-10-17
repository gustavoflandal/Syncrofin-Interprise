import uuid
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.user import User


class CategoryGroup(Base):
    __tablename__ = "category_groups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"))
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))
    icon: Mapped[str] = mapped_column(String(50), default="folder")
    color: Mapped[str] = mapped_column(String(7), default="#6B7280")
    position: Mapped[int] = mapped_column(Integer, default=0)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    parent_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("category_groups.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    code: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    natureza: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    depth: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="0", default=0)

    user: Mapped["User"] = relationship(back_populates="category_groups")
    children: Mapped[list["CategoryGroup"]] = relationship(
        "CategoryGroup",
        back_populates="parent",
        foreign_keys="[CategoryGroup.parent_id]",
    )
    parent: Mapped[Optional["CategoryGroup"]] = relationship(
        "CategoryGroup",
        back_populates="children",
        foreign_keys="[CategoryGroup.parent_id]",
        remote_side="CategoryGroup.id",
    )
    categories: Mapped[list["Category"]] = relationship(
        back_populates="group",
        order_by="Category.name",
    )
