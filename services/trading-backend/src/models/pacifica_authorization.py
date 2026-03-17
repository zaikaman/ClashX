from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class PacificaAuthorization(Base):
    __tablename__ = "pacifica_authorizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True)
    account_address: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    agent_wallet_address: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    encrypted_agent_private_key: Mapped[str] = mapped_column(Text)
    builder_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    max_fee_rate: Mapped[str] = mapped_column(String(32), default="0.001")
    status: Mapped[str] = mapped_column(String(24), default="draft", index=True)
    builder_approval_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    builder_approval_timestamp: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    builder_approval_expiry_window: Mapped[int | None] = mapped_column(Integer, nullable=True)
    builder_approval_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    builder_approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    bind_agent_message: Mapped[str] = mapped_column(Text)
    bind_agent_timestamp: Mapped[int] = mapped_column(BigInteger)
    bind_agent_expiry_window: Mapped[int] = mapped_column(Integer)
    bind_agent_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_bound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(240), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(tz=UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(tz=UTC),
        onupdate=lambda: datetime.now(tz=UTC),
    )
