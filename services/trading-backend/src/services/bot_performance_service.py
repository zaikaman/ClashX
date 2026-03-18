from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.services.pacifica_client import PacificaClient, PacificaClientError
from src.services.supabase_rest import SupabaseRestClient


class BotPerformanceService:
    def __init__(self, pacifica_client: PacificaClient | None = None, supabase: SupabaseRestClient | None = None) -> None:
        self._pacifica = pacifica_client or PacificaClient()
        self._supabase = supabase or SupabaseRestClient()

    async def calculate_runtime_performance(self, runtime: dict[str, Any]) -> dict[str, Any]:
        events = self._supabase.select(
            "bot_execution_events",
            filters={"runtime_id": runtime["id"], "event_type": "action.executed"},
            order="created_at.asc",
            limit=1000,
        )

        order_history_cache: dict[int, list[dict[str, Any]]] = {}
        positions: dict[str, dict[str, float]] = {}
        realized_pnl = 0.0
        close_events: list[dict[str, Any]] = []

        for event in events:
            event_realized = 0.0
            event_closed = False
            fills = await self._resolve_event_fills(event, order_history_cache)
            for fill in fills:
                applied = self._apply_fill(positions, fill)
                event_realized += applied["realized_pnl"]
                event_closed = event_closed or applied["closed"]
            if event_closed:
                close_events.append(
                    {
                        "created_at": event.get("created_at"),
                        "pnl": round(event_realized, 8),
                    }
                )
            realized_pnl += event_realized

        market_lookup = await self._load_market_lookup()
        live_position_lookup, live_positions_loaded = await self._load_live_position_lookup(runtime)
        open_positions: list[dict[str, Any]] = []
        unrealized_pnl = 0.0
        for symbol, state in positions.items():
            quantity = float(state.get("quantity") or 0.0)
            entry_price = float(state.get("entry_price") or 0.0)
            if abs(quantity) <= 1e-12 or entry_price <= 0:
                continue
            live_position = live_position_lookup.get(symbol)
            if live_position is not None:
                live_amount = abs(float(live_position.get("amount") or 0.0))
                live_side = self._normalize_position_side(live_position.get("side"))
                runtime_side = "long" if quantity > 0 else "short"
                if live_amount <= 1e-12 or live_side != runtime_side:
                    continue
                size = min(abs(quantity), live_amount)
                if size <= 1e-12:
                    continue
                live_entry_price = float(live_position.get("entry_price") or 0.0)
                live_mark_price = float(live_position.get("mark_price") or 0.0)
                if live_entry_price > 0:
                    entry_price = live_entry_price
                mark_price = live_mark_price if live_mark_price > 0 else live_entry_price
            elif live_positions_loaded:
                continue
            else:
                size = abs(quantity)
                mark_price = float((market_lookup.get(symbol) or {}).get("mark_price") or 0.0)
                if mark_price <= 0:
                    mark_price = entry_price
            side = "long" if quantity > 0 else "short"
            pnl = (mark_price - entry_price) * size if quantity > 0 else (entry_price - mark_price) * size
            unrealized_pnl += pnl
            open_positions.append(
                {
                    "symbol": symbol,
                    "side": side,
                    "amount": round(size, 8),
                    "entry_price": round(entry_price, 8),
                    "mark_price": round(mark_price, 8),
                    "unrealized_pnl": round(pnl, 8),
                }
            )

        return {
            "pnl_total": round(realized_pnl + unrealized_pnl, 2),
            "pnl_realized": round(realized_pnl, 2),
            "pnl_unrealized": round(unrealized_pnl, 2),
            "win_streak": self._compute_win_streak(close_events),
            "positions": open_positions,
        }

    async def _resolve_event_fills(
        self,
        event: dict[str, Any],
        order_history_cache: dict[int, list[dict[str, Any]]],
    ) -> list[dict[str, Any]]:
        order_id = self._extract_order_id(event)
        if order_id is not None:
            if order_id not in order_history_cache:
                order_history_cache[order_id] = await self._load_order_history(order_id)
            fills = [row for row in order_history_cache[order_id] if self._is_usable_fill(row)]
            if fills:
                return fills
        fallback = self._build_fallback_fill(event)
        return [fallback] if fallback is not None else []

    async def _load_order_history(self, order_id: int) -> list[dict[str, Any]]:
        try:
            rows = await self._pacifica.get_order_history_by_id(order_id)
        except PacificaClientError:
            return []
        fills = [row for row in rows if self._is_fill_event(row)]
        fills.sort(key=lambda row: str(row.get("created_at") or ""))
        return fills

    async def _load_market_lookup(self) -> dict[str, dict[str, Any]]:
        try:
            markets = await self._pacifica.get_markets()
        except PacificaClientError:
            return {}
        return {
            self._normalize_symbol(item.get("symbol") or item.get("display_symbol")): item
            for item in markets
            if isinstance(item, dict)
        }

    async def _load_live_position_lookup(self, runtime: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], bool]:
        wallet_address = str(runtime.get("wallet_address") or "").strip()
        if not wallet_address:
            return {}, False
        try:
            positions = await self._pacifica.get_positions(wallet_address)
        except PacificaClientError:
            return {}, False
        return (
            {
            self._normalize_symbol(item.get("symbol")): item
            for item in positions
            if isinstance(item, dict) and self._normalize_symbol(item.get("symbol"))
            },
            True,
        )

    def _apply_fill(self, positions: dict[str, dict[str, float]], fill: dict[str, Any]) -> dict[str, Any]:
        symbol = self._normalize_symbol(fill.get("symbol"))
        side = str(fill.get("side") or "").lower().strip()
        amount = float(fill.get("amount") or 0.0)
        price = float(fill.get("price") or 0.0)
        reduce_only = bool(fill.get("reduce_only", False))
        if not symbol or side not in {"bid", "ask", "long", "short"} or amount <= 0 or price <= 0:
            return {"realized_pnl": 0.0, "closed": False}

        direction = 1.0 if side in {"bid", "long"} else -1.0
        delta = direction * amount
        state = positions.setdefault(symbol, {"quantity": 0.0, "entry_price": 0.0})
        quantity = float(state["quantity"])
        entry_price = float(state["entry_price"])
        realized_pnl = 0.0
        closed = False

        if abs(quantity) <= 1e-12:
            if reduce_only:
                return {"realized_pnl": 0.0, "closed": False}
            state["quantity"] = delta
            state["entry_price"] = price
            return {"realized_pnl": 0.0, "closed": False}

        same_direction = quantity * delta > 0
        if same_direction:
            if reduce_only:
                return {"realized_pnl": 0.0, "closed": False}
            combined = abs(quantity) + abs(delta)
            weighted_entry = ((abs(quantity) * entry_price) + (abs(delta) * price)) / combined
            state["quantity"] = quantity + delta
            state["entry_price"] = weighted_entry
            return {"realized_pnl": 0.0, "closed": False}

        close_size = min(abs(quantity), abs(delta))
        realized_pnl = (price - entry_price) * close_size * (1.0 if quantity > 0 else -1.0)
        closed = close_size > 0
        remaining = abs(delta) - close_size
        if remaining <= 1e-12 or reduce_only:
            next_quantity = quantity + delta
            if abs(next_quantity) <= 1e-12:
                state["quantity"] = 0.0
                state["entry_price"] = 0.0
            else:
                state["quantity"] = next_quantity
            return {"realized_pnl": realized_pnl, "closed": closed}

        state["quantity"] = (1.0 if delta > 0 else -1.0) * remaining
        state["entry_price"] = price
        return {"realized_pnl": realized_pnl, "closed": closed}

    def _build_fallback_fill(self, event: dict[str, Any]) -> dict[str, Any] | None:
        result_payload = event.get("result_payload") if isinstance(event.get("result_payload"), dict) else {}
        execution_meta = result_payload.get("execution_meta") if isinstance(result_payload.get("execution_meta"), dict) else {}
        payload = result_payload.get("payload") if isinstance(result_payload.get("payload"), dict) else {}
        source = execution_meta or payload
        symbol = self._normalize_symbol(source.get("symbol"))
        side = str(source.get("side") or "").lower().strip()
        amount = self._to_float(source.get("amount"))
        price = self._to_float(source.get("reference_price")) or self._to_float(source.get("price"))
        reduce_only = bool(source.get("reduce_only", False))
        if not symbol or side not in {"bid", "ask", "long", "short"} or amount <= 0 or price <= 0:
            return None
        return {
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "price": price,
            "reduce_only": reduce_only,
            "event_type": "fallback",
            "created_at": event.get("created_at") or datetime.now(tz=UTC).isoformat(),
        }

    @staticmethod
    def _extract_order_id(event: dict[str, Any]) -> int | None:
        result_payload = event.get("result_payload") if isinstance(event.get("result_payload"), dict) else {}
        response = result_payload.get("response") if isinstance(result_payload.get("response"), dict) else {}
        candidates = (
            response.get("order_id"),
            response.get("orderId"),
            result_payload.get("request_id"),
        )
        for candidate in candidates:
            try:
                if candidate is None or candidate == "":
                    continue
                return int(candidate)
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _is_fill_event(row: dict[str, Any]) -> bool:
        event_type = str(row.get("event_type") or "").lower()
        return event_type not in {"", "make", "cancel", "cancelled"}

    @classmethod
    def _is_usable_fill(cls, row: dict[str, Any]) -> bool:
        if not cls._is_fill_event(row):
            return False
        side = str(row.get("side") or "").lower().strip()
        amount = cls._to_float(row.get("amount"))
        price = cls._to_float(row.get("price"))
        return side in {"bid", "ask", "long", "short"} and amount > 0 and price > 0

    @staticmethod
    def _compute_win_streak(close_events: list[dict[str, Any]]) -> int:
        streak = 0
        for event in sorted(close_events, key=lambda item: str(item.get("created_at") or ""), reverse=True):
            pnl = float(event.get("pnl") or 0.0)
            if pnl > 0:
                streak += 1
                continue
            break
        return streak

    @staticmethod
    def _normalize_symbol(value: Any) -> str:
        return str(value or "").upper().replace("-PERP", "").strip()

    @staticmethod
    def _normalize_position_side(value: Any) -> str:
        normalized = str(value or "").lower().strip()
        if normalized in {"bid", "long", "buy"}:
            return "long"
        if normalized in {"ask", "short", "sell"}:
            return "short"
        return normalized

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            if value is None or value == "":
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0
