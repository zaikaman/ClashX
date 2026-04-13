from __future__ import annotations

from src.workers.bot_runtime_worker import BotRuntimeWorker


def test_capture_trade_close_notifications_classifies_take_profit() -> None:
    worker = BotRuntimeWorker.__new__(BotRuntimeWorker)

    runtime_state, notifications = worker._capture_trade_close_notifications(
        runtime_state={
            "managed_positions": {
                "BTC": {
                    "take_profit_client_order_id": "tp-1",
                    "stop_loss_client_order_id": "sl-1",
                }
            }
        },
        history_rows=[
            {
                "history_id": "hist-1",
                "symbol": "BTC",
                "event_kind": "close",
                "position_side": "long",
                "amount": 0.25,
                "price": 64000,
                "pnl": 125.5,
                "client_order_id": "tp-1",
                "created_at": "2026-04-13T13:10:00+00:00",
            }
        ],
        notified_after="2026-04-13T13:00:00+00:00",
    )

    assert notifications == [
        {
            "symbol": "BTC",
            "reason": "take_profit",
            "quantity": 0.25,
            "position_side": "long",
            "realized_pnl": 125.5,
            "created_at": "2026-04-13T13:10:00+00:00",
        }
    ]
    assert runtime_state["telegram_notified_closure_keys"] == ["history:hist-1"]


def test_capture_trade_close_notifications_skips_duplicate_history() -> None:
    worker = BotRuntimeWorker.__new__(BotRuntimeWorker)

    runtime_state, notifications = worker._capture_trade_close_notifications(
        runtime_state={
            "managed_positions": {
                "ETH": {
                    "take_profit_client_order_id": "tp-2",
                    "stop_loss_client_order_id": "sl-2",
                }
            },
            "telegram_notified_closure_keys": ["history:hist-2"],
        },
        history_rows=[
            {
                "history_id": "hist-2",
                "symbol": "ETH",
                "event_kind": "close",
                "position_side": "short",
                "amount": 1.0,
                "price": 3000,
                "pnl": -40,
                "client_order_id": "sl-2",
                "created_at": "2026-04-13T13:15:00+00:00",
            }
        ],
        notified_after="2026-04-13T13:00:00+00:00",
    )

    assert notifications == []
    assert runtime_state["telegram_notified_closure_keys"] == ["history:hist-2"]
