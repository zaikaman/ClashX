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
class PortfolioAllocationMemberRecord:
    id: str
    portfolio_basket_id: str
    source_runtime_id: str
    target_weight_pct: float
    target_notional_usd: float
    max_scale_bps: int
    target_scale_bps: int
    relationship_id: str | None
    status: str
    latest_scale_bps: int | None
    last_rebalanced_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        *,
        portfolio_basket_id: str,
        source_runtime_id: str,
        target_weight_pct: float,
        target_notional_usd: float,
        max_scale_bps: int,
        target_scale_bps: int,
        created_at: str | None = None,
    ) -> "PortfolioAllocationMemberRecord":
        timestamp = _resolve_timestamp(created_at)
        return cls(
            id=str(uuid.uuid4()),
            portfolio_basket_id=portfolio_basket_id,
            source_runtime_id=source_runtime_id,
            target_weight_pct=round(float(target_weight_pct), 4),
            target_notional_usd=round(float(target_notional_usd), 4),
            max_scale_bps=max(500, int(max_scale_bps)),
            target_scale_bps=max(500, int(target_scale_bps)),
            relationship_id=None,
            status="active",
            latest_scale_bps=None,
            last_rebalanced_at=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "portfolio_basket_id": self.portfolio_basket_id,
            "source_runtime_id": self.source_runtime_id,
            "target_weight_pct": self.target_weight_pct,
            "target_notional_usd": self.target_notional_usd,
            "max_scale_bps": self.max_scale_bps,
            "target_scale_bps": self.target_scale_bps,
            "relationship_id": self.relationship_id,
            "status": self.status,
            "latest_scale_bps": self.latest_scale_bps,
            "last_rebalanced_at": self.last_rebalanced_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
