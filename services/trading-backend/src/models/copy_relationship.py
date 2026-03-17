import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class CopyRelationship(Base):
    __tablename__ = "copy_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    follower_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    source_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    scale_bps: Mapped[int] = mapped_column(Integer, default=10_000)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    risk_ack_version: Mapped[str] = mapped_column(String(24), default="v1")
    max_notional_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=UTC)
    )
