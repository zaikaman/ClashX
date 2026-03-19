from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace
from typing import Any

from src.services.pacifica_client import PacificaClient
from src.workers.bot_runtime_worker import BotRuntimeWorker


def test_normalize_payload_canonicalizes_custom_client_order_ids() -> None:
    client = object.__new__(PacificaClient)
    client.settings = SimpleNamespace(pacifica_builder_code="")

    normalized = client._normalize_payload(
        "set_position_tpsl",
        {
            "account": "wallet-1",
            "symbol": "BTC",
            "side": "ask",
            "take_profit": {
                "stop_price": 120_000,
                "amount": 0.1,
                "client_order_id": "maker-entry-001",
            },
            "stop_loss": {
                "stop_price": 99_800,
                "amount": 0.1,
                "client_order_id": "maker-entry-001",
            },
        },
        account="wallet-1",
    )

    take_profit_id = normalized["take_profit"]["client_order_id"]
    stop_loss_id = normalized["stop_loss"]["client_order_id"]

    assert take_profit_id == PacificaClient.canonicalize_client_order_id(
        "maker-entry-001",
        account="wallet-1",
        symbol="BTC",
        scope="take_profit.client_order_id",
    )
    assert stop_loss_id == PacificaClient.canonicalize_client_order_id(
        "maker-entry-001",
        account="wallet-1",
        symbol="BTC",
        scope="stop_loss.client_order_id",
    )
    assert take_profit_id != stop_loss_id
    assert str(uuid.UUID(take_profit_id)) == take_profit_id
    assert str(uuid.UUID(stop_loss_id)) == stop_loss_id


def test_normalize_payload_preserves_existing_uuid_client_order_id() -> None:
    client = object.__new__(PacificaClient)
    client.settings = SimpleNamespace(pacifica_builder_code="")
    existing = str(uuid.uuid4())

    normalized = client._normalize_payload(
        "create_order",
        {
            "account": "wallet-1",
            "symbol": "BTC",
            "side": "bid",
            "price": 100_000,
            "amount": 0.1,
            "tif": "GTC",
            "reduce_only": False,
            "client_order_id": existing,
        },
        account="wallet-1",
    )

    assert normalized["client_order_id"] == existing


class _FakePacificaClient:
    def __init__(self, response_payload: dict[str, Any]) -> None:
        self.response_payload = response_payload
        self.requests: list[dict[str, Any]] = []

    async def place_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.requests.append(payload)
        return {
            "status": "submitted",
            "request_id": "req-1",
            "network": "testnet",
            "payload": self.response_payload,
        }


async def _noop_ensure_leverage(**_: Any) -> None:
    return None


def test_execute_action_uses_normalized_client_order_id_from_client_payload() -> None:
    normalized_id = str(uuid.uuid4())
    worker = object.__new__(BotRuntimeWorker)
    worker._pacifica = _FakePacificaClient({"client_order_id": normalized_id})
    worker._ensure_leverage = _noop_ensure_leverage

    response = asyncio.run(
        worker._execute_action(
            runtime={"id": "runtime-1"},
            runtime_state={},
            action={
                "type": "place_limit_order",
                "symbol": "BTC",
                "side": "long",
                "price": 99_500,
                "quantity": 0.01,
                "leverage": 3,
                "reduce_only": False,
                "client_order_id": "maker-entry-001",
            },
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"lot_size": 0.001, "mark_price": 105_000}},
            position_lookup={},
        )
    )

    assert response["execution_meta"]["client_order_id"] == normalized_id


def test_execute_action_uses_normalized_tpsl_ids_from_client_payload() -> None:
    take_profit_id = str(uuid.uuid4())
    stop_loss_id = str(uuid.uuid4())
    worker = object.__new__(BotRuntimeWorker)
    worker._pacifica = _FakePacificaClient(
        {
            "take_profit": {"client_order_id": take_profit_id},
            "stop_loss": {"client_order_id": stop_loss_id},
        }
    )

    response = asyncio.run(
        worker._execute_action(
            runtime={"id": "runtime-1"},
            runtime_state={
                "managed_positions": {
                    "BTC": {
                        "symbol": "BTC",
                        "amount": 0.01,
                        "side": "bid",
                        "entry_client_order_id": "maker-entry-001",
                    }
                }
            },
            action={
                "type": "set_tpsl",
                "symbol": "BTC",
                "take_profit_pct": 1.8,
                "stop_loss_pct": 0.9,
            },
            credentials={
                "account_address": "wallet-1",
                "agent_wallet_address": "agent-1",
                "agent_private_key": "secret",
            },
            market_lookup={"BTC": {"tick_size": 0.5, "mark_price": 105_000}},
            position_lookup={
                "BTC": {
                    "symbol": "BTC",
                    "side": "bid",
                    "amount": 0.01,
                    "mark_price": 105_000,
                }
            },
        )
    )

    assert response["execution_meta"]["take_profit_client_order_id"] == take_profit_id
    assert response["execution_meta"]["stop_loss_client_order_id"] == stop_loss_id
