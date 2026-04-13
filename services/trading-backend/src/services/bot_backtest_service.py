from __future__ import annotations

import uuid
from bisect import bisect_right
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

from src.services.indicator_context_service import extract_candle_requests, normalize_symbol
from src.services.pacifica_client import PacificaClient, PacificaClientError, get_pacifica_client
from src.services.rules_engine import RulesEngine
from src.services.supabase_rest import SupabaseRestClient


MAIN_TIMEFRAME_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}
SUPPORTED_ACTION_TYPES = {
    "open_long",
    "open_short",
    "place_market_order",
    "close_position",
    "set_tpsl",
    "update_leverage",
}
UNSUPPORTED_ACTION_TYPES = {
    "place_limit_order",
    "place_twap_order",
    "cancel_order",
    "cancel_twap_order",
    "cancel_all_orders",
}
MARKET_UNIVERSE_SYMBOL = "__BOT_MARKET_UNIVERSE__"
DEFAULT_BACKTEST_ASSUMPTIONS = {
    "fee_bps": 0.0,
    "slippage_bps": 0.0,
    "funding_bps_per_interval": 0.0,
}
DEFAULT_BACKTEST_INTERVAL = "15m"


def infer_backtest_interval_from_rules(rules_json: dict[str, Any] | None) -> str:
    if not isinstance(rules_json, dict):
        return DEFAULT_BACKTEST_INTERVAL

    requests = extract_candle_requests(rules_json)
    supported_timeframes = {
        str(request.get("timeframe") or "").strip().lower()
        for request in requests
        if str(request.get("timeframe") or "").strip().lower() in MAIN_TIMEFRAME_MS
    }
    if not supported_timeframes:
        return DEFAULT_BACKTEST_INTERVAL

    return min(supported_timeframes, key=lambda timeframe: MAIN_TIMEFRAME_MS[timeframe])


class BotBacktestService:
    def __init__(
        self,
        pacifica_client: PacificaClient | None = None,
        supabase: SupabaseRestClient | None = None,
        rules_engine: RulesEngine | None = None,
    ) -> None:
        self._pacifica = pacifica_client or get_pacifica_client()
        self._supabase = supabase or SupabaseRestClient()
        self._rules = rules_engine or RulesEngine()

    async def run_backtest(
        self,
        db: Any,
        *,
        bot_id: str,
        wallet_address: str,
        user_id: str,
        interval: str | None,
        start_time: int,
        end_time: int,
        initial_capital_usd: float,
        assumptions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        del db
        bot = self._resolve_bot(bot_id=bot_id, wallet_address=wallet_address, user_id=user_id)
        rules_snapshot = deepcopy(bot.get("rules_json") if isinstance(bot.get("rules_json"), dict) else {})
        resolved_interval = str(interval or "").strip().lower() or infer_backtest_interval_from_rules(rules_snapshot)
        normalized_assumptions = self._normalize_assumptions(assumptions)
        placeholder_symbols = self._market_scope_symbols(str(bot.get("market_scope") or ""))
        preflight_issues = self._preflight_issues(
            bot=bot,
            interval=resolved_interval,
            start_time=start_time,
            end_time=end_time,
            initial_capital_usd=initial_capital_usd,
        )
        now_iso = self._now_iso()
        status = "completed"
        result_json: dict[str, Any]

        try:
            if preflight_issues:
                status = "failed"
                result_json = self._failed_result(
                    bot=bot,
                    interval=resolved_interval,
                    start_time=start_time,
                    end_time=end_time,
                    initial_capital_usd=initial_capital_usd,
                    assumptions=normalized_assumptions,
                    preflight_issues=preflight_issues,
                )
            else:
                result_json = await self._simulate(
                    bot=bot,
                    rules_snapshot=rules_snapshot,
                    interval=resolved_interval,
                    start_time=start_time,
                    end_time=end_time,
                    initial_capital_usd=initial_capital_usd,
                    assumptions=normalized_assumptions,
                    placeholder_symbols=placeholder_symbols,
                )
        except (PacificaClientError, ValueError) as exc:
            status = "failed"
            result_json = self._failed_result(
                bot=bot,
                interval=resolved_interval,
                start_time=start_time,
                end_time=end_time,
                initial_capital_usd=initial_capital_usd,
                assumptions=normalized_assumptions,
                execution_issues=[str(exc)],
            )

        summary = result_json.get("summary") if isinstance(result_json.get("summary"), dict) else {}
        completed_at = self._now_iso()
        failure_reason = self._extract_failure_reason(result_json=result_json, status=status)
        row = self._supabase.insert(
            "bot_backtest_runs",
            {
                "id": str(uuid.uuid4()),
                "bot_definition_id": bot["id"],
                "user_id": bot["user_id"],
                "wallet_address": wallet_address,
                "bot_name_snapshot": bot["name"],
                "market_scope_snapshot": str(bot.get("market_scope") or ""),
                "strategy_type_snapshot": str(bot.get("strategy_type") or ""),
                "rules_snapshot_json": rules_snapshot,
                "interval": resolved_interval,
                "start_time": start_time,
                "end_time": end_time,
                "initial_capital_usd": initial_capital_usd,
                "execution_model": "candle_close_v2",
                "pnl_total": self._to_float(summary.get("pnl_total"), 0.0),
                "pnl_total_pct": self._to_float(summary.get("pnl_total_pct"), 0.0),
                "max_drawdown_pct": self._to_float(summary.get("max_drawdown_pct"), 0.0),
                "win_rate": self._to_float(summary.get("win_rate"), 0.0),
                "trade_count": int(self._to_float(summary.get("trade_count"), 0.0)),
                "status": status,
                "assumption_config_json": normalized_assumptions,
                "failure_reason": failure_reason,
                "result_json": result_json,
                "created_at": now_iso,
                "completed_at": completed_at,
                "updated_at": completed_at,
            },
        )[0]
        return self.serialize_run_detail(row)

    def list_runs(
        self,
        db: Any,
        *,
        wallet_address: str,
        user_id: str,
        bot_id: str | None = None,
    ) -> list[dict[str, Any]]:
        del db, user_id
        filters: dict[str, Any] = {"wallet_address": wallet_address}
        if bot_id:
            filters["bot_definition_id"] = bot_id
        rows = self._supabase.select("bot_backtest_runs", filters=filters, order="completed_at.desc")
        return [self.serialize_run_summary(row) for row in rows]

    def get_run(
        self,
        db: Any,
        *,
        run_id: str,
        wallet_address: str,
        user_id: str,
    ) -> dict[str, Any]:
        del db, user_id
        row = self._supabase.maybe_one("bot_backtest_runs", filters={"id": run_id, "wallet_address": wallet_address})
        if row is None:
            raise ValueError("Backtest run not found")
        return self.serialize_run_detail(row)

    async def _simulate(
        self,
        *,
        bot: dict[str, Any],
        rules_snapshot: dict[str, Any],
        interval: str,
        start_time: int,
        end_time: int,
        initial_capital_usd: float,
        assumptions: dict[str, float],
        placeholder_symbols: list[str],
    ) -> dict[str, Any]:
        evaluation_rulesets = self._build_evaluation_rulesets(rules_snapshot, placeholder_symbols)
        active_symbols = sorted(
            {
                symbol
                for ruleset in evaluation_rulesets
                for symbol in self._extract_symbols(ruleset)
                if symbol and symbol != MARKET_UNIVERSE_SYMBOL
            }
        )
        if not active_symbols:
            raise ValueError("Backtests need at least one concrete market symbol.")
        requested_symbols = list(active_symbols)

        candle_requests = {
            (symbol, interval): {"symbol": symbol, "timeframe": interval}
            for symbol in active_symbols
        }
        for ruleset in evaluation_rulesets:
            for request in extract_candle_requests(ruleset):
                symbol = normalize_symbol(request.get("symbol"))
                timeframe = str(request.get("timeframe") or "").strip().lower()
                if not symbol or timeframe not in MAIN_TIMEFRAME_MS:
                    continue
                candle_requests[(symbol, timeframe)] = {"symbol": symbol, "timeframe": timeframe}

        candle_lookup: dict[str, dict[str, list[dict[str, Any]]]] = {}
        close_time_lookup: dict[tuple[str, str], list[int]] = {}
        missing_main_symbols: set[str] = set()
        for symbol, timeframe in sorted(candle_requests):
            candles = await self._pacifica.get_kline(
                symbol,
                interval=timeframe,
                start_time=start_time,
                end_time=end_time,
            )
            if timeframe == interval and not candles:
                missing_main_symbols.add(symbol)
                continue
            candle_lookup.setdefault(symbol, {})[timeframe] = candles
            close_time_lookup[(symbol, timeframe)] = [int(item.get("close_time") or 0) for item in candles]

        if missing_main_symbols:
            active_symbols = [symbol for symbol in active_symbols if symbol not in missing_main_symbols]
            evaluation_rulesets = [
                ruleset
                for ruleset in evaluation_rulesets
                if self._extract_symbols(ruleset).intersection(active_symbols)
            ]

        if not active_symbols:
            if len(requested_symbols) == 1:
                raise ValueError(f"No historical candles were returned for {requested_symbols[0]} on {interval}.")
            raise ValueError(
                "No historical candles were returned for any requested symbol on "
                f"{interval}. Missing: {', '.join(sorted(missing_main_symbols))}."
            )

        main_candles = {symbol: candle_lookup.get(symbol, {}).get(interval, []) for symbol in active_symbols}
        timeline = sorted(
            {
                int(candle.get("close_time") or 0)
                for symbol in active_symbols
                for candle in main_candles.get(symbol, [])
                if int(candle.get("close_time") or 0) > 0
            }
        )
        if not timeline:
            raise ValueError("No main replay bars were returned for this backtest range.")

        current_candle_by_symbol: dict[str, dict[str, Any]] = {}
        candle_index_by_symbol = {symbol: -1 for symbol in active_symbols}
        positions: dict[str, dict[str, Any]] = {}
        trigger_events: list[dict[str, Any]] = []
        closed_trades: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []
        last_executed_at: str | None = None
        cumulative_realized = 0.0
        trade_counter = 0

        for timestamp in timeline:
            timestamp_iso = self._iso_from_ms(timestamp)
            for symbol in active_symbols:
                symbol_candles = main_candles.get(symbol, [])
                next_index = candle_index_by_symbol[symbol] + 1
                while next_index < len(symbol_candles) and int(symbol_candles[next_index].get("close_time") or 0) <= timestamp:
                    candle_index_by_symbol[symbol] = next_index
                    next_index += 1
                index = candle_index_by_symbol[symbol]
                if index >= 0:
                    current_candle_by_symbol[symbol] = symbol_candles[index]

            self._accrue_funding(
                positions=positions,
                current_candle_by_symbol=current_candle_by_symbol,
                assumptions=assumptions,
            )

            for symbol, position in list(positions.items()):
                current_candle = current_candle_by_symbol.get(symbol)
                if current_candle is None:
                    continue
                protection = self._resolve_protection_exit(position=position, candle=current_candle)
                if protection is None:
                    continue
                closed_trade = self._close_position(
                    position=position,
                    exit_price=self._apply_execution_slippage(
                        price=protection["exit_price"],
                        side=str(position.get("side") or ""),
                        intent="exit",
                        slippage_bps=assumptions["slippage_bps"],
                    ),
                    timestamp_ms=timestamp,
                    reason=protection["reason"],
                    assumptions=assumptions,
                )
                cumulative_realized += self._to_float(closed_trade.get("pnl_usd"), 0.0)
                closed_trades.append(closed_trade)
                positions.pop(symbol, None)
                last_executed_at = timestamp_iso
                trigger_events.append(
                    {
                        "timestamp": timestamp,
                        "symbol": symbol,
                        "kind": "protection_exit",
                        "title": "Protection exit",
                        "detail": f"{symbol} closed via {protection['reason'].replace('_', ' ')} at {protection['exit_price']:.4f}.",
                    }
                )

            market_lookup = {
                symbol: self._market_snapshot_from_candle(symbol, candle)
                for symbol, candle in current_candle_by_symbol.items()
            }
            position_lookup = {
                symbol: self._position_snapshot(
                    position=position,
                    mark_price=self._to_float((market_lookup.get(symbol) or {}).get("mark_price"), position.get("entry_price", 0.0)),
                )
                for symbol, position in positions.items()
            }

            for ruleset in evaluation_rulesets:
                context = {
                    "market_lookup": market_lookup,
                    "position_lookup": position_lookup,
                    "candle_lookup": self._slice_candle_lookup(candle_lookup, close_time_lookup, timestamp),
                    "runtime": {
                        "state": {
                            "last_executed_at": last_executed_at,
                            "now": timestamp_iso,
                        }
                    },
                }
                evaluation = self._rules.evaluate(rules_json=ruleset, context=context)
                actions = evaluation.get("actions") if isinstance(evaluation.get("actions"), list) else []
                if not actions:
                    continue

                for action in actions:
                    action_result = self._execute_action(
                        action=action,
                        timestamp_ms=timestamp,
                        current_candle_by_symbol=current_candle_by_symbol,
                        positions=positions,
                        position_lookup=position_lookup,
                        trade_counter=trade_counter,
                        assumptions=assumptions,
                    )
                    trade_counter = action_result["trade_counter"]
                    if action_result.get("closed_trade") is not None:
                        closed_trade = action_result["closed_trade"]
                        cumulative_realized += self._to_float(closed_trade.get("pnl_usd"), 0.0)
                        closed_trades.append(closed_trade)
                    for removed_symbol in action_result.get("removed_symbols", []):
                        positions.pop(removed_symbol, None)
                    if action_result.get("opened_position") is not None:
                        opened_position = action_result["opened_position"]
                        positions[opened_position["symbol"]] = opened_position

                    trigger_events.append(
                        {
                            "timestamp": timestamp,
                            "symbol": action_result.get("symbol") or normalize_symbol(action.get("symbol")),
                            "kind": "action",
                            "title": str(action.get("type") or "action").replace("_", " "),
                            "detail": action_result.get("detail") or f"Executed {action.get('type') or 'action'}.",
                        }
                    )
                    if action_result.get("executed"):
                        last_executed_at = timestamp_iso

                position_lookup = {
                    symbol: self._position_snapshot(
                        position=position,
                        mark_price=self._to_float((market_lookup.get(symbol) or {}).get("mark_price"), position.get("entry_price", 0.0)),
                    )
                    for symbol, position in positions.items()
                }

            unrealized_pnl = sum(self._to_float(snapshot.get("unrealized_pnl"), 0.0) for snapshot in position_lookup.values())
            equity = initial_capital_usd + cumulative_realized + unrealized_pnl
            equity_curve.append(
                {
                    "time": timestamp,
                    "equity": round(equity, 8),
                    "realized_pnl": round(cumulative_realized, 8),
                    "unrealized_pnl": round(unrealized_pnl, 8),
                }
            )

        open_trades = [
            self._open_trade_snapshot(
                position=position,
                mark_price=self._to_float((current_candle_by_symbol.get(symbol) or {}).get("close"), position.get("entry_price", 0.0)),
            )
            for symbol, position in positions.items()
        ]
        total_fees_paid = round(
            sum(self._to_float(trade.get("fees_paid_usd"), 0.0) for trade in [*closed_trades, *open_trades]),
            8,
        )
        total_funding_pnl = round(
            sum(self._to_float(trade.get("funding_pnl_usd"), 0.0) for trade in [*closed_trades, *open_trades]),
            8,
        )
        primary_symbol = active_symbols[0]
        ending_equity = equity_curve[-1]["equity"] if equity_curve else initial_capital_usd
        pnl_total = ending_equity - initial_capital_usd
        gross_pnl_total = round(pnl_total + total_fees_paid - total_funding_pnl, 8)
        trade_count = len(closed_trades)
        winning_trades = len([trade for trade in closed_trades if self._to_float(trade.get("pnl_usd"), 0.0) > 0])
        win_rate = (winning_trades / trade_count * 100.0) if trade_count else 0.0
        avg_duration_seconds = (
            sum(int(trade.get("duration_seconds") or 0) for trade in closed_trades) / trade_count if trade_count else 0.0
        )
        summary = {
            "primary_symbol": primary_symbol,
            "symbols": active_symbols,
            "requested_symbols": requested_symbols,
            "skipped_symbols": sorted(missing_main_symbols),
            "interval": interval,
            "initial_capital_usd": round(initial_capital_usd, 8),
            "ending_equity": round(ending_equity, 8),
            "realized_pnl": round(cumulative_realized, 8),
            "unrealized_pnl": round(sum(self._to_float(trade.get("unrealized_pnl"), 0.0) for trade in open_trades), 8),
            "gross_pnl_total": gross_pnl_total,
            "pnl_total": round(pnl_total, 8),
            "pnl_total_pct": round((pnl_total / initial_capital_usd * 100.0) if initial_capital_usd > 0 else 0.0, 8),
            "max_drawdown_pct": round(self._max_drawdown_pct(equity_curve), 8),
            "win_rate": round(win_rate, 8),
            "trade_count": trade_count,
            "winning_trades": winning_trades,
            "losing_trades": max(trade_count - winning_trades, 0),
            "avg_trade_duration_seconds": round(avg_duration_seconds, 8),
            "fees_paid_usd": total_fees_paid,
            "funding_pnl_usd": total_funding_pnl,
        }
        return {
            "equity_curve": equity_curve,
            "price_series": {
                "primary_symbol": primary_symbol,
                "series_by_symbol": {
                    symbol: [
                        {
                            "time": int(candle.get("close_time") or 0),
                            "open": self._to_float(candle.get("open"), 0.0),
                            "high": self._to_float(candle.get("high"), 0.0),
                            "low": self._to_float(candle.get("low"), 0.0),
                            "close": self._to_float(candle.get("close"), 0.0),
                            "volume": self._to_float(candle.get("volume"), 0.0),
                        }
                        for candle in main_candles.get(symbol, [])
                    ]
                    for symbol in active_symbols
                },
            },
            "trades": [*closed_trades, *open_trades],
            "trigger_events": trigger_events,
            "summary": summary,
            "assumption_config": assumptions,
            "assumptions": self._build_assumptions_text(
                assumptions=assumptions,
                missing_main_symbols=missing_main_symbols,
            ),
        }

    def _preflight_issues(
        self,
        *,
        bot: dict[str, Any],
        interval: str,
        start_time: int,
        end_time: int,
        initial_capital_usd: float,
    ) -> list[str]:
        issues: list[str] = []
        if bot.get("authoring_mode") != "visual":
            issues.append("Only saved visual bots can be backtested in v1.")
        rules_json = bot.get("rules_json") if isinstance(bot.get("rules_json"), dict) else {}
        if not rules_json:
            issues.append("Bot rules are missing or invalid.")
        else:
            issues.extend(self._rules.validation_issues(rules_json=rules_json))
        if interval not in MAIN_TIMEFRAME_MS:
            issues.append("Replay interval is not supported.")
        if end_time <= start_time:
            issues.append("End time must be after start time.")
        if initial_capital_usd <= 0:
            issues.append("Initial capital must be greater than zero.")
        action_types = self._action_types_in_rules(rules_json)
        unsupported = sorted(action_type for action_type in action_types if action_type in UNSUPPORTED_ACTION_TYPES)
        if unsupported:
            issues.append(
                "This bot uses actions that are not supported in v1 backtesting: "
                + ", ".join(action.replace("_", " ") for action in unsupported)
                + "."
            )
        if MARKET_UNIVERSE_SYMBOL in self._symbols_in_rules(rules_json) and not self._market_scope_symbols(str(bot.get("market_scope") or "")):
            issues.append("Bot market universe blocks need explicit selected markets in market scope for v1 backtests.")
        return issues

    def _failed_result(
        self,
        *,
        bot: dict[str, Any],
        interval: str,
        start_time: int,
        end_time: int,
        initial_capital_usd: float,
        assumptions: dict[str, float],
        preflight_issues: list[str] | None = None,
        execution_issues: list[str] | None = None,
    ) -> dict[str, Any]:
        symbols = sorted(self._extract_symbols(bot.get("rules_json") if isinstance(bot.get("rules_json"), dict) else {}))
        primary_symbol = symbols[0] if symbols else None
        issues_are_preflight = bool(preflight_issues)
        failed_assumption = (
            "This run failed during preflight and did not execute the replay engine."
            if issues_are_preflight
            else "This run failed while loading market data or replaying the strategy."
        )
        return {
            "equity_curve": [],
            "price_series": {"primary_symbol": primary_symbol, "series_by_symbol": {}},
            "trades": [],
            "trigger_events": [],
            "summary": {
                "primary_symbol": primary_symbol,
                "symbols": symbols,
                "interval": interval,
                "initial_capital_usd": round(initial_capital_usd, 8),
                "ending_equity": round(initial_capital_usd, 8),
                "realized_pnl": 0.0,
                "unrealized_pnl": 0.0,
                "gross_pnl_total": 0.0,
                "pnl_total": 0.0,
                "pnl_total_pct": 0.0,
                "max_drawdown_pct": 0.0,
                "win_rate": 0.0,
                "trade_count": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "avg_trade_duration_seconds": 0.0,
                "fees_paid_usd": 0.0,
                "funding_pnl_usd": 0.0,
            },
            "assumption_config": assumptions,
            "assumptions": [
                failed_assumption,
            ],
            "preflight_issues": preflight_issues or [],
            "execution_issues": execution_issues or [],
            "requested_range": {
                "start_time": start_time,
                "end_time": end_time,
            },
        }

    def _build_evaluation_rulesets(self, rules_json: dict[str, Any], placeholder_symbols: list[str]) -> list[dict[str, Any]]:
        if MARKET_UNIVERSE_SYMBOL not in self._symbols_in_rules(rules_json):
            return [deepcopy(rules_json)]
        return [self._replace_market_universe_symbol(rules_json, symbol) for symbol in placeholder_symbols]

    def _execute_action(
        self,
        *,
        action: dict[str, Any],
        timestamp_ms: int,
        current_candle_by_symbol: dict[str, dict[str, Any]],
        positions: dict[str, dict[str, Any]],
        position_lookup: dict[str, dict[str, Any]],
        trade_counter: int,
        assumptions: dict[str, float],
    ) -> dict[str, Any]:
        del position_lookup
        action_type = str(action.get("type") or "").strip()
        symbol = normalize_symbol(action.get("symbol"))
        current_candle = current_candle_by_symbol.get(symbol)
        current_price = self._to_float((current_candle or {}).get("close"), 0.0)

        if action_type == "update_leverage":
            position = positions.get(symbol)
            leverage = max(1.0, self._to_float(action.get("leverage"), position.get("leverage", 1.0) if position else 1.0))
            if position is None:
                return {"executed": False, "trade_counter": trade_counter, "symbol": symbol, "detail": f"No open {symbol} position to update leverage."}
            position["leverage"] = leverage
            position["margin"] = position["notional_usd"] / leverage if leverage > 0 else position["notional_usd"]
            return {"executed": True, "trade_counter": trade_counter, "symbol": symbol, "detail": f"Updated {symbol} leverage to {leverage:.2f}x."}

        if action_type == "set_tpsl":
            position = positions.get(symbol)
            if position is None:
                return {"executed": False, "trade_counter": trade_counter, "symbol": symbol, "detail": f"No open {symbol} position available for TP/SL."}
            take_profit_pct = self._to_float(action.get("take_profit_pct"), 0.0)
            stop_loss_pct = self._to_float(action.get("stop_loss_pct"), 0.0)
            self._apply_tpsl(position, take_profit_pct=take_profit_pct, stop_loss_pct=stop_loss_pct)
            return {
                "executed": True,
                "trade_counter": trade_counter,
                "symbol": symbol,
                "detail": f"Attached TP {take_profit_pct:.2f}% and SL {stop_loss_pct:.2f}% to {symbol}.",
            }

        if action_type == "close_position":
            position = positions.get(symbol)
            if position is None or current_price <= 0:
                return {"executed": False, "trade_counter": trade_counter, "symbol": symbol, "detail": f"No open {symbol} position to close."}
            execution_price = self._apply_execution_slippage(
                price=current_price,
                side=str(position.get("side") or ""),
                intent="exit",
                slippage_bps=assumptions["slippage_bps"],
            )
            closed_trade = self._close_position(
                position=position,
                exit_price=execution_price,
                timestamp_ms=timestamp_ms,
                reason="action_close",
                assumptions=assumptions,
            )
            return {
                "executed": True,
                "trade_counter": trade_counter,
                "symbol": symbol,
                "closed_trade": closed_trade,
                "removed_symbols": [symbol],
                "detail": self._build_close_detail(symbol=symbol, closed_trade=closed_trade),
            }

        if action_type in {"open_long", "open_short", "place_market_order"}:
            if current_price <= 0:
                return {"executed": False, "trade_counter": trade_counter, "symbol": symbol, "detail": f"Price unavailable for {symbol}."}
            if action_type == "place_market_order" and self._to_bool(action.get("reduce_only")):
                position = positions.get(symbol)
                if position is None:
                    return {"executed": False, "trade_counter": trade_counter, "symbol": symbol, "detail": f"No open {symbol} position available for reduce-only execution."}
                execution_price = self._apply_execution_slippage(
                    price=current_price,
                    side=str(position.get("side") or ""),
                    intent="exit",
                    slippage_bps=assumptions["slippage_bps"],
                )
                closed_trade = self._close_position(
                    position=position,
                    exit_price=execution_price,
                    timestamp_ms=timestamp_ms,
                    reason="reduce_only_close",
                    assumptions=assumptions,
                )
                return {
                    "executed": True,
                    "trade_counter": trade_counter,
                    "symbol": symbol,
                    "closed_trade": closed_trade,
                    "removed_symbols": [symbol],
                    "detail": self._build_close_detail(symbol=symbol, closed_trade=closed_trade),
                }
            target_side = self._resolve_target_side(action)
            existing_position = positions.get(symbol)
            removed_symbols: list[str] = []
            closed_trade: dict[str, Any] | None = None
            if existing_position is not None:
                if existing_position["side"] == target_side:
                    return {
                        "executed": False,
                        "trade_counter": trade_counter,
                        "symbol": symbol,
                        "detail": f"{symbol} already has an open {target_side} position.",
                    }
                reversal_exit_price = self._apply_execution_slippage(
                    price=current_price,
                    side=str(existing_position.get("side") or ""),
                    intent="exit",
                    slippage_bps=assumptions["slippage_bps"],
                )
                closed_trade = self._close_position(
                    position=existing_position,
                    exit_price=reversal_exit_price,
                    timestamp_ms=timestamp_ms,
                    reason="action_reverse",
                    assumptions=assumptions,
                )
                removed_symbols.append(symbol)
            trade_counter += 1
            execution_price = self._apply_execution_slippage(
                price=current_price,
                side=target_side,
                intent="entry",
                slippage_bps=assumptions["slippage_bps"],
            )
            opened_position = self._open_position(
                action=action,
                symbol=symbol,
                side=target_side,
                entry_price=execution_price,
                timestamp_ms=timestamp_ms,
                trade_id=f"trade-{trade_counter}",
                assumptions=assumptions,
            )
            detail_prefix = "Reversed" if closed_trade is not None else "Opened"
            return {
                "executed": True,
                "trade_counter": trade_counter,
                "symbol": symbol,
                "closed_trade": closed_trade,
                "opened_position": opened_position,
                "removed_symbols": removed_symbols,
                "detail": self._build_open_detail(symbol=symbol, side=target_side, position=opened_position, prefix=detail_prefix),
            }

        return {
            "executed": False,
            "trade_counter": trade_counter,
            "symbol": symbol,
            "detail": f"{action_type.replace('_', ' ')} is not supported in backtesting.",
        }

    def _open_position(
        self,
        *,
        action: dict[str, Any],
        symbol: str,
        side: str,
        entry_price: float,
        timestamp_ms: int,
        trade_id: str,
        assumptions: dict[str, float],
    ) -> dict[str, Any]:
        leverage = max(1.0, self._to_float(action.get("leverage"), 1.0))
        size_usd = self._to_float(action.get("size_usd"), 0.0)
        quantity = self._to_float(action.get("quantity"), 0.0)
        notional_usd = size_usd if size_usd > 0 else quantity * entry_price
        if notional_usd <= 0:
            notional_usd = entry_price
        amount = quantity if quantity > 0 else notional_usd / entry_price
        entry_fee_usd = round(notional_usd * (assumptions["fee_bps"] / 10_000.0), 8)
        position = {
            "trade_id": trade_id,
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "entry_price": entry_price,
            "notional_usd": notional_usd,
            "leverage": leverage,
            "margin": notional_usd / leverage if leverage > 0 else notional_usd,
            "opened_at_ms": timestamp_ms,
            "opened_at": self._iso_from_ms(timestamp_ms),
            "take_profit_price": None,
            "stop_loss_price": None,
            "entry_fee_usd": entry_fee_usd,
            "accrued_funding_pnl_usd": 0.0,
        }
        self._apply_tpsl(
            position,
            take_profit_pct=self._to_float(action.get("take_profit_pct"), 0.0),
            stop_loss_pct=self._to_float(action.get("stop_loss_pct"), 0.0),
        )
        return position

    def _apply_tpsl(self, position: dict[str, Any], *, take_profit_pct: float, stop_loss_pct: float) -> None:
        entry_price = self._to_float(position.get("entry_price"), 0.0)
        side = str(position.get("side") or "").strip()
        if entry_price <= 0 or side not in {"long", "short"}:
            return
        if take_profit_pct > 0:
            position["take_profit_price"] = entry_price * (1 + take_profit_pct / 100.0) if side == "long" else entry_price * (1 - take_profit_pct / 100.0)
        if stop_loss_pct > 0:
            position["stop_loss_price"] = entry_price * (1 - stop_loss_pct / 100.0) if side == "long" else entry_price * (1 + stop_loss_pct / 100.0)

    def _close_position(
        self,
        *,
        position: dict[str, Any],
        exit_price: float,
        timestamp_ms: int,
        reason: str,
        assumptions: dict[str, float],
    ) -> dict[str, Any]:
        amount = self._to_float(position.get("amount"), 0.0)
        entry_price = self._to_float(position.get("entry_price"), 0.0)
        side = str(position.get("side") or "").strip()
        direction = 1.0 if side == "long" else -1.0
        gross_pnl_usd = (exit_price - entry_price) * amount * direction
        margin = self._to_float(position.get("margin"), 0.0)
        entry_fee_usd = self._to_float(position.get("entry_fee_usd"), 0.0)
        exit_fee_usd = abs(exit_price * amount) * (assumptions["fee_bps"] / 10_000.0)
        funding_pnl_usd = self._to_float(position.get("accrued_funding_pnl_usd"), 0.0)
        fees_paid_usd = entry_fee_usd + exit_fee_usd
        pnl_usd = gross_pnl_usd + funding_pnl_usd - fees_paid_usd
        duration_seconds = max(0, (timestamp_ms - int(position.get("opened_at_ms") or timestamp_ms)) // 1000)
        return {
            "trade_id": position.get("trade_id"),
            "symbol": position.get("symbol"),
            "side": side,
            "status": "closed",
            "entry_time": position.get("opened_at"),
            "exit_time": self._iso_from_ms(timestamp_ms),
            "entry_price": round(entry_price, 8),
            "exit_price": round(exit_price, 8),
            "quantity": round(amount, 8),
            "notional_usd": round(self._to_float(position.get("notional_usd"), 0.0), 8),
            "leverage": round(self._to_float(position.get("leverage"), 1.0), 8),
            "gross_pnl_usd": round(gross_pnl_usd, 8),
            "fees_paid_usd": round(fees_paid_usd, 8),
            "funding_pnl_usd": round(funding_pnl_usd, 8),
            "pnl_usd": round(pnl_usd, 8),
            "pnl_pct": round((pnl_usd / margin * 100.0) if margin > 0 else 0.0, 8),
            "duration_seconds": duration_seconds,
            "close_reason": reason,
        }

    def _open_trade_snapshot(self, *, position: dict[str, Any], mark_price: float) -> dict[str, Any]:
        amount = self._to_float(position.get("amount"), 0.0)
        entry_price = self._to_float(position.get("entry_price"), 0.0)
        side = str(position.get("side") or "").strip()
        direction = 1.0 if side == "long" else -1.0
        gross_unrealized_pnl = (mark_price - entry_price) * amount * direction
        margin = self._to_float(position.get("margin"), 0.0)
        fees_paid_usd = self._to_float(position.get("entry_fee_usd"), 0.0)
        funding_pnl_usd = self._to_float(position.get("accrued_funding_pnl_usd"), 0.0)
        unrealized_pnl = gross_unrealized_pnl + funding_pnl_usd - fees_paid_usd
        return {
            "trade_id": position.get("trade_id"),
            "symbol": position.get("symbol"),
            "side": side,
            "status": "open",
            "entry_time": position.get("opened_at"),
            "exit_time": None,
            "entry_price": round(entry_price, 8),
            "exit_price": None,
            "quantity": round(amount, 8),
            "notional_usd": round(self._to_float(position.get("notional_usd"), 0.0), 8),
            "leverage": round(self._to_float(position.get("leverage"), 1.0), 8),
            "gross_pnl_usd": round(gross_unrealized_pnl, 8),
            "fees_paid_usd": round(fees_paid_usd, 8),
            "funding_pnl_usd": round(funding_pnl_usd, 8),
            "pnl_usd": None,
            "pnl_pct": None,
            "duration_seconds": None,
            "close_reason": None,
            "unrealized_pnl": round(unrealized_pnl, 8),
            "unrealized_pnl_pct": round((unrealized_pnl / margin * 100.0) if margin > 0 else 0.0, 8),
        }

    def _resolve_protection_exit(self, *, position: dict[str, Any], candle: dict[str, Any]) -> dict[str, Any] | None:
        side = str(position.get("side") or "").strip()
        high = self._to_float(candle.get("high"), 0.0)
        low = self._to_float(candle.get("low"), 0.0)
        take_profit_price = self._to_float(position.get("take_profit_price"), 0.0)
        stop_loss_price = self._to_float(position.get("stop_loss_price"), 0.0)
        if side == "long":
            hit_take_profit = take_profit_price > 0 and high >= take_profit_price
            hit_stop_loss = stop_loss_price > 0 and low <= stop_loss_price
        else:
            hit_take_profit = take_profit_price > 0 and low <= take_profit_price
            hit_stop_loss = stop_loss_price > 0 and high >= stop_loss_price
        if hit_take_profit and hit_stop_loss:
            return {"reason": "stop_loss", "exit_price": stop_loss_price}
        if hit_stop_loss:
            return {"reason": "stop_loss", "exit_price": stop_loss_price}
        if hit_take_profit:
            return {"reason": "take_profit", "exit_price": take_profit_price}
        return None

    def _slice_candle_lookup(
        self,
        candle_lookup: dict[str, dict[str, list[dict[str, Any]]]],
        close_time_lookup: dict[tuple[str, str], list[int]],
        timestamp_ms: int,
    ) -> dict[str, dict[str, list[dict[str, Any]]]]:
        sliced: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for symbol, timeframe_rows in candle_lookup.items():
            for timeframe, candles in timeframe_rows.items():
                close_times = close_time_lookup.get((symbol, timeframe), [])
                end_index = bisect_right(close_times, timestamp_ms)
                if end_index <= 0:
                    continue
                sliced.setdefault(symbol, {})[timeframe] = candles[:end_index]
        return sliced

    def _position_snapshot(self, *, position: dict[str, Any], mark_price: float) -> dict[str, Any]:
        amount = self._to_float(position.get("amount"), 0.0)
        entry_price = self._to_float(position.get("entry_price"), 0.0)
        side = str(position.get("side") or "").strip()
        direction = 1.0 if side == "long" else -1.0
        gross_unrealized_pnl = (mark_price - entry_price) * amount * direction
        margin = self._to_float(position.get("margin"), 0.0)
        fees_paid_usd = self._to_float(position.get("entry_fee_usd"), 0.0)
        funding_pnl_usd = self._to_float(position.get("accrued_funding_pnl_usd"), 0.0)
        unrealized_pnl = gross_unrealized_pnl + funding_pnl_usd - fees_paid_usd
        return {
            "amount": amount,
            "side": side,
            "entry_price": entry_price,
            "mark_price": mark_price,
            "margin": margin,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_pnl_pct": (unrealized_pnl / margin * 100.0) if margin > 0 else 0.0,
        }

    def _normalize_assumptions(self, assumptions: dict[str, Any] | None) -> dict[str, float]:
        raw = assumptions if isinstance(assumptions, dict) else {}
        return {
            "fee_bps": max(0.0, self._to_float(raw.get("fee_bps"), DEFAULT_BACKTEST_ASSUMPTIONS["fee_bps"])),
            "slippage_bps": max(0.0, self._to_float(raw.get("slippage_bps"), DEFAULT_BACKTEST_ASSUMPTIONS["slippage_bps"])),
            "funding_bps_per_interval": self._to_float(
                raw.get("funding_bps_per_interval"),
                DEFAULT_BACKTEST_ASSUMPTIONS["funding_bps_per_interval"],
            ),
        }

    def _build_assumptions_text(
        self,
        *,
        assumptions: dict[str, float],
        missing_main_symbols: set[str],
    ) -> list[str]:
        lines = [
            "Entries and exits execute on candle close.",
            "Take-profit and stop-loss checks use candle high/low on later bars.",
            "If both TP and SL are touched in one bar, the replay picks the less favorable exit.",
        ]
        if assumptions["fee_bps"] > 0:
            lines.append(f"Trading fees are modeled at {assumptions['fee_bps']:.2f} bps on entry and exit.")
        else:
            lines.append("Trading fees are disabled for this replay.")
        if assumptions["slippage_bps"] > 0:
            lines.append(f"Market fills include {assumptions['slippage_bps']:.2f} bps of adverse slippage.")
        else:
            lines.append("Market fills assume zero slippage.")
        if assumptions["funding_bps_per_interval"] != 0:
            lines.append(
                f"Funding is applied every replay bar at {assumptions['funding_bps_per_interval']:.2f} bps; positive values charge longs and credit shorts."
            )
        else:
            lines.append("Funding is disabled for this replay.")
        if missing_main_symbols:
            lines.append("Symbols without main-interval history are skipped instead of failing the entire replay.")
        return lines

    def _accrue_funding(
        self,
        *,
        positions: dict[str, dict[str, Any]],
        current_candle_by_symbol: dict[str, dict[str, Any]],
        assumptions: dict[str, float],
    ) -> None:
        funding_rate = assumptions["funding_bps_per_interval"] / 10_000.0
        if funding_rate == 0.0:
            return
        for symbol, position in positions.items():
            candle = current_candle_by_symbol.get(symbol)
            if candle is None:
                continue
            mark_price = self._to_float(candle.get("close"), 0.0)
            amount = self._to_float(position.get("amount"), 0.0)
            side = str(position.get("side") or "").strip().lower()
            if mark_price <= 0 or amount <= 0 or side not in {"long", "short"}:
                continue
            notional_usd = abs(mark_price * amount)
            direction = -1.0 if side == "long" else 1.0
            position["accrued_funding_pnl_usd"] = self._to_float(position.get("accrued_funding_pnl_usd"), 0.0) + (
                notional_usd * funding_rate * direction
            )

    def _apply_execution_slippage(self, *, price: float, side: str, intent: str, slippage_bps: float) -> float:
        if price <= 0 or slippage_bps <= 0:
            return price
        slip = slippage_bps / 10_000.0
        normalized_side = side.strip().lower()
        if intent == "entry":
            return price * (1.0 + slip) if normalized_side == "long" else price * (1.0 - slip)
        return price * (1.0 - slip) if normalized_side == "long" else price * (1.0 + slip)

    def _build_open_detail(self, *, symbol: str, side: str, position: dict[str, Any], prefix: str) -> str:
        return (
            f"{prefix} {side} on {symbol} at {self._to_float(position.get('entry_price'), 0.0):.4f}. "
            f"Entry fee ${self._to_float(position.get('entry_fee_usd'), 0.0):.2f}."
        )

    def _build_close_detail(self, *, symbol: str, closed_trade: dict[str, Any]) -> str:
        pnl_usd = self._to_float(closed_trade.get("pnl_usd"), 0.0)
        return (
            f"Closed {symbol} at {self._to_float(closed_trade.get('exit_price'), 0.0):.4f}. "
            f"Net {pnl_usd:+.2f} after ${self._to_float(closed_trade.get('fees_paid_usd'), 0.0):.2f} fees."
        )

    def _extract_failure_reason(self, *, result_json: dict[str, Any], status: str) -> str | None:
        if status != "failed":
            return None
        for issue_key in ("preflight_issues", "execution_issues"):
            issues = result_json.get(issue_key)
            if not isinstance(issues, list):
                continue
            for issue in issues:
                text = str(issue).strip()
                if text:
                    return text
        return "Backtest failed."

    @staticmethod
    def _resolve_target_side(action: dict[str, Any]) -> str:
        action_type = str(action.get("type") or "").strip()
        if action_type == "open_short":
            return "short"
        if action_type == "open_long":
            return "long"
        raw_side = str(action.get("side") or "").strip().lower()
        return "short" if raw_side == "short" else "long"

    @staticmethod
    def _market_snapshot_from_candle(symbol: str, candle: dict[str, Any]) -> dict[str, Any]:
        return {
            "mark_price": BotBacktestService._to_float(candle.get("close"), 0.0),
            "funding_rate": 0.0,
            "volume_24h": BotBacktestService._to_float(candle.get("volume"), 0.0),
            "updated_at": BotBacktestService._iso_from_ms(int(candle.get("close_time") or 0)),
            "symbol": symbol,
        }

    @staticmethod
    def _max_drawdown_pct(equity_curve: list[dict[str, Any]]) -> float:
        peak = None
        worst_drawdown = 0.0
        for point in equity_curve:
            equity = BotBacktestService._to_float(point.get("equity"), 0.0)
            peak = equity if peak is None else max(peak, equity)
            if peak <= 0:
                continue
            drawdown = ((peak - equity) / peak) * 100.0
            worst_drawdown = max(worst_drawdown, drawdown)
        return worst_drawdown

    def _resolve_bot(self, *, bot_id: str, wallet_address: str, user_id: str) -> dict[str, Any]:
        del user_id
        bot = self._supabase.maybe_one("bot_definitions", filters={"id": bot_id, "wallet_address": wallet_address})
        if bot is None:
            raise ValueError("Bot not found")
        return bot

    @staticmethod
    def serialize_run_summary(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "bot_definition_id": row["bot_definition_id"],
            "bot_name_snapshot": row["bot_name_snapshot"],
            "market_scope_snapshot": row.get("market_scope_snapshot"),
            "strategy_type_snapshot": row.get("strategy_type_snapshot"),
            "interval": row["interval"],
            "start_time": row["start_time"],
            "end_time": row["end_time"],
            "initial_capital_usd": row["initial_capital_usd"],
            "execution_model": row["execution_model"],
            "pnl_total": row["pnl_total"],
            "pnl_total_pct": row["pnl_total_pct"],
            "max_drawdown_pct": row["max_drawdown_pct"],
            "win_rate": row["win_rate"],
            "trade_count": row["trade_count"],
            "status": row["status"],
            "assumption_config_json": row.get("assumption_config_json") if isinstance(row.get("assumption_config_json"), dict) else {},
            "failure_reason": row.get("failure_reason"),
            "created_at": row["created_at"],
            "completed_at": row.get("completed_at"),
            "updated_at": row["updated_at"],
        }

    @classmethod
    def serialize_run_detail(cls, row: dict[str, Any]) -> dict[str, Any]:
        return {
            **cls.serialize_run_summary(row),
            "user_id": row["user_id"],
            "wallet_address": row["wallet_address"],
            "rules_snapshot_json": row["rules_snapshot_json"],
            "result_json": row.get("result_json") if isinstance(row.get("result_json"), dict) else {},
        }

    def _action_types_in_rules(self, rules_json: dict[str, Any]) -> set[str]:
        action_types: set[str] = set()
        actions = rules_json.get("actions")
        if isinstance(actions, list):
            for action in actions:
                if isinstance(action, dict):
                    action_type = str(action.get("type") or "").strip()
                    if action_type:
                        action_types.add(action_type)
        graph = rules_json.get("graph")
        if isinstance(graph, dict):
            nodes = graph.get("nodes")
            if isinstance(nodes, list):
                for node in nodes:
                    if not isinstance(node, dict) or str(node.get("kind") or "").strip() != "action":
                        continue
                    config = node.get("config")
                    if not isinstance(config, dict):
                        continue
                    action_type = str(config.get("type") or "").strip()
                    if action_type:
                        action_types.add(action_type)
        return action_types

    def _symbols_in_rules(self, rules_json: dict[str, Any]) -> set[str]:
        symbols: set[str] = set()
        for group in ("conditions", "actions"):
            rows = rules_json.get(group)
            if not isinstance(rows, list):
                continue
            for row in rows:
                if not isinstance(row, dict):
                    continue
                symbol = str(row.get("symbol") or "").strip()
                if symbol:
                    symbols.add(symbol)
        graph = rules_json.get("graph")
        if isinstance(graph, dict):
            nodes = graph.get("nodes")
            if isinstance(nodes, list):
                for node in nodes:
                    if not isinstance(node, dict):
                        continue
                    config = node.get("config")
                    if not isinstance(config, dict):
                        continue
                    symbol = str(config.get("symbol") or "").strip()
                    if symbol:
                        symbols.add(symbol)
        return symbols

    def _extract_symbols(self, rules_json: dict[str, Any]) -> set[str]:
        return {
            normalize_symbol(symbol)
            for symbol in self._symbols_in_rules(rules_json)
            if symbol and symbol != MARKET_UNIVERSE_SYMBOL
        }

    def _replace_market_universe_symbol(self, value: Any, symbol: str) -> Any:
        if isinstance(value, dict):
            return {key: self._replace_market_universe_symbol(item, symbol) for key, item in value.items()}
        if isinstance(value, list):
            return [self._replace_market_universe_symbol(item, symbol) for item in value]
        if value == MARKET_UNIVERSE_SYMBOL:
            return symbol
        return deepcopy(value)

    @staticmethod
    def _market_scope_symbols(scope: str) -> list[str]:
        normalized = scope.strip()
        if not normalized or "all pacifica" in normalized.lower():
            return []
        tail = normalized.split("/")[-1]
        return [part for part in (normalize_symbol(piece) for piece in tail.split(",")) if part]

    @staticmethod
    def _to_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _now_iso() -> str:
        return datetime.now(tz=UTC).isoformat()

    @staticmethod
    def _iso_from_ms(value: int) -> str:
        return datetime.fromtimestamp(value / 1000.0, tz=UTC).isoformat()
