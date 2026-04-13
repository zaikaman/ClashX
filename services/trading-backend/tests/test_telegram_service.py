from __future__ import annotations

import asyncio
import logging
from types import SimpleNamespace
from typing import Any

import pytest

import src.services.telegram_service as telegram_module
from src.services.telegram_service import TelegramRateLimitError, TelegramService


class _FakeSupabase:
    def __init__(self) -> None:
        self.users: list[dict[str, Any]] = []

    def maybe_one(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        del columns, order, cache_ttl_seconds
        rows = self.select(table, filters=filters, limit=1)
        return rows[0] if rows else None

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: dict[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        del columns, order, cache_ttl_seconds
        if table != "users":
            raise AssertionError(f"unexpected table {table}")
        rows = [dict(row) for row in self.users if self._matches(row, filters or {})]
        return rows[:limit] if limit is not None else rows

    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
        returning: str = "representation",
    ) -> list[dict[str, Any]]:
        del upsert, on_conflict, returning
        if table != "users":
            raise AssertionError(f"unexpected table {table}")
        rows = payload if isinstance(payload, list) else [payload]
        inserted: list[dict[str, Any]] = []
        for row in rows:
            copy = dict(row)
            self.users.append(copy)
            inserted.append(dict(copy))
        return inserted

    def update(
        self,
        table: str,
        values: dict[str, Any],
        *,
        filters: dict[str, Any],
        returning: str = "representation",
    ) -> list[dict[str, Any]]:
        del returning
        if table != "users":
            raise AssertionError(f"unexpected table {table}")
        updated: list[dict[str, Any]] = []
        for row in self.users:
            if self._matches(row, filters):
                row.update(values)
                updated.append(dict(row))
        return updated

    @staticmethod
    def _matches(row: dict[str, Any], filters: dict[str, Any]) -> bool:
        for key, value in filters.items():
            if isinstance(value, tuple):
                operator, operand = value
                if operator != "in":
                    raise AssertionError(f"unsupported operator {operator}")
                if row.get(key) not in operand:
                    return False
                continue
            if row.get(key) != value:
                return False
        return True


def _fake_settings() -> SimpleNamespace:
    return SimpleNamespace(
        telegram_bot_token="telegram-token",
        telegram_bot_username="clash_x_bot",
        telegram_webhook_url="https://api.example.com/api/telegram/webhook",
        telegram_webhook_secret="secret-token",
        telegram_link_code_ttl_minutes=20,
    )


def test_issue_link_code_and_handle_start_links_wallet(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_supabase = _FakeSupabase()
    service = TelegramService(supabase=fake_supabase)
    sent_messages: list[str] = []

    async def fake_send_message(*, chat_id: int, text: str) -> None:
        assert chat_id == 777
        sent_messages.append(text)

    monkeypatch.setattr(telegram_module, "get_settings", _fake_settings)
    monkeypatch.setattr(service, "_send_message", fake_send_message)

    status = service.issue_link_code(wallet_address="wallet-12345678")
    assert status["deeplink_url"] is not None
    code = str(fake_supabase.users[0]["telegram_link_code"])
    assert code

    asyncio.run(
        service.handle_webhook(
            update={
                "message": {
                    "chat": {"id": 777, "type": "private"},
                    "from": {"username": "relay_user", "first_name": "Relay"},
                    "text": f"/start connect_{code}",
                }
            },
            secret_token="secret-token",
        )
    )

    stored_user = fake_supabase.users[0]
    assert stored_user["telegram_chat_id"] == 777
    assert stored_user["telegram_username"] == "relay_user"
    assert stored_user["telegram_link_code"] is None
    assert any("linked to" in message for message in sent_messages)


def test_notify_user_respects_disabled_preference(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_supabase = _FakeSupabase()
    fake_supabase.users.append(
        {
            "id": "user-1",
            "wallet_address": "wallet-12345678",
            "telegram_chat_id": 777,
            "telegram_chat_type": "private",
            "telegram_username": "relay_user",
            "telegram_notifications_enabled": True,
            "telegram_notification_prefs": {
                "critical_alerts": False,
                "execution_failures": True,
                "copy_activity": True,
            },
        }
    )
    service = TelegramService(supabase=fake_supabase)
    sent_messages: list[str] = []

    async def fake_send_message(*, chat_id: int, text: str) -> None:
        del chat_id
        sent_messages.append(text)

    monkeypatch.setattr(service, "_send_message", fake_send_message)

    delivered = asyncio.run(
        service.notify_user(
            user_id="user-1",
            event="bot.runtime.stopped",
            payload={"runtime_id": "runtime-1", "error_reason": "risk breach"},
        )
    )

    assert delivered is False
    assert sent_messages == []


def test_configure_bot_skips_set_webhook_when_url_matches(monkeypatch: pytest.MonkeyPatch) -> None:
    service = TelegramService(supabase=_FakeSupabase())
    requests: list[tuple[str, dict[str, Any]]] = []

    async def fake_telegram_request(method: str, payload: dict[str, Any], *, settings) -> dict[str, Any]:
        del settings
        requests.append((method, dict(payload)))
        if method == "getWebhookInfo":
            return {"url": "https://api.example.com/api/telegram/webhook"}
        return {}

    monkeypatch.setattr(service, "_telegram_request", fake_telegram_request)

    asyncio.run(service.configure_bot(settings=_fake_settings()))

    assert requests == [
        ("setMyCommands", {"commands": telegram_module.BOT_COMMANDS}),
        ("getWebhookInfo", {}),
    ]


def test_configure_bot_logs_warning_on_rate_limit(monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture) -> None:
    service = TelegramService(supabase=_FakeSupabase())

    async def fake_telegram_request(method: str, payload: dict[str, Any], *, settings) -> dict[str, Any]:
        del payload, settings
        if method == "setWebhook":
            raise TelegramRateLimitError(method=method, retry_after_seconds=30, description="Too Many Requests: retry later")
        if method == "getWebhookInfo":
            return {"url": ""}
        return {}

    monkeypatch.setattr(service, "_telegram_request", fake_telegram_request)

    with caplog.at_level(logging.WARNING):
        asyncio.run(service.configure_bot(settings=_fake_settings()))

    assert "Telegram bot configuration rate limited" in caplog.text
    assert "setWebhook" in caplog.text


def test_render_trade_open_notification() -> None:
    service = TelegramService(supabase=_FakeSupabase())

    rendered = service._render_notification_message(
        event="bot.execution.success",
        payload={
            "request_payload": {"type": "open_long", "symbol": "btc"},
            "result_payload": {
                "execution_meta": {
                    "side": "bid",
                    "amount": 0.25,
                    "reduce_only": False,
                }
            },
        },
    )

    assert rendered == "Trade opened\nBTC long\nSize: 0.2500"


def test_render_tpsl_armed_notification() -> None:
    service = TelegramService(supabase=_FakeSupabase())

    rendered = service._render_notification_message(
        event="bot.execution.success",
        payload={
            "request_payload": {"type": "set_tpsl", "symbol": "eth"},
            "result_payload": {"execution_meta": {"amount": 1.5}},
        },
    )

    assert rendered == "Protection armed\nETH\nTP and SL orders were placed for 1.5000."


def test_render_position_closed_notification() -> None:
    service = TelegramService(supabase=_FakeSupabase())

    rendered = service._render_notification_message(
        event="bot.position.closed",
        payload={
            "symbol": "sol",
            "reason": "take_profit",
            "quantity": 3,
            "position_side": "long",
            "realized_pnl": 42.5,
        },
    )

    assert rendered == "Position closed\nSOL long\nReason: take profit\nSize: 3.0000\nRealized PnL: +$42.50"
