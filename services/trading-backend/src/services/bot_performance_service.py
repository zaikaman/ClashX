from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.services.bot_risk_service import BotRiskService
from src.services.pacifica_client import PacificaClient, PacificaClientError
from src.services.supabase_rest import SupabaseRestClient


class BotPerformanceService:
    def __init__(self, pacifica_client: PacificaClient | None = None, supabase: SupabaseRestClient | None = None) -> None:
        self._pacifica = pacifica_client or PacificaClient()
        self._supabase = supabase or SupabaseRestClient()
        self._risk = BotRiskService()

    async def calculate_runtime_performance(self, runtime: dict[str, Any]) -> dict[str, Any]:
        return await self.calculate_runtime_performance_with_context(
            runtime,
            market_lookup=None,
            live_position_lookup=None,
            manual_close_history=None,
        )

    async def calculate_runtime_performance_with_context(
        self,
        runtime: dict[str, Any],
        *,
        market_lookup: dict[str, dict[str, Any]] | None,
        live_position_lookup: dict[str, dict[str, Any]] | None,
        manual_close_history: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        events = self._supabase.select(
            "bot_execution_events",
            filters={"runtime_id": runtime["id"], "event_type": "action.executed"},
            order="created_at.asc",
            limit=1000,
        )

        order_history_cache: dict[int, list[dict[str, Any]]] = {}
        bot_records: list[dict[str, Any]] = []
        bot_positions: dict[str, dict[str, float]] = {}
        realized_pnl = 0.0
        close_events: list[dict[str, Any]] = []

        for event in events:
            event_realized = 0.0
            event_closed = False
            fills = await self._resolve_event_fills(event, order_history_cache)
            for fill in fills:
                applied = self._apply_fill(bot_positions, fill)
                bot_records.extend(self._build_bot_records(event, fill, applied, event.get("created_at")))
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

        manual_close_records = await self._load_manual_close_records(
            runtime,
            bot_records,
            history_rows=manual_close_history,
        )
        lots, closures, close_events = self._build_runtime_ledger(runtime, bot_records, manual_close_records, close_events)
        self._persist_runtime_ledger(runtime, events, lots, closures)
        realized_pnl = round(sum(float(item.get("realized_pnl") or 0.0) for item in closures), 8)

        resolved_market_lookup = market_lookup or await self._load_market_lookup()
        if live_position_lookup is None:
            resolved_live_position_lookup, live_positions_loaded = await self._load_live_position_lookup(runtime)
        else:
            resolved_live_position_lookup = live_position_lookup
            live_positions_loaded = True
        open_positions: list[dict[str, Any]] = []
        unrealized_pnl = 0.0
        open_lots = [item for item in lots if self._to_float(item.get("quantity_remaining")) > 1e-12]
        position_states = self._summarize_open_lots(open_lots)
        for symbol, state in position_states.items():
            quantity = float(state.get("quantity") or 0.0)
            entry_price = float(state.get("entry_price") or 0.0)
            if abs(quantity) <= 1e-12 or entry_price <= 0:
                continue
            live_position = resolved_live_position_lookup.get(symbol)
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
                mark_price = float((resolved_market_lookup.get(symbol) or {}).get("mark_price") or 0.0)
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

        total_pnl = realized_pnl + unrealized_pnl
        runtime_policy = runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
        allocated_capital = float(self._risk.normalize_policy(runtime_policy).get("allocated_capital_usd") or 0.0)

        return {
            "pnl_total": round(total_pnl, 2),
            "pnl_total_pct": round((total_pnl / allocated_capital * 100.0) if allocated_capital > 0 else 0.0, 4),
            "pnl_realized": round(realized_pnl, 2),
            "pnl_unrealized": round(unrealized_pnl, 2),
            "win_streak": self._compute_win_streak(close_events),
            "positions": open_positions,
        }

    def _build_runtime_ledger(
        self,
        runtime: dict[str, Any],
        bot_records: list[dict[str, Any]],
        manual_close_records: list[dict[str, Any]],
        initial_close_events: list[dict[str, Any]],
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
        open_lots_by_symbol: dict[str, list[dict[str, Any]]] = {}
        all_lots: list[dict[str, Any]] = []
        closures: list[dict[str, Any]] = []
        close_events = list(initial_close_events)

        for record in sorted([*bot_records, *manual_close_records], key=self._timeline_sort_key):
            fill = record["fill"]
            symbol = self._normalize_symbol(fill.get("symbol"))
            if not symbol:
                continue
            event_kind = str(record.get("event_kind") or "")
            position_side = str(record.get("position_side") or "")
            if event_kind == "open":
                lot = self._make_lot(runtime["id"], record, fill, position_side)
                open_lots_by_symbol.setdefault(symbol, []).append(lot)
                all_lots.append(lot)
                continue
            if event_kind != "close":
                continue
            remaining = self._to_float(fill.get("amount"))
            if remaining <= 1e-12:
                continue
            symbol_lots = open_lots_by_symbol.get(symbol, [])
            matched_realized = 0.0
            for lot in list(symbol_lots):
                if remaining <= 1e-12:
                    break
                if lot["side"] != position_side:
                    continue
                available = self._to_float(lot.get("quantity_remaining"))
                if available <= 1e-12:
                    continue
                matched = min(remaining, available)
                remaining -= matched
                lot["quantity_remaining"] = round(available - matched, 12)
                lot["updated_at"] = self._coerce_iso(record.get("created_at"))
                realized = self._calculate_realized_pnl(position_side, self._to_float(lot.get("entry_price")), self._to_float(fill.get("price")), matched)
                matched_realized += realized
                closures.append(self._make_closure(runtime["id"], lot, record, fill, matched, realized))
            open_lots_by_symbol[symbol] = [item for item in symbol_lots if self._to_float(item.get("quantity_remaining")) > 1e-12]
            if matched_realized:
                close_events.append({"created_at": record.get("created_at"), "pnl": round(matched_realized, 8)})

        return all_lots, closures, close_events

    def _persist_runtime_ledger(
        self,
        runtime: dict[str, Any],
        events: list[dict[str, Any]],
        lots: list[dict[str, Any]],
        closures: list[dict[str, Any]],
    ) -> None:
        runtime_id = runtime["id"]
        self._supabase.delete("bot_trade_closures", filters={"runtime_id": runtime_id})
        self._supabase.delete("bot_trade_lots", filters={"runtime_id": runtime_id})
        self._supabase.delete("bot_trade_sync_state", filters={"runtime_id": runtime_id})
        if lots:
            self._supabase.insert("bot_trade_lots", self._dedupe_rows(lots, key="id"), upsert=True, on_conflict="id")
        if closures:
            self._supabase.insert(
                "bot_trade_closures",
                self._dedupe_rows(closures, key="id"),
                upsert=True,
                on_conflict="id",
            )
        last_execution_at = events[-1].get("created_at") if events else None
        last_history_at = max((item.get("closed_at") for item in closures), default=None)
        self._supabase.insert(
            "bot_trade_sync_state",
            {
                "runtime_id": runtime_id,
                "synced_at": datetime.now(tz=UTC).isoformat(),
                "execution_events_count": len(events),
                "position_history_count": len(closures),
                "last_execution_at": last_execution_at,
                "last_history_at": last_history_at,
                "last_error": None,
            },
            upsert=True,
            on_conflict="runtime_id",
        )

    def _summarize_open_lots(self, lots: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
        states: dict[str, dict[str, float]] = {}
        for lot in lots:
            symbol = self._normalize_symbol(lot.get("symbol"))
            remaining = self._to_float(lot.get("quantity_remaining"))
            entry_price = self._to_float(lot.get("entry_price"))
            side = str(lot.get("side") or "")
            if not symbol or remaining <= 1e-12 or entry_price <= 0 or side not in {"long", "short"}:
                continue
            state = states.setdefault(symbol, {"quantity": 0.0, "entry_notional": 0.0, "entry_price": 0.0})
            signed = remaining if side == "long" else -remaining
            state["quantity"] += signed
            state["entry_notional"] += remaining * entry_price
        for state in states.values():
            size = abs(float(state.get("quantity") or 0.0))
            state["entry_price"] = (float(state.get("entry_notional") or 0.0) / size) if size > 1e-12 else 0.0
        return states

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

    async def _load_manual_close_records(
        self,
        runtime: dict[str, Any],
        bot_records: list[dict[str, Any]],
        *,
        history_rows: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        wallet_address = str(runtime.get("wallet_address") or "").strip()
        if not wallet_address or not bot_records:
            return []
        resolved_history_rows = history_rows
        if resolved_history_rows is None:
            try:
                resolved_history_rows = await self._pacifica.get_position_history(wallet_address, limit=200, offset=0)
            except PacificaClientError:
                return []

        deployed_at = runtime.get("deployed_at")
        normalized_history: list[dict[str, Any]] = []
        for row in resolved_history_rows:
            event_kind, position_side = self._position_history_event_kind(row)
            amount = self._to_float(row.get("amount"))
            price = self._to_float(row.get("price"))
            created_at = row.get("created_at")
            if event_kind not in {"open", "close"} or not position_side or amount <= 0 or price <= 0:
                continue
            if deployed_at and self._timestamp_value(created_at) < self._timestamp_value(deployed_at):
                continue
            normalized_history.append(
                {
                    "symbol": self._normalize_symbol(row.get("symbol")),
                    "event_kind": event_kind,
                    "position_side": position_side,
                    "amount": amount,
                    "remaining_amount": amount,
                    "price": price,
                    "pnl": self._to_float(row.get("pnl")),
                    "history_id": row.get("history_id"),
                    "created_at": created_at,
                }
            )

        self._consume_bot_history_matches(bot_records, normalized_history)

        manual_close_records: list[dict[str, Any]] = []
        for row in normalized_history:
            remaining_amount = self._to_float(row.get("remaining_amount"))
            if row.get("event_kind") != "close" or remaining_amount <= 1e-12:
                continue
            close_side = "short" if row.get("position_side") == "long" else "long"
            manual_close_records.append(
                {
                    "source": "manual",
                    "created_at": row.get("created_at"),
                    "symbol": row.get("symbol"),
                    "event_kind": "close",
                    "position_side": row.get("position_side"),
                    "pnl": float(row.get("pnl") or 0.0) * min(1.0, remaining_amount / max(self._to_float(row.get("amount")), 1e-12)),
                    "source_history_id": row.get("history_id"),
                    "fill": {
                        "symbol": row.get("symbol"),
                        "side": close_side,
                        "amount": remaining_amount,
                        "price": row.get("price"),
                        "reduce_only": True,
                        "event_type": "manual_close",
                        "created_at": row.get("created_at"),
                    },
                }
            )
        return manual_close_records

    def _consume_bot_history_matches(self, bot_records: list[dict[str, Any]], history_rows: list[dict[str, Any]]) -> None:
        for record in sorted(bot_records, key=self._timeline_sort_key):
            remaining = self._to_float(record.get("amount"))
            if remaining <= 1e-12:
                continue
            candidates = [
                row
                for row in history_rows
                if row.get("symbol") == record.get("symbol")
                and row.get("event_kind") == record.get("event_kind")
                and row.get("position_side") == record.get("position_side")
                and self._to_float(row.get("remaining_amount")) > 1e-12
            ]
            candidates.sort(
                key=lambda row: abs(self._timestamp_value(row.get("created_at")) - self._timestamp_value(record.get("created_at")))
            )
            for row in candidates:
                available = self._to_float(row.get("remaining_amount"))
                if available <= 1e-12:
                    continue
                consumed = min(remaining, available)
                row["remaining_amount"] = round(available - consumed, 12)
                remaining -= consumed
                if remaining <= 1e-12:
                    break

    def _build_bot_records(
        self,
        event: dict[str, Any],
        fill: dict[str, Any],
        applied: dict[str, Any],
        created_at: Any,
    ) -> list[dict[str, Any]]:
        symbol = self._normalize_symbol(fill.get("symbol"))
        price = self._to_float(fill.get("price"))
        order_id = self._extract_order_id(event)
        history_id = fill.get("history_id")
        if not symbol or price <= 0:
            return []
        records: list[dict[str, Any]] = []

        open_size = self._to_float(applied.get("open_size"))
        if open_size > 1e-12:
            position_side = self._normalize_position_side(fill.get("side"))
            if position_side in {"long", "short"}:
                records.append(
                    {
                        "source": "bot",
                        "created_at": created_at,
                        "symbol": symbol,
                        "event_kind": "open",
                        "position_side": position_side,
                        "amount": open_size,
                        "source_event_id": event.get("id"),
                        "source_order_id": str(order_id) if order_id is not None else None,
                        "source_history_id": history_id,
                        "fill": {
                            "symbol": symbol,
                            "side": position_side,
                            "amount": open_size,
                            "price": price,
                            "reduce_only": False,
                            "created_at": created_at,
                        },
                    }
                )

        close_size = self._to_float(applied.get("close_size"))
        closed_position_side = str(applied.get("closed_position_side") or "")
        if close_size > 1e-12 and closed_position_side in {"long", "short"}:
            close_side = "short" if closed_position_side == "long" else "long"
            records.append(
                {
                    "source": "bot",
                    "created_at": created_at,
                    "symbol": symbol,
                    "event_kind": "close",
                    "position_side": closed_position_side,
                    "amount": close_size,
                    "source_event_id": event.get("id"),
                    "source_order_id": str(order_id) if order_id is not None else None,
                    "source_history_id": history_id,
                    "fill": {
                        "symbol": symbol,
                        "side": close_side,
                        "amount": close_size,
                        "price": price,
                        "reduce_only": True,
                        "created_at": created_at,
                    },
                }
            )
        return records

    def _make_lot(self, runtime_id: str, record: dict[str, Any], fill: dict[str, Any], side: str) -> dict[str, Any]:
        source_event_id = record.get("source_event_id")
        source_order_id = record.get("source_order_id")
        source_history_id = record.get("source_history_id")
        opened_at = self._coerce_iso(record.get("created_at"))
        lot_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"lot:{runtime_id}:{record.get('source')}:{source_event_id}:{source_order_id}:{source_history_id}:{record.get('symbol')}:{side}:{record.get('amount')}:{opened_at}",
            )
        )
        return {
            "id": lot_id,
            "runtime_id": runtime_id,
            "symbol": self._normalize_symbol(record.get("symbol")),
            "side": side,
            "opened_at": opened_at,
            "source": record.get("source") or "bot",
            "source_event_id": source_event_id,
            "source_order_id": source_order_id,
            "source_history_id": source_history_id,
            "entry_price": self._to_float(fill.get("price")),
            "quantity_opened": self._to_float(fill.get("amount")),
            "quantity_remaining": self._to_float(fill.get("amount")),
            "created_at": datetime.now(tz=UTC).isoformat(),
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }

    def _make_closure(
        self,
        runtime_id: str,
        lot: dict[str, Any],
        record: dict[str, Any],
        fill: dict[str, Any],
        quantity_closed: float,
        realized_pnl: float,
    ) -> dict[str, Any]:
        source_event_id = record.get("source_event_id")
        source_order_id = record.get("source_order_id")
        source_history_id = record.get("source_history_id")
        closed_at = self._coerce_iso(record.get("created_at"))
        closure_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"closure:{runtime_id}:{lot['id']}:{record.get('source')}:{source_event_id}:{source_order_id}:{source_history_id}:{quantity_closed}:{closed_at}",
            )
        )
        return {
            "id": closure_id,
            "runtime_id": runtime_id,
            "lot_id": lot["id"],
            "symbol": lot["symbol"],
            "side": lot["side"],
            "closed_at": closed_at,
            "source": record.get("source") or "bot",
            "source_event_id": source_event_id,
            "source_order_id": source_order_id,
            "source_history_id": source_history_id,
            "quantity_closed": quantity_closed,
            "entry_price": self._to_float(lot.get("entry_price")),
            "exit_price": self._to_float(fill.get("price")),
            "realized_pnl": realized_pnl,
            "created_at": datetime.now(tz=UTC).isoformat(),
        }

    @staticmethod
    def _calculate_realized_pnl(position_side: str, entry_price: float, exit_price: float, quantity: float) -> float:
        if position_side == "long":
            return (exit_price - entry_price) * quantity
        if position_side == "short":
            return (entry_price - exit_price) * quantity
        return 0.0

    @staticmethod
    def _dedupe_rows(rows: list[dict[str, Any]], *, key: str) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for row in rows:
            identifier = str(row.get(key) or "").strip()
            if not identifier:
                continue
            deduped[identifier] = row
        return list(deduped.values())

    @staticmethod
    def _coerce_iso(value: Any) -> str:
        text = str(value or "").strip()
        return text if text else datetime.now(tz=UTC).isoformat()

    def _apply_fill(self, positions: dict[str, dict[str, float]], fill: dict[str, Any]) -> dict[str, Any]:
        symbol = self._normalize_symbol(fill.get("symbol"))
        side = str(fill.get("side") or "").lower().strip()
        amount = float(fill.get("amount") or 0.0)
        price = float(fill.get("price") or 0.0)
        reduce_only = bool(fill.get("reduce_only", False))
        if not symbol or side not in {"bid", "ask", "long", "short"} or amount <= 0 or price <= 0:
            return {"realized_pnl": 0.0, "closed": False, "open_size": 0.0, "close_size": 0.0, "closed_position_side": None}

        direction = 1.0 if side in {"bid", "long"} else -1.0
        delta = direction * amount
        state = positions.setdefault(symbol, {"quantity": 0.0, "entry_price": 0.0})
        quantity = float(state["quantity"])
        entry_price = float(state["entry_price"])
        realized_pnl = 0.0
        closed = False
        close_size = 0.0
        open_size = 0.0
        closed_position_side = "long" if quantity > 0 else "short" if quantity < 0 else None

        if abs(quantity) <= 1e-12:
            if reduce_only:
                return {"realized_pnl": 0.0, "closed": False, "open_size": 0.0, "close_size": 0.0, "closed_position_side": None}
            state["quantity"] = delta
            state["entry_price"] = price
            open_size = abs(delta)
            return {"realized_pnl": 0.0, "closed": False, "open_size": open_size, "close_size": 0.0, "closed_position_side": None}

        same_direction = quantity * delta > 0
        if same_direction:
            if reduce_only:
                return {"realized_pnl": 0.0, "closed": False, "open_size": 0.0, "close_size": 0.0, "closed_position_side": None}
            combined = abs(quantity) + abs(delta)
            weighted_entry = ((abs(quantity) * entry_price) + (abs(delta) * price)) / combined
            state["quantity"] = quantity + delta
            state["entry_price"] = weighted_entry
            open_size = abs(delta)
            return {"realized_pnl": 0.0, "closed": False, "open_size": open_size, "close_size": 0.0, "closed_position_side": None}

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
            return {
                "realized_pnl": realized_pnl,
                "closed": closed,
                "open_size": 0.0,
                "close_size": close_size,
                "closed_position_side": closed_position_side,
            }

        state["quantity"] = (1.0 if delta > 0 else -1.0) * remaining
        state["entry_price"] = price
        open_size = remaining
        return {
            "realized_pnl": realized_pnl,
            "closed": closed,
            "open_size": open_size,
            "close_size": close_size,
            "closed_position_side": closed_position_side,
        }

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

    @classmethod
    def _position_history_event_kind(cls, row: dict[str, Any]) -> tuple[str | None, str | None]:
        event_type = str(row.get("event_type") or "").lower().strip()
        if event_type.startswith("open_"):
            return "open", "long" if event_type.endswith("long") else "short" if event_type.endswith("short") else None
        if event_type.startswith("close_"):
            return "close", "long" if event_type.endswith("long") else "short" if event_type.endswith("short") else None
        return None, None

    @classmethod
    def _timeline_sort_key(cls, item: dict[str, Any]) -> tuple[float, int]:
        source_rank = 0 if item.get("source") == "bot" else 1
        return cls._timestamp_value(item.get("created_at")), source_rank

    @staticmethod
    def _timestamp_value(value: Any) -> float:
        if isinstance(value, (int, float)):
            numeric = float(value)
            return numeric / 1000.0 if numeric > 10_000_000_000 else numeric
        text = str(value or "").strip()
        if not text:
            return 0.0
        try:
            return float(text)
        except ValueError:
            pass
        normalized = text.replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(normalized).timestamp()
        except ValueError:
            return 0.0

    @classmethod
    def _compute_win_streak(cls, close_events: list[dict[str, Any]]) -> int:
        streak = 0
        for event in sorted(close_events, key=lambda item: cls._timestamp_value(item.get("created_at")), reverse=True):
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
