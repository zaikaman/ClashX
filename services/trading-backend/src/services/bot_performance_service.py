from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.services.bot_risk_service import BotRiskService
from src.services.pacifica_client import PacificaClient, PacificaClientError, get_pacifica_client
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError


class BotPerformanceService:
    def __init__(self, pacifica_client: PacificaClient | None = None, supabase: SupabaseRestClient | None = None) -> None:
        self._pacifica = pacifica_client or get_pacifica_client()
        self._supabase = supabase or SupabaseRestClient()
        self._risk = BotRiskService()

    async def calculate_runtime_performance(
        self,
        runtime: dict[str, Any],
        *,
        market_lookup: dict[str, dict[str, Any]] | None = None,
        live_position_lookup: dict[str, dict[str, Any]] | None = None,
        manual_close_history: list[dict[str, Any]] | None = None,
        live_positions_loaded: bool | None = None,
    ) -> dict[str, Any]:
        return await self.calculate_runtime_performance_with_context(
            runtime,
            market_lookup=market_lookup,
            live_position_lookup=live_position_lookup,
            manual_close_history=manual_close_history,
            live_positions_loaded=live_positions_loaded,
        )

    async def load_market_lookup(self) -> dict[str, dict[str, Any]]:
        return await self._load_market_lookup()

    async def load_live_position_lookup_for_wallet(self, wallet_address: str) -> tuple[dict[str, dict[str, Any]], bool]:
        return await self._load_live_position_lookup({"wallet_address": wallet_address})

    async def load_position_history_for_wallet(
        self,
        wallet_address: str,
        *,
        limit: int = 200,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        if not str(wallet_address or "").strip():
            return []
        return await self._load_manual_history_rows(wallet_address, limit=limit, offset=offset)

    async def calculate_runtime_performance_with_context(
        self,
        runtime: dict[str, Any],
        *,
        market_lookup: dict[str, dict[str, Any]] | None,
        live_position_lookup: dict[str, dict[str, Any]] | None,
        manual_close_history: list[dict[str, Any]] | None,
        live_positions_loaded: bool | None = None,
    ) -> dict[str, Any]:
        sibling_runtimes = self._load_wallet_runtimes(runtime)
        if len(sibling_runtimes) > 1 and self._wallet_requires_joint_reconciliation(sibling_runtimes):
            performance_by_runtime = await self._calculate_wallet_runtime_performance_map(
                sibling_runtimes,
                market_lookup=market_lookup,
                live_position_lookup=live_position_lookup,
                manual_close_history=manual_close_history,
                live_positions_loaded=live_positions_loaded,
            )
            return performance_by_runtime.get(str(runtime.get("id") or "").strip(), self._empty_performance_payload())
        return await self._calculate_runtime_performance_isolated(
            runtime,
            market_lookup=market_lookup,
            live_position_lookup=live_position_lookup,
            manual_close_history=manual_close_history,
            live_positions_loaded=live_positions_loaded,
        )

    async def _calculate_runtime_performance_isolated(
        self,
        runtime: dict[str, Any],
        *,
        market_lookup: dict[str, dict[str, Any]] | None,
        live_position_lookup: dict[str, dict[str, Any]] | None,
        manual_close_history: list[dict[str, Any]] | None,
        live_positions_loaded: bool | None = None,
    ) -> dict[str, Any]:
        events = self._supabase.select(
            "bot_execution_events",
            columns="id,created_at,request_payload,result_payload",
            filters={"runtime_id": runtime["id"], "event_type": "action.executed"},
            order="created_at.asc",
            limit=1000,
        )

        resolved_live_positions_loaded = live_positions_loaded
        if live_position_lookup is None:
            resolved_live_position_lookup, resolved_live_positions_loaded = await self._load_live_position_lookup(runtime)
        else:
            resolved_live_position_lookup = live_position_lookup
            if resolved_live_positions_loaded is None:
                resolved_live_positions_loaded = True

        resolved_manual_close_history = manual_close_history
        if resolved_manual_close_history is None:
            resolved_manual_close_history = await self.load_position_history_for_wallet(
                str(runtime.get("wallet_address") or "").strip()
            )

        cached_ledger = self._load_cached_runtime_ledger(
            runtime,
            events=events,
            live_position_lookup=resolved_live_position_lookup,
            live_positions_loaded=bool(resolved_live_positions_loaded),
            manual_close_history=resolved_manual_close_history,
        )
        if cached_ledger is None:
            order_history_cache: dict[int, list[dict[str, Any]]] = {}
            bot_records: list[dict[str, Any]] = []
            bot_positions: dict[str, dict[str, float]] = {}
            close_events: list[dict[str, Any]] = []
            unresolved_events: list[dict[str, Any]] = []

            for event in events:
                event_realized = 0.0
                event_closed = False
                event_records: list[dict[str, Any]] = []
                fills = await self._resolve_event_fills(event, order_history_cache)
                for fill in fills:
                    applied = self._apply_fill(bot_positions, fill)
                    records = self._build_bot_records(event, fill, applied, event.get("created_at"))
                    bot_records.extend(records)
                    event_records.extend(records)
                    event_realized += applied["realized_pnl"]
                    event_closed = event_closed or applied["closed"]
                if not event_records:
                    unresolved_events.append(event)
                if event_closed:
                    close_events.append(
                        {
                            "created_at": event.get("created_at"),
                            "pnl": round(event_realized, 8),
                        }
                    )

            manual_close_records = await self._load_manual_close_records(
                runtime,
                bot_records,
                unresolved_events=unresolved_events,
                history_rows=resolved_manual_close_history,
            )
            lots, closures, close_events = self._build_runtime_ledger(runtime, bot_records, manual_close_records, close_events)
            self._persist_runtime_ledger(runtime, events, lots, closures)
        else:
            lots, closures = cached_ledger
            close_events = self._build_close_events_from_closures(closures)

        resolved_market_lookup = market_lookup or await self._load_market_lookup()
        return self._build_performance_payload(
            runtime,
            lots=lots,
            closures=closures,
            close_events=close_events,
            market_lookup=resolved_market_lookup,
            live_position_lookup=resolved_live_position_lookup,
            live_positions_loaded=bool(resolved_live_positions_loaded),
        )

    async def _calculate_wallet_runtime_performance_map(
        self,
        runtimes: list[dict[str, Any]],
        *,
        market_lookup: dict[str, dict[str, Any]] | None,
        live_position_lookup: dict[str, dict[str, Any]] | None,
        manual_close_history: list[dict[str, Any]] | None,
        live_positions_loaded: bool | None,
    ) -> dict[str, dict[str, Any]]:
        if not runtimes:
            return {}

        reference_runtime = runtimes[0]
        resolved_live_positions_loaded = live_positions_loaded
        if live_position_lookup is None:
            resolved_live_position_lookup, resolved_live_positions_loaded = await self._load_live_position_lookup(reference_runtime)
        else:
            resolved_live_position_lookup = live_position_lookup
            if resolved_live_positions_loaded is None:
                resolved_live_positions_loaded = True

        resolved_history = manual_close_history
        if resolved_history is None:
            resolved_history = await self.load_position_history_for_wallet(str(reference_runtime.get("wallet_address") or "").strip())
        resolved_market_lookup = market_lookup or await self._load_market_lookup()

        order_history_cache: dict[int, list[dict[str, Any]]] = {}
        runtime_ledgers: dict[str, dict[str, Any]] = {}
        global_bot_records: list[dict[str, Any]] = []

        for runtime in runtimes:
            runtime_id = str(runtime.get("id") or "").strip()
            if not runtime_id:
                continue
            events = self._supabase.select(
                "bot_execution_events",
                columns="id,created_at,request_payload,result_payload",
                filters={"runtime_id": runtime_id, "event_type": "action.executed"},
                order="created_at.asc",
                limit=1000,
            )
            bot_records: list[dict[str, Any]] = []
            bot_positions: dict[str, dict[str, float]] = {}
            unresolved_events: list[dict[str, Any]] = []
            for event in events:
                event_records: list[dict[str, Any]] = []
                fills = await self._resolve_event_fills(event, order_history_cache)
                for fill in fills:
                    applied = self._apply_fill(bot_positions, fill)
                    records = self._build_bot_records(event, fill, applied, event.get("created_at"))
                    bot_records.extend(records)
                    event_records.extend(records)
                if not event_records:
                    unresolved_events.append(event)
            runtime_ledgers[runtime_id] = {
                "runtime": runtime,
                "unresolved_events": unresolved_events,
                "bot_records": bot_records,
            }

        history_rows = self._normalize_position_history_rows(runtimes, resolved_history or [])
        for runtime_id, ledger in runtime_ledgers.items():
            bot_records = list(ledger.get("bot_records") or [])
            bot_records.extend(
                self._materialize_bot_history_records(
                    ledger.get("unresolved_events") or [],
                    history_rows,
                )
            )
            lots, closures, _ = self._build_runtime_ledger(ledger["runtime"], bot_records, [], [])
            runtime_ledgers[runtime_id] = {
                "runtime": ledger["runtime"],
                "lots": lots,
                "closures": closures,
            }
            for record in bot_records:
                global_bot_records.append({**record, "runtime_id": runtime_id})
        self._consume_bot_history_matches(global_bot_records, history_rows)
        manual_closures = self._apply_history_closures_to_lots(history_rows, runtime_ledgers)
        self._cap_open_lots_to_live_positions(
            runtime_ledgers,
            live_position_lookup=resolved_live_position_lookup,
            live_positions_loaded=bool(resolved_live_positions_loaded),
        )

        performance_by_runtime: dict[str, dict[str, Any]] = {}
        for runtime_id, ledger in runtime_ledgers.items():
            closures = [*ledger["closures"], *manual_closures.get(runtime_id, [])]
            performance_by_runtime[runtime_id] = self._build_performance_payload(
                ledger["runtime"],
                lots=ledger["lots"],
                closures=closures,
                close_events=self._build_close_events_from_closures(closures),
                market_lookup=resolved_market_lookup,
                live_position_lookup=resolved_live_position_lookup,
                live_positions_loaded=bool(resolved_live_positions_loaded),
            )
        return performance_by_runtime

    def _load_wallet_runtimes(self, runtime: dict[str, Any]) -> list[dict[str, Any]]:
        wallet_address = str(runtime.get("wallet_address") or "").strip()
        runtime_id = str(runtime.get("id") or "").strip()
        if not wallet_address:
            return [runtime]
        runtimes = self._supabase.select("bot_runtimes", filters={"wallet_address": wallet_address})
        if not runtimes:
            return [runtime]
        if runtime_id and not any(str(item.get("id") or "").strip() == runtime_id for item in runtimes):
            return runtimes if not self._runtime_exists(runtime_id) else [runtime, *runtimes]
        return runtimes

    def _wallet_requires_joint_reconciliation(self, runtimes: list[dict[str, Any]]) -> bool:
        symbol_owners: dict[str, set[str]] = {}
        for runtime in runtimes:
            runtime_id = str(runtime.get("id") or "").strip()
            if not runtime_id:
                continue
            events = self._supabase.select(
                "bot_execution_events",
                columns="result_payload,request_payload",
                filters={"runtime_id": runtime_id, "event_type": "action.executed"},
                limit=1000,
            )
            for event in events:
                symbol = self._extract_event_symbol_hint(event)
                if not symbol:
                    continue
                owners = symbol_owners.setdefault(symbol, set())
                owners.add(runtime_id)
                if len(owners) > 1:
                    return True
        return False

    def _extract_event_symbol_hint(self, event: dict[str, Any]) -> str:
        result_payload = event.get("result_payload") if isinstance(event.get("result_payload"), dict) else {}
        execution_meta = result_payload.get("execution_meta") if isinstance(result_payload.get("execution_meta"), dict) else {}
        payload = result_payload.get("payload") if isinstance(result_payload.get("payload"), dict) else {}
        request_payload = event.get("request_payload") if isinstance(event.get("request_payload"), dict) else {}
        for candidate in (
            execution_meta.get("symbol"),
            payload.get("symbol"),
            request_payload.get("symbol"),
        ):
            symbol = self._normalize_symbol(candidate)
            if symbol:
                return symbol
        return ""

    def _normalize_position_history_rows(
        self,
        runtimes: list[dict[str, Any]],
        history_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        deployed_after = min(
            (
                self._timestamp_value(runtime.get("deployed_at"))
                for runtime in runtimes
                if self._timestamp_value(runtime.get("deployed_at")) > 0
            ),
            default=0.0,
        )
        return self._normalize_manual_history_rows(history_rows, deployed_after=deployed_after)

    def _apply_history_closures_to_lots(
        self,
        history_rows: list[dict[str, Any]],
        runtime_ledgers: dict[str, dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        open_lots: list[dict[str, Any]] = []
        for runtime_id, ledger in runtime_ledgers.items():
            for lot in ledger["lots"]:
                if self._to_float(lot.get("quantity_remaining")) <= 1e-12:
                    continue
                open_lots.append({"runtime_id": runtime_id, "lot": lot})

        manual_closures: dict[str, list[dict[str, Any]]] = {}
        close_rows = sorted(
            [
                row
                for row in history_rows
                if row.get("event_kind") == "close" and self._to_float(row.get("remaining_amount")) > 1e-12
            ],
            key=lambda row: self._timestamp_value(row.get("created_at")),
        )
        for row in close_rows:
            remaining = self._to_float(row.get("remaining_amount"))
            if remaining <= 1e-12:
                continue
            candidate_lots = [
                item
                for item in open_lots
                if item["lot"].get("symbol") == row.get("symbol")
                and item["lot"].get("side") == row.get("position_side")
                and self._to_float(item["lot"].get("quantity_remaining")) > 1e-12
            ]
            candidate_lots.sort(key=lambda item: self._timestamp_value(item["lot"].get("opened_at")))
            for item in candidate_lots:
                if remaining <= 1e-12:
                    break
                lot = item["lot"]
                available = self._to_float(lot.get("quantity_remaining"))
                if available <= 1e-12:
                    continue
                matched = min(remaining, available)
                remaining -= matched
                lot["quantity_remaining"] = round(available - matched, 12)
                lot["updated_at"] = self._coerce_iso(row.get("created_at"))
                realized = self._calculate_realized_pnl(
                    str(lot.get("side") or ""),
                    self._to_float(lot.get("entry_price")),
                    self._to_float(row.get("price")),
                    matched,
                )
                runtime_id = item["runtime_id"]
                manual_closures.setdefault(runtime_id, []).append(
                    self._make_closure(
                        runtime_id,
                        lot,
                        {
                            "source": "manual",
                            "created_at": row.get("created_at"),
                            "source_order_id": row.get("order_id"),
                            "source_history_id": row.get("history_id"),
                        },
                        {"price": row.get("price")},
                        matched,
                        realized,
                    )
                )
            row["remaining_amount"] = round(remaining, 12)
        return manual_closures

    def _cap_open_lots_to_live_positions(
        self,
        runtime_ledgers: dict[str, dict[str, Any]],
        *,
        live_position_lookup: dict[str, dict[str, Any]],
        live_positions_loaded: bool,
    ) -> None:
        if not live_positions_loaded:
            return
        lots_by_symbol_side: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for ledger in runtime_ledgers.values():
            for lot in ledger["lots"]:
                quantity_remaining = self._to_float(lot.get("quantity_remaining"))
                side = str(lot.get("side") or "")
                symbol = self._normalize_symbol(lot.get("symbol"))
                if quantity_remaining <= 1e-12 or side not in {"long", "short"} or not symbol:
                    continue
                lots_by_symbol_side.setdefault((symbol, side), []).append(lot)

        for (symbol, side), lots in lots_by_symbol_side.items():
            live_position = live_position_lookup.get(symbol)
            live_side = self._normalize_position_side((live_position or {}).get("side"))
            live_amount = abs(self._to_float((live_position or {}).get("amount"))) if live_side == side else 0.0
            total_open = sum(self._to_float(lot.get("quantity_remaining")) for lot in lots)
            excess = total_open - live_amount
            if excess <= 1e-12:
                continue
            lots.sort(key=lambda lot: self._timestamp_value(lot.get("opened_at")))
            for lot in lots:
                if excess <= 1e-12:
                    break
                available = self._to_float(lot.get("quantity_remaining"))
                if available <= 1e-12:
                    continue
                reduction = min(excess, available)
                lot["quantity_remaining"] = round(available - reduction, 12)
                excess -= reduction

    def _build_performance_payload(
        self,
        runtime: dict[str, Any],
        *,
        lots: list[dict[str, Any]],
        closures: list[dict[str, Any]],
        close_events: list[dict[str, Any]],
        market_lookup: dict[str, dict[str, Any]],
        live_position_lookup: dict[str, dict[str, Any]],
        live_positions_loaded: bool,
    ) -> dict[str, Any]:
        realized_pnl = round(sum(float(item.get("realized_pnl") or 0.0) for item in closures), 8)
        open_positions: list[dict[str, Any]] = []
        unrealized_pnl = 0.0
        open_lots = [item for item in lots if self._to_float(item.get("quantity_remaining")) > 1e-12]
        position_states = self._summarize_open_lots(open_lots)
        for symbol, state in position_states.items():
            quantity = float(state.get("quantity") or 0.0)
            entry_price = float(state.get("entry_price") or 0.0)
            if abs(quantity) <= 1e-12 or entry_price <= 0:
                continue
            runtime_side = "long" if quantity > 0 else "short"
            live_position = live_position_lookup.get(symbol)
            live_side = self._normalize_position_side((live_position or {}).get("side"))
            if live_positions_loaded and (live_position is None or live_side != runtime_side):
                continue
            mark_price = 0.0
            if live_position is not None and live_side == runtime_side:
                mark_price = float(live_position.get("mark_price") or 0.0)
            if mark_price <= 0:
                mark_price = float((market_lookup.get(symbol) or {}).get("mark_price") or 0.0)
            if mark_price <= 0:
                if live_positions_loaded:
                    continue
                mark_price = entry_price
            size = abs(quantity)
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

    @staticmethod
    def _empty_performance_payload() -> dict[str, Any]:
        return {
            "pnl_total": 0.0,
            "pnl_total_pct": 0.0,
            "pnl_realized": 0.0,
            "pnl_unrealized": 0.0,
            "win_streak": 0,
            "positions": [],
        }

    def _load_cached_runtime_ledger(
        self,
        runtime: dict[str, Any],
        *,
        events: list[dict[str, Any]],
        live_position_lookup: dict[str, dict[str, Any]],
        live_positions_loaded: bool,
        manual_close_history: list[dict[str, Any]] | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]] | None:
        runtime_id = str(runtime.get("id") or "").strip()
        if not runtime_id:
            return None
        sync_state = self._supabase.maybe_one("bot_trade_sync_state", filters={"runtime_id": runtime_id})
        if sync_state is None:
            return None
        if int(sync_state.get("execution_events_count") or 0) != len(events):
            return None
        latest_event_at = events[-1].get("created_at") if events else None
        if not self._timestamps_match(sync_state.get("last_execution_at"), latest_event_at):
            return None
        lots = self._supabase.select("bot_trade_lots", filters={"runtime_id": runtime_id})
        closures = self._supabase.select("bot_trade_closures", filters={"runtime_id": runtime_id})
        if self._has_live_position_drift(lots, live_position_lookup, live_positions_loaded):
            return None
        if self._has_manual_history_drift(runtime, sync_state, lots, manual_close_history):
            return None
        return lots, closures

    def _has_live_position_drift(
        self,
        lots: list[dict[str, Any]],
        live_position_lookup: dict[str, dict[str, Any]],
        live_positions_loaded: bool,
    ) -> bool:
        if not live_positions_loaded:
            return False
        position_states = self._summarize_open_lots([item for item in lots if self._to_float(item.get("quantity_remaining")) > 1e-12])
        for symbol, state in position_states.items():
            quantity = float(state.get("quantity") or 0.0)
            if abs(quantity) <= 1e-12:
                continue
            live_position = live_position_lookup.get(symbol)
            runtime_side = "long" if quantity > 0 else "short"
            if live_position is None:
                return True
            live_side = self._normalize_position_side(live_position.get("side"))
            live_amount = abs(float(live_position.get("amount") or 0.0))
            if live_side != runtime_side or live_amount <= 1e-12:
                return True
        return False

    def _has_manual_history_drift(
        self,
        runtime: dict[str, Any],
        sync_state: dict[str, Any],
        lots: list[dict[str, Any]],
        manual_close_history: list[dict[str, Any]] | None,
    ) -> bool:
        if manual_close_history is None:
            return False
        symbols = {
            self._normalize_symbol(item.get("symbol"))
            for item in lots
            if self._normalize_symbol(item.get("symbol"))
        }
        if not symbols:
            return False
        deployed_at = self._timestamp_value(runtime.get("deployed_at"))
        latest_relevant_close_at = max(
            (
                self._timestamp_value(row.get("created_at"))
                for row in manual_close_history
                if self._normalize_symbol(row.get("symbol")) in symbols
                and ((str(row.get("event_kind") or "").strip().lower()) or self._position_history_event_kind(row)[0]) == "close"
                and self._timestamp_value(row.get("created_at")) >= deployed_at
            ),
            default=0.0,
        )
        if latest_relevant_close_at <= 0:
            return False
        return latest_relevant_close_at > self._timestamp_value(sync_state.get("last_history_at"))

    @classmethod
    def _build_close_events_from_closures(cls, closures: list[dict[str, Any]]) -> list[dict[str, Any]]:
        totals_by_closed_at: dict[str, float] = {}
        for closure in closures:
            closed_at = str(closure.get("closed_at") or "").strip()
            if not closed_at:
                continue
            totals_by_closed_at[closed_at] = totals_by_closed_at.get(closed_at, 0.0) + float(closure.get("realized_pnl") or 0.0)
        return [
            {"created_at": closed_at, "pnl": round(pnl, 8)}
            for closed_at, pnl in totals_by_closed_at.items()
        ]

    @classmethod
    def _timestamps_match(cls, left: Any, right: Any) -> bool:
        return abs(cls._timestamp_value(left) - cls._timestamp_value(right)) <= 1e-6

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
        runtime_id = str(runtime.get("id") or "").strip()
        if not runtime_id or not self._runtime_exists(runtime_id):
            return
        try:
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
        except SupabaseRestError as exc:
            if self._is_missing_runtime_fk_violation(exc):
                return
            raise

    def _runtime_exists(self, runtime_id: str) -> bool:
        return self._supabase.maybe_one("bot_runtimes", columns="id", filters={"id": runtime_id}) is not None

    @staticmethod
    def _is_missing_runtime_fk_violation(exc: SupabaseRestError) -> bool:
        if exc.status_code != 409:
            return False
        detail = str(exc).lower()
        return "bot_trade_" in detail and "runtime_id_fkey" in detail

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
        unresolved_events: list[dict[str, Any]] | None = None,
        history_rows: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        wallet_address = str(runtime.get("wallet_address") or "").strip()
        if not wallet_address:
            return []
        resolved_history_rows = history_rows
        if resolved_history_rows is None:
            resolved_history_rows = await self._load_manual_history_rows(wallet_address, limit=200, offset=0)
            if not resolved_history_rows:
                return []

        normalized_history = self._normalize_manual_history_rows(
            resolved_history_rows,
            deployed_after=self._timestamp_value(runtime.get("deployed_at")),
        )

        bot_records.extend(self._materialize_bot_history_records(unresolved_events or [], normalized_history))
        if not bot_records:
            return []
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
                    "source_order_id": row.get("order_id"),
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

    def _materialize_bot_history_records(
        self,
        unresolved_events: list[dict[str, Any]],
        history_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for event in unresolved_events:
            hint = self._infer_request_history_hint(event)
            if hint is None:
                continue
            row = self._match_history_row_for_hint(hint, history_rows)
            if row is None:
                continue
            amount = self._to_float(row.get("amount"))
            price = self._to_float(row.get("price"))
            if amount <= 1e-12 or price <= 0:
                continue
            position_side = str(hint.get("position_side") or "")
            event_kind = str(hint.get("event_kind") or "")
            fill_side = position_side if event_kind == "open" else ("short" if position_side == "long" else "long")
            records.append(
                {
                    "source": "bot",
                    "created_at": row.get("created_at") or event.get("created_at"),
                    "symbol": row.get("symbol"),
                    "event_kind": event_kind,
                    "position_side": position_side,
                    "amount": amount,
                    "source_event_id": event.get("id"),
                    "source_order_id": str(self._extract_order_id(event)) if self._extract_order_id(event) is not None else None,
                    "source_history_id": row.get("history_id"),
                    "fill": {
                        "symbol": row.get("symbol"),
                        "side": fill_side,
                        "amount": amount,
                        "price": price,
                        "reduce_only": event_kind == "close",
                        "event_type": "history_match",
                        "created_at": row.get("created_at") or event.get("created_at"),
                    },
                }
            )
        return records

    def _infer_request_history_hint(self, event: dict[str, Any]) -> dict[str, Any] | None:
        request_payload = event.get("request_payload") if isinstance(event.get("request_payload"), dict) else {}
        symbol = self._normalize_symbol(request_payload.get("symbol"))
        if not symbol:
            return None
        action_type = str(request_payload.get("type") or "").strip().lower()
        if action_type == "open_long":
            return {"symbol": symbol, "event_kind": "open", "position_side": "long", "created_at": event.get("created_at")}
        if action_type == "open_short":
            return {"symbol": symbol, "event_kind": "open", "position_side": "short", "created_at": event.get("created_at")}
        if action_type == "close_position":
            side = self._normalize_position_side(request_payload.get("side"))
            position_side = "short" if side == "long" else "long" if side == "short" else ""
            if not position_side:
                return None
            return {"symbol": symbol, "event_kind": "close", "position_side": position_side, "created_at": event.get("created_at")}
        if action_type in {"place_market_order", "place_limit_order", "place_twap_order"}:
            order_side = self._normalize_position_side(request_payload.get("side"))
            if order_side not in {"long", "short"}:
                return None
            reduce_only = self._to_bool(request_payload.get("reduce_only"), False)
            position_side = "short" if reduce_only and order_side == "long" else "long" if reduce_only and order_side == "short" else order_side
            event_kind = "close" if reduce_only else "open"
            return {"symbol": symbol, "event_kind": event_kind, "position_side": position_side, "created_at": event.get("created_at")}
        return None

    def _match_history_row_for_hint(
        self,
        hint: dict[str, Any],
        history_rows: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        candidates = [
            row
            for row in history_rows
            if row.get("symbol") == hint.get("symbol")
            and row.get("event_kind") == hint.get("event_kind")
            and row.get("position_side") == hint.get("position_side")
            and self._to_float(row.get("remaining_amount")) > 1e-12
        ]
        if not candidates:
            return None
        candidates.sort(
            key=lambda row: abs(self._timestamp_value(row.get("created_at")) - self._timestamp_value(hint.get("created_at")))
        )
        row = candidates[0]
        row["remaining_amount"] = 0.0
        return row

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
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(BotPerformanceService._timestamp_value(value), tz=UTC).isoformat()
        text = str(value or "").strip()
        if not text:
            return datetime.now(tz=UTC).isoformat()
        try:
            numeric = float(text)
        except ValueError:
            normalized = text.replace("Z", "+00:00")
            try:
                return datetime.fromisoformat(normalized).astimezone(UTC).isoformat()
            except ValueError:
                return datetime.now(tz=UTC).isoformat()
        return datetime.fromtimestamp(BotPerformanceService._timestamp_value(numeric), tz=UTC).isoformat()

    async def _load_manual_history_rows(
        self,
        wallet_address: str,
        *,
        limit: int,
        offset: int,
    ) -> list[dict[str, Any]]:
        position_rows = await self._load_position_history_pages(wallet_address, limit=limit, offset=offset)
        order_rows = await self._load_wallet_order_history_pages(wallet_address, limit=limit, offset=offset)
        return self._normalize_manual_history_rows([*position_rows, *order_rows])

    async def _load_position_history_pages(
        self,
        wallet_address: str,
        *,
        limit: int,
        offset: int,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        page_size = max(1, int(limit or 200))
        page_offset = max(0, int(offset or 0))
        try:
            for _ in range(max_pages):
                batch = await self._pacifica.get_position_history(wallet_address, limit=page_size, offset=page_offset)
                if not batch:
                    break
                for row in batch:
                    if not isinstance(row, dict):
                        continue
                    dedupe_key = self._position_history_dedupe_key(row)
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)
                    rows.append(row)
                if len(batch) < page_size:
                    break
                page_offset += page_size
        except PacificaClientError:
            return []
        rows.sort(key=lambda row: self._timestamp_value(row.get("created_at") or row.get("createdAt")))
        return rows

    async def _load_wallet_order_history_pages(
        self,
        wallet_address: str,
        *,
        limit: int,
        offset: int,
        max_pages: int = 10,
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        page_size = max(1, int(limit or 200))
        page_offset = max(0, int(offset or 0))
        try:
            for _ in range(max_pages):
                batch = await self._pacifica.get_order_history(wallet_address, limit=page_size, offset=page_offset)
                if not batch:
                    break
                for row in batch:
                    if not isinstance(row, dict):
                        continue
                    dedupe_key = self._position_history_dedupe_key(row)
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)
                    rows.append(row)
                if len(batch) < page_size:
                    break
                page_offset += page_size
        except (AttributeError, PacificaClientError):
            return []
        rows.sort(key=lambda row: self._timestamp_value(row.get("created_at") or row.get("createdAt")))
        return rows

    @classmethod
    def _position_history_dedupe_key(cls, row: dict[str, Any]) -> str:
        history_id = row.get("history_id") or row.get("historyId")
        if history_id not in (None, ""):
            return f"history:{history_id}"
        order_id = row.get("order_id") or row.get("orderId")
        if order_id not in (None, ""):
            return f"order:{order_id}"
        return "|".join(
            (
                cls._normalize_symbol(row.get("symbol")),
                str(row.get("event_type") or row.get("eventType") or "").strip().lower(),
                str(row.get("created_at") or row.get("createdAt") or "").strip(),
                str(row.get("amount") or "").strip(),
                str(row.get("price") or "").strip(),
            )
        )

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

    def _normalize_manual_history_rows(
        self,
        history_rows: list[dict[str, Any]],
        *,
        deployed_after: float = 0.0,
    ) -> list[dict[str, Any]]:
        normalized_history: list[dict[str, Any]] = []
        seen_keys: set[str] = set()
        for row in history_rows:
            normalized_row = self._normalize_manual_history_row(row)
            if normalized_row is None:
                continue
            if deployed_after > 0 and self._timestamp_value(normalized_row.get("created_at")) < deployed_after:
                continue
            dedupe_key = self._manual_history_row_key(normalized_row)
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            normalized_history.append(normalized_row)
        normalized_history.sort(key=lambda item: self._timestamp_value(item.get("created_at")))
        return normalized_history

    def _normalize_manual_history_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        event_kind = str(row.get("event_kind") or "").strip().lower()
        position_side = str(row.get("position_side") or "").strip().lower()
        if event_kind not in {"open", "close"} or position_side not in {"long", "short"}:
            event_kind, position_side = self._position_history_event_kind(row)
        amount = self._to_float(row.get("amount"))
        price = self._to_float(row.get("price"))
        symbol = self._normalize_symbol(row.get("symbol"))
        if event_kind not in {"open", "close"} or position_side not in {"long", "short"} or amount <= 1e-12 or price <= 0 or not symbol:
            return None
        remaining_amount = self._to_float(row.get("remaining_amount"))
        return {
            "history_id": row.get("history_id") or row.get("historyId"),
            "order_id": row.get("order_id") or row.get("orderId"),
            "client_order_id": str(row.get("client_order_id") or row.get("clientOrderId") or "").strip() or None,
            "symbol": symbol,
            "event_kind": event_kind,
            "position_side": position_side,
            "amount": amount,
            "remaining_amount": remaining_amount if remaining_amount > 1e-12 else amount,
            "price": price,
            "pnl": self._to_float(row.get("pnl")),
            "created_at": row.get("created_at") or row.get("createdAt"),
        }

    @classmethod
    def _manual_history_row_key(cls, row: dict[str, Any]) -> str:
        return "|".join(
            (
                cls._normalize_symbol(row.get("symbol")),
                str(row.get("event_kind") or "").strip().lower(),
                str(row.get("position_side") or "").strip().lower(),
                f"{cls._timestamp_value(row.get('created_at')):.6f}",
                f"{cls._to_float(row.get('amount')):.12f}",
                f"{cls._to_float(row.get('price')):.8f}",
                f"{cls._to_float(row.get('pnl')):.8f}",
            )
        )

    @classmethod
    def _position_history_event_kind(cls, row: dict[str, Any]) -> tuple[str | None, str | None]:
        event_type = str(row.get("event_type") or row.get("eventType") or "").lower().strip()
        if event_type.startswith("open_"):
            return "open", "long" if event_type.endswith("long") else "short" if event_type.endswith("short") else None
        if event_type.startswith("close_"):
            return "close", "long" if event_type.endswith("long") else "short" if event_type.endswith("short") else None
        side = cls._normalize_position_side(row.get("side"))
        if side not in {"long", "short"}:
            return None, None
        reduce_only = cls._to_bool(row.get("reduce_only"), False)
        amount = cls._to_float(row.get("amount"))
        price = cls._to_float(row.get("price"))
        order_status = str(row.get("order_status") or row.get("status") or "").lower().strip()
        if amount <= 1e-12 or price <= 0:
            return None, None
        if reduce_only and (order_status in {"", "filled", "partially_filled"} or event_type.startswith("fulfill")):
            return "close", "short" if side == "long" else "long"
        if order_status in {"filled", "partially_filled"} or event_type.startswith("fulfill"):
            return "open", side
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

    @staticmethod
    def _to_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"1", "true", "yes", "y"}:
                return True
            if normalized in {"0", "false", "no", "n"}:
                return False
        return bool(value)
