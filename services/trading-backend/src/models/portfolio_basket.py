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
class PortfolioBasketRecord:
    id: str
    owner_user_id: str
    wallet_address: str
    name: str
    description: str
    status: str
    rebalance_mode: str
    rebalance_interval_minutes: int
    drift_threshold_pct: float
    target_notional_usd: float
    current_notional_usd: float
    kill_switch_reason: str | None
    last_rebalanced_at: str | None
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        *,
        owner_user_id: str,
        wallet_address: str,
        name: str,
        description: str,
        status: str,
        rebalance_mode: str,
        rebalance_interval_minutes: int,
        drift_threshold_pct: float,
        target_notional_usd: float,
        created_at: str | None = None,
    ) -> "PortfolioBasketRecord":
        timestamp = _resolve_timestamp(created_at)
        return cls(
            id=str(uuid.uuid4()),
            owner_user_id=owner_user_id,
            wallet_address=wallet_address,
            name=name.strip(),
            description=description.strip(),
            status=status.strip() or "draft",
            rebalance_mode=rebalance_mode.strip() or "drift",
            rebalance_interval_minutes=max(5, int(rebalance_interval_minutes)),
            drift_threshold_pct=max(0.5, float(drift_threshold_pct)),
            target_notional_usd=max(50.0, float(target_notional_usd)),
            current_notional_usd=0.0,
            kill_switch_reason=None,
            last_rebalanced_at=None,
            created_at=timestamp,
            updated_at=timestamp,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "owner_user_id": self.owner_user_id,
            "wallet_address": self.wallet_address,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "rebalance_mode": self.rebalance_mode,
            "rebalance_interval_minutes": self.rebalance_interval_minutes,
            "drift_threshold_pct": self.drift_threshold_pct,
            "target_notional_usd": self.target_notional_usd,
            "current_notional_usd": self.current_notional_usd,
            "kill_switch_reason": self.kill_switch_reason,
            "last_rebalanced_at": self.last_rebalanced_at,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
