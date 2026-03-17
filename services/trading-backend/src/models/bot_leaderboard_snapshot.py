import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.session import Base


class BotLeaderboardSnapshot(Base):
    __tablename__ = "bot_leaderboard_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    runtime_id: Mapped[str] = mapped_column(String(36), ForeignKey("bot_runtimes.id"), index=True)
    rank: Mapped[int] = mapped_column(Integer, default=0, index=True)
    pnl_total: Mapped[float] = mapped_column(Float, default=0.0)
    pnl_unrealized: Mapped[float] = mapped_column(Float, default=0.0)
    win_streak: Mapped[int] = mapped_column(Integer, default=0)
    drawdown: Mapped[float] = mapped_column(Float, default=0.0)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(tz=UTC), index=True
    )
