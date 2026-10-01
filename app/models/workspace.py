from datetime import datetime, timezone
from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base


class Workspace(Base):
    """A Legal Study workspace: a named collection of PDFs owned by one user.

    Hierarchy: User -> Workspace -> Document -> DocumentChunk.
    Workspace documents reuse the existing `documents` / `document_chunks`
    tables (via Document.workspace_id), so every chunk keeps `document_id`
    and `page_number`.
    """
    __tablename__ = "workspaces"
    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(150))
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
    owner = relationship("User", back_populates="workspaces")
    documents = relationship("Document", back_populates="workspace", cascade="all")
    __table_args__ = (Index("ix_workspaces_owner_updated", "owner_id", "updated_at"),)
