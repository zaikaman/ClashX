import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class CopyExecutionEvent(Base):
    __tablename__ = "copy_execution_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    copy_relationship_id: Mapped[str] = mapped_column(String(36), ForeignKey("copy_relationships.id"), index=True)
    source_order_ref: Mapped[str] = mapped_column(String(120), index=True)
    mirrored_order_ref: Mapped[str] = mapped_column(String(120), index=True)
    symbol: Mapped[str] = mapped_column(String(16), index=True)
    side: Mapped[str] = mapped_column(String(8))
    size_source: Mapped[float] = mapped_column(Float, default=0.0)
    size_mirrored: Mapped[float] = mapped_column(Float, default=0.0)
    status: Mapped[str] = mapped_column(String(24), default="queued", index=True)
    error_reason: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=UTC)
    )
