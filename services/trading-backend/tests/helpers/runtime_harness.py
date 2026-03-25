from __future__ import annotations

import asyncio
from copy import deepcopy
from typing import Any

from src.workers.bot_runtime_worker import BotRuntimeWorker

from tests.helpers.runtime_fakes import (
    FakeAuthService,
    FakeCoordinationService,
    FakeIndicatorContextService,
    FakePacificaClient,
    FakeSupabaseRestClient,
)


class RuntimeHarness:
    def __init__(self) -> None:
        self.supabase = FakeSupabaseRestClient(
            {
                "bot_definitions": [],
                "bot_runtimes": [],
                "bot_execution_events": [],
            }
        )
        self.pacifica = FakePacificaClient()
        self.auth = FakeAuthService()
        self.worker = BotRuntimeWorker()
        self.worker._supabase = self.supabase
        self.worker._engine._supabase = self.supabase
        self.worker._auth = self.auth
        self.worker._pacifica = self.pacifica
        self.worker._indicator_context = FakeIndicatorContextService()
        self.worker._coordination = FakeCoordinationService()
        self.bot_id = "bot-1"
        self.runtime_id = "runtime-1"
        self.wallet_address = "wallet-1"
        self.user_id = "user-1"
        self._seed_bot()
        self._seed_runtime()

    def with_bot(
        self,
        *,
        conditions: list[dict[str, Any]],
        actions: list[dict[str, Any]],
        risk_policy: dict[str, Any] | None = None,
    ) -> RuntimeHarness:
        self.supabase.tables["bot_definitions"] = [
            {
                "id": self.bot_id,
                "user_id": self.user_id,
                "wallet_address": self.wallet_address,
                "rules_json": {
                    "conditions": deepcopy(conditions),
                    "actions": deepcopy(actions),
                },
            }
        ]
        runtime = self.supabase.tables["bot_runtimes"][0]
        runtime["risk_policy_json"] = deepcopy(risk_policy or {})
        return self

    def with_market(
        self,
        *,
        symbol: str = "BTC",
        mark_price: float = 105_000.0,
        lot_size: float = 0.001,
        min_order_size: float = 0.001,
        tick_size: float = 0.5,
        max_leverage: int = 5,
    ) -> RuntimeHarness:
        self.pacifica._markets = [
            {
                "symbol": f"{symbol}-PERP",
                "display_symbol": f"{symbol}-PERP",
                "mark_price": mark_price,
                "lot_size": lot_size,
                "min_order_size": min_order_size,
                "tick_size": tick_size,
                "max_leverage": max_leverage,
            }
        ]
        return self

    def with_position(
        self,
        *,
        symbol: str = "BTC",
        side: str = "bid",
        amount: float = 0.002,
        entry_price: float = 105_000.0,
        mark_price: float = 105_000.0,
    ) -> RuntimeHarness:
        self.pacifica._position = {
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "entry_price": entry_price,
            "mark_price": mark_price,
            "margin": 105.0,
            "isolated": True,
            "created_at": "2026-03-16T00:00:00Z",
            "updated_at": "2026-03-16T00:00:00Z",
        }
        return self

    def with_open_orders(self, orders: list[dict[str, Any]]) -> RuntimeHarness:
        self.pacifica._open_orders = [deepcopy(item) for item in orders]
        return self

    def with_auth(self, *, active: bool) -> RuntimeHarness:
        self.auth.active_wallets = {self.wallet_address} if active else set()
        return self

    def with_margin_settings(self, settings: list[dict[str, Any]]) -> RuntimeHarness:
        self.pacifica._margin_settings = [deepcopy(item) for item in settings]
        return self

    def process_once(self) -> None:
        asyncio.run(self.worker._process_runtime(None, deepcopy(self.supabase.tables["bot_runtimes"][0])))

    def execute_action(
        self,
        action: dict[str, Any],
        *,
        runtime_state: dict[str, Any] | None = None,
        position_lookup: dict[str, dict[str, Any]] | None = None,
        open_order_lookup: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        credentials = self.auth.get_trading_credentials(None, self.wallet_address)
        if credentials is None:
            raise RuntimeError("Harness credentials are inactive")
        market_lookup = self.worker._build_market_lookup(asyncio.run(self.pacifica.get_markets()))
        return asyncio.run(
            self.worker._execute_action(
                runtime={"id": self.runtime_id},
                runtime_state=runtime_state or {},
                action=deepcopy(action),
                credentials=credentials,
                market_lookup=market_lookup,
                position_lookup=position_lookup or {},
                open_order_lookup=open_order_lookup,
            )
        )

    def pacifica_calls(self) -> list[dict[str, Any]]:
        return self.pacifica.order_calls

    def batch_calls(self) -> list[list[dict[str, Any]]]:
        return self.pacifica.batch_order_calls

    def execution_events(self) -> list[dict[str, Any]]:
        return self.supabase.tables["bot_execution_events"]

    def runtime_state(self) -> dict[str, Any]:
        runtime = self.supabase.tables["bot_runtimes"][0]
        policy = runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
        state = policy.get("_runtime_state") if isinstance(policy.get("_runtime_state"), dict) else {}
        return deepcopy(state)

    def _seed_bot(self) -> None:
        self.supabase.tables["bot_definitions"] = [
            {
                "id": self.bot_id,
                "user_id": self.user_id,
                "wallet_address": self.wallet_address,
                "rules_json": {
                    "conditions": [{"type": "price_below", "symbol": "BTC", "value": 200000}],
                    "actions": [{"type": "open_long", "symbol": "BTC", "size_usd": 105.0, "leverage": 3}],
                },
            }
        ]

    def _seed_runtime(self) -> None:
        self.supabase.tables["bot_runtimes"] = [
            {
                "id": self.runtime_id,
                "bot_definition_id": self.bot_id,
                "user_id": self.user_id,
                "wallet_address": self.wallet_address,
                "status": "active",
                "mode": "live",
                "risk_policy_json": {"max_open_positions": 1, "cooldown_seconds": 0},
                "updated_at": "2026-03-18T07:00:00+00:00",
            }
        ]

