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
class BotInviteAccessRecord:
    id: str
    bot_definition_id: str
    invited_wallet_address: str
    invited_by_user_id: str
    status: str
    note: str
    created_at: str
    updated_at: str

    @classmethod
    def create(
        cls,
        *,
        bot_definition_id: str,
        invited_wallet_address: str,
        invited_by_user_id: str,
        note: str | None = None,
        created_at: str | None = None,
    ) -> "BotInviteAccessRecord":
        timestamp = _resolve_timestamp(created_at)
        return cls(
            id=str(uuid.uuid4()),
            bot_definition_id=bot_definition_id,
            invited_wallet_address=invited_wallet_address.strip(),
            invited_by_user_id=invited_by_user_id,
            status="active",
            note=(note or "").strip(),
            created_at=timestamp,
            updated_at=timestamp,
        )

    def to_row(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_definition_id": self.bot_definition_id,
            "invited_wallet_address": self.invited_wallet_address,
            "invited_by_user_id": self.invited_by_user_id,
            "status": self.status,
            "note": self.note,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
