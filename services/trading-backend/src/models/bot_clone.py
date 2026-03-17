import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class BotClone(Base):
    __tablename__ = "bot_clones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_bot_definition_id: Mapped[str] = mapped_column(String(36), ForeignKey("bot_definitions.id"), index=True)
    new_bot_definition_id: Mapped[str] = mapped_column(String(36), ForeignKey("bot_definitions.id"), index=True)
    created_by_user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=UTC)
    )
