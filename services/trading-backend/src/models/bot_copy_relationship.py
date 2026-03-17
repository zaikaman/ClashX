import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class BotCopyRelationship(Base):
    __tablename__ = "bot_copy_relationships"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_runtime_id: Mapped[str] = mapped_column(String(36), ForeignKey("bot_runtimes.id"), index=True)
    follower_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    follower_wallet_address: Mapped[str] = mapped_column(String(128), index=True)
    mode: Mapped[str] = mapped_column(String(24), default="mirror")
    scale_bps: Mapped[int] = mapped_column(Integer, default=10_000)
    status: Mapped[str] = mapped_column(String(24), default="active", index=True)
    risk_ack_version: Mapped[str] = mapped_column(String(24), default="v1")
    confirmed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=UTC)
    )
