from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def _resolve_timestamp(value: str | None = None) -> str:
    if isinstance(value, str) and value.strip():
        return value
    return datetime.now(tz=UTC).isoformat()


@dataclass(frozen=True, slots=True)
class PortfolioRiskPolicyRecord:
    id: str
    portfolio_basket_id: str
    max_drawdown_pct: float
    max_member_drawdown_pct: float
    min_trust_score: int
    max_active_members: int
    auto_pause_on_source_stale: bool
    kill_switch_on_breach: bool
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        *,
        portfolio_basket_id: str,
        max_drawdown_pct: float,
        max_member_drawdown_pct: float,
        min_trust_score: int,
        max_active_members: int,
        auto_pause_on_source_stale: bool,
        kill_switch_on_breach: bool,
        created_at: str | None = None,
    ) -> "PortfolioRiskPolicyRecord":
        timestamp = _resolve_timestamp(created_at)
        return cls(
            id=str(uuid.uuid4()),
            portfolio_basket_id=portfolio_basket_id,
            max_drawdown_pct=max(5.0, float(max_drawdown_pct)),
            max_member_drawdown_pct=max(5.0, float(max_member_drawdown_pct)),
            min_trust_score=max(0, min(100, int(min_trust_score))),
            max_active_members=max(1, int(max_active_members)),
            auto_pause_on_source_stale=bool(auto_pause_on_source_stale),
            kill_switch_on_breach=bool(kill_switch_on_breach),
            created_at=timestamp,
            updated_at=timestamp,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "portfolio_basket_id": self.portfolio_basket_id,
            "max_drawdown_pct": self.max_drawdown_pct,
            "max_member_drawdown_pct": self.max_member_drawdown_pct,
            "min_trust_score": self.min_trust_score,
            "max_active_members": self.max_active_members,
            "auto_pause_on_source_stale": self.auto_pause_on_source_stale,
            "kill_switch_on_breach": self.kill_switch_on_breach,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
