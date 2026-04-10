from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from src.api.auth import AuthenticatedUser
from src.services.copilot_conversation_service import CopilotConversationService


def _utc_now() -> str:
    return datetime.now(tz=UTC).isoformat()


def _user() -> AuthenticatedUser:
    return AuthenticatedUser(user_id="privy-user", wallet_addresses=["wallet-abc"])


def _matches(value: Any, expected: Any) -> bool:
    if isinstance(expected, tuple):
        operator, operand = expected
        if operator == "in":
            return value in operand
        return False
    return value == expected


@dataclass
class _FakeSupabase:
    tables: dict[str, list[dict[str, Any]]] = field(
        default_factory=lambda: {
            "users": [],
            "copilot_conversations": [],
            "copilot_messages": [],
        }
    )

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        del columns
        rows = [dict(row) for row in self.tables[table]]
        if filters:
            rows = [
                row
                for row in rows
                if all(_matches(row.get(key), expected) for key, expected in filters.items())
            ]
        if order:
            parts = order.split(".")
            field_name = parts[0]
            reverse = len(parts) > 1 and parts[1] == "desc"
            rows.sort(key=lambda row: row.get(field_name) or "", reverse=reverse)
        if limit is not None:
            rows = rows[:limit]
        return rows

    def maybe_one(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self.select(table, columns=columns, filters=filters, order=order, limit=1)
        return rows[0] if rows else None

    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
    ) -> list[dict[str, Any]]:
        items = payload if isinstance(payload, list) else [payload]
        inserted: list[dict[str, Any]] = []
        for item in items:
            row = dict(item)
            if upsert and on_conflict:
                existing = next(
                    (
                        saved
                        for saved in self.tables[table]
                        if saved.get(on_conflict) == row.get(on_conflict)
                    ),
                    None,
                )
                if existing is not None:
                    existing.update(row)
                    inserted.append(dict(existing))
                    continue
            self.tables[table].append(row)
            inserted.append(dict(row))
        return inserted

    def update(
        self,
        table: str,
        values: dict[str, Any],
        *,
        filters: dict[str, Any],
    ) -> list[dict[str, Any]]:
        updated: list[dict[str, Any]] = []
        for row in self.tables[table]:
            if all(_matches(row.get(key), expected) for key, expected in filters.items()):
                row.update(values)
                updated.append(dict(row))
        return updated


@dataclass
class _FakeCopilot:
    reply: str = "Stored answer"
    summary: str = "Rolled summary"
    chat_calls: list[dict[str, Any]] = field(default_factory=list)
    summary_calls: list[dict[str, Any]] = field(default_factory=list)

    async def chat(self, *, messages: list[dict[str, str]], user: AuthenticatedUser, wallet_address: str | None) -> dict[str, Any]:
        self.chat_calls.append({"messages": messages, "user": user, "wallet_address": wallet_address})
        return {
            "reply": self.reply,
            "followUps": ["Inspect latest runtime"],
            "toolCalls": [],
            "provider": "OpenAI",
            "usedWalletAddress": wallet_address,
        }

    async def summarize_history(self, *, existing_summary: str, messages: list[dict[str, str]]) -> str:
        self.summary_calls.append({"existing_summary": existing_summary, "messages": messages})
        return self.summary


def test_create_and_list_conversations() -> None:
    supabase = _FakeSupabase()
    copilot = _FakeCopilot()
    service = CopilotConversationService(copilot=copilot, supabase=supabase)

    created = service.create_conversation(user=_user(), wallet_address="wallet-abc", title="Portfolio review")
    listed = service.list_conversations(user=_user())

    assert created["title"] == "Portfolio review"
    assert listed[0]["id"] == created["id"]
    assert listed[0]["walletAddress"] == "wallet-abc"
    assert listed[0]["messageCount"] == 0


def test_send_message_persists_conversation_and_assistant_reply() -> None:
    supabase = _FakeSupabase()
    copilot = _FakeCopilot(reply="You have 2 active bots.")
    service = CopilotConversationService(copilot=copilot, supabase=supabase)

    result = asyncio.run(service.send_message(user=_user(), content="Summarize my bots"))

    conversation = supabase.tables["copilot_conversations"][0]
    messages = supabase.tables["copilot_messages"]
    assert result["reply"] == "You have 2 active bots."
    assert result["conversation"]["messageCount"] == 2
    assert conversation["title"] == "Summarize my bots"
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert copilot.chat_calls[0]["wallet_address"] == "wallet-abc"


def test_send_message_rolls_older_turns_into_summary_before_chat() -> None:
    supabase = _FakeSupabase()
    copilot = _FakeCopilot()
    service = CopilotConversationService(copilot=copilot, supabase=supabase)
    user = _user()

    created = service.create_conversation(user=user, wallet_address="wallet-abc", title="Long session")
    conversation_id = created["id"]
    long_text = "x" * 60_000
    for index in range(8):
        supabase.insert(
            "copilot_messages",
            {
                "id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "role": "user" if index % 2 == 0 else "assistant",
                "content": f"turn-{index} {long_text}",
                "tool_calls_json": [],
                "follow_ups_json": [],
                "provider": None,
                "token_estimate": 15_000,
                "created_at": _utc_now(),
            },
        )
    supabase.update(
        "copilot_conversations",
        {
            "message_count": 8,
            "latest_message_at": _utc_now(),
            "updated_at": _utc_now(),
        },
        filters={"id": conversation_id},
    )

    result = asyncio.run(
        service.send_message(
            user=user,
            conversation_id=conversation_id,
            content="Use the full session context",
        )
    )

    conversation = supabase.maybe_one("copilot_conversations", filters={"id": conversation_id})
    assert result["conversationId"] == conversation_id
    assert conversation is not None
    assert conversation["summary_message_count"] == 3
    assert conversation["context_summary"] == "Rolled summary"
    assert len(copilot.summary_calls) == 1
    assert copilot.chat_calls[0]["messages"][0]["content"].startswith("CONTEXT_SUMMARY")
    assert len(copilot.chat_calls[0]["messages"]) == 7
