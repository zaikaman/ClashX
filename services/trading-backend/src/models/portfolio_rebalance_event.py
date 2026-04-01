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
class PortfolioRebalanceEventRecord:
    id: str
    portfolio_basket_id: str
    trigger: str
    status: str
    summary_json: dict[str, Any]
    created_at: str

    @classmethod
    def create(
        cls,
        *,
        portfolio_basket_id: str,
        trigger: str,
        status: str,
        summary_json: dict[str, Any] | None = None,
        created_at: str | None = None,
    ) -> "PortfolioRebalanceEventRecord":
        return cls(
            id=str(uuid.uuid4()),
            portfolio_basket_id=portfolio_basket_id,
            trigger=trigger.strip() or "manual",
            status=status.strip() or "completed",
            summary_json=summary_json if isinstance(summary_json, dict) else {},
            created_at=_resolve_timestamp(created_at),
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "portfolio_basket_id": self.portfolio_basket_id,
            "trigger": self.trigger,
            "status": self.status,
            "summary_json": self.summary_json,
            "created_at": self.created_at,
        }
