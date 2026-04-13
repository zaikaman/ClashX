from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class BotRiskService:
    VALID_SIZING_MODES = {"fixed_usd", "risk_adjusted"}
    DEFAULT_POLICY = {
        "max_leverage": 5,
        "max_order_size_usd": 200,
        "allocated_capital_usd": 200,
        "max_open_positions": 1,
        "cooldown_seconds": 30,
        "max_drawdown_pct": 25,
        "allowed_symbols": [],
        "sizing_mode": "fixed_usd",
        "fixed_usd_amount": 200,
        "risk_per_trade_pct": 1,
    }

    def normalize_policy(self, policy: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(self.DEFAULT_POLICY)
        if isinstance(policy, dict):
            merged.update({key: value for key, value in policy.items() if key != "_runtime_state"})
            if "_runtime_state" in policy and isinstance(policy["_runtime_state"], dict):
                merged["_runtime_state"] = dict(policy["_runtime_state"])
        else:
            merged["_runtime_state"] = {}

        merged["max_leverage"] = int(self._to_float(merged.get("max_leverage"), self.DEFAULT_POLICY["max_leverage"]))
        merged["max_order_size_usd"] = self._to_float(
            merged.get("max_order_size_usd"), self.DEFAULT_POLICY["max_order_size_usd"]
        )
        merged["allocated_capital_usd"] = max(
            1.0,
            self._to_float(
                merged.get("allocated_capital_usd"),
                self.DEFAULT_POLICY["allocated_capital_usd"],
            ),
        )
        merged["max_open_positions"] = max(
            1,
            int(self._to_float(merged.get("max_open_positions"), self.DEFAULT_POLICY["max_open_positions"])),
        )
        merged["cooldown_seconds"] = int(
            self._to_float(merged.get("cooldown_seconds"), self.DEFAULT_POLICY["cooldown_seconds"])
        )
        merged["max_drawdown_pct"] = self._to_float(
            merged.get("max_drawdown_pct"), self.DEFAULT_POLICY["max_drawdown_pct"]
        )
        sizing_mode = str(merged.get("sizing_mode") or self.DEFAULT_POLICY["sizing_mode"]).strip().lower()
        merged["sizing_mode"] = sizing_mode if sizing_mode in self.VALID_SIZING_MODES else self.DEFAULT_POLICY["sizing_mode"]
        merged["fixed_usd_amount"] = max(
            1.0,
            self._to_float(
                merged.get("fixed_usd_amount"),
                self.DEFAULT_POLICY["fixed_usd_amount"],
            ),
        )
        merged["risk_per_trade_pct"] = max(
            0.1,
            self._to_float(
                merged.get("risk_per_trade_pct"),
                self.DEFAULT_POLICY["risk_per_trade_pct"],
            ),
        )
        allowed_symbols = merged.get("allowed_symbols")
        if not isinstance(allowed_symbols, list):
            allowed_symbols = []
        merged["allowed_symbols"] = [str(symbol).upper().replace("-PERP", "") for symbol in allowed_symbols if str(symbol).strip()]
        merged.setdefault("_runtime_state", {})
        return merged

    def assess_action(
        self,
        *,
        policy: dict[str, Any],
        action: dict[str, Any],
        runtime_state: dict[str, Any],
        position_lookup: dict[str, dict[str, Any]] | None = None,
        open_order_lookup: dict[str, list[dict[str, Any]]] | None = None,
        market_lookup: dict[str, dict[str, Any]] | None = None,
    ) -> list[str]:
        issues: list[str] = []
        normalized = self.normalize_policy(policy)
        action_type = str(action.get("type") or "")
        order_action_types = {
            "open_long",
            "open_short",
            "place_market_order",
            "place_limit_order",
            "place_twap_order",
        }
        symbol = str(action.get("symbol") or "").upper().replace("-PERP", "")
        positions = position_lookup if isinstance(position_lookup, dict) else {}
        open_orders = open_order_lookup if isinstance(open_order_lookup, dict) else {}
        markets = market_lookup if isinstance(market_lookup, dict) else {}
        pending_entries = runtime_state.get("pending_entry_symbols")
        if not isinstance(pending_entries, dict):
            pending_entries = {}
        managed_positions = runtime_state.get("managed_positions")
        if not isinstance(managed_positions, dict):
            managed_positions = {}
        managed_position = managed_positions.get(symbol)
        if not isinstance(managed_position, dict):
            managed_position = {}

        allowed_symbols = normalized.get("allowed_symbols") or []
        live_position_symbols = self._live_position_symbols(
            position_lookup=positions,
            allowed_symbols=allowed_symbols,
        )
        reserved_entry_symbols = self._reserved_entry_symbols(
            managed_positions=managed_positions,
            pending_entries=pending_entries,
            live_position_symbols=live_position_symbols,
        )
        if symbol and allowed_symbols and symbol not in allowed_symbols:
            issues.append(f"symbol {symbol} is not in allowed_symbols policy")

        leverage = self._to_float(action.get("leverage"), 1.0)
        if action_type in order_action_types | {"update_leverage"} and leverage > normalized["max_leverage"]:
            issues.append(f"requested leverage {leverage:g} exceeds max_leverage {normalized['max_leverage']}")
        market = markets.get(symbol) if symbol else None
        market_max_leverage = self._to_float(market.get("max_leverage"), 0.0) if isinstance(market, dict) else 0.0
        if (
            action_type in order_action_types | {"update_leverage"}
            and market_max_leverage > 0
            and leverage > market_max_leverage
        ):
            issues.append(
                f"requested leverage {leverage:g} exceeds {symbol} market max_leverage {market_max_leverage:g}"
            )

        requested_order_value = self._resolve_order_value_usd(
            action=action,
            market=market,
        )
        if action_type in order_action_types and requested_order_value > normalized["max_order_size_usd"]:
            issues.append(
                f"requested order value {requested_order_value:g} exceeds max_order_size_usd {normalized['max_order_size_usd']:g}"
            )
        if action_type in order_action_types and self._is_reduce_only_order_action(action):
            if abs(self._to_float(managed_position.get("amount"), 0.0)) <= 0:
                issues.append(f"bot does not manage an open position on {symbol}")
        elif action_type in order_action_types:
            if len(reserved_entry_symbols) >= normalized["max_open_positions"] and symbol not in reserved_entry_symbols:
                issues.append(
                    f"max_open_positions {normalized['max_open_positions']} reached"
                )
            if abs(self._to_float(managed_position.get("amount"), 0.0)) > 0:
                issues.append(f"bot already manages an open position on {symbol}")
            elif symbol and symbol in live_position_symbols:
                issues.append(f"existing live position on {symbol} already consumes bot capacity")
            symbol_orders = open_orders.get(symbol) or []
            entry_client_order_id = str(managed_position.get("entry_client_order_id") or "").strip()
            if entry_client_order_id and any(
                str(item.get("client_order_id") or "").strip() == entry_client_order_id
                and not self._to_bool(item.get("reduce_only"), False)
                for item in symbol_orders
            ):
                issues.append(f"existing bot entry order on {symbol} is still open")
            if symbol and symbol in pending_entries:
                issues.append(f"pending entry on {symbol} is still syncing")

        if action_type == "set_tpsl":
            if abs(self._to_float(managed_position.get("amount"), 0.0)) <= 0:
                issues.append(f"bot does not manage an open position on {symbol}")
            symbol_position = positions.get(symbol) or {}
            if abs(self._to_float(symbol_position.get("amount"), 0.0)) <= 0 and symbol in pending_entries:
                issues.append(f"awaiting position sync on {symbol} before TP/SL")
            symbol_orders = open_orders.get(symbol) or []
            take_profit_client_order_id = str(managed_position.get("take_profit_client_order_id") or "").strip()
            stop_loss_client_order_id = str(managed_position.get("stop_loss_client_order_id") or "").strip()
            managed_amount = abs(self._to_float(managed_position.get("amount"), 0.0))
            symbol_amount = abs(self._to_float(symbol_position.get("amount"), 0.0))
            has_take_profit_order = any(self._is_take_profit_order(item) for item in symbol_orders)
            has_stop_loss_order = any(self._is_stop_loss_order(item) for item in symbol_orders)
            covers_full_position = (
                managed_amount > 0
                and symbol_amount > 0
                and abs(symbol_amount - managed_amount) <= max(1e-9, managed_amount * 0.001)
            )
            if take_profit_client_order_id and stop_loss_client_order_id:
                open_client_order_ids = {
                    str(item.get("client_order_id") or "").strip()
                    for item in symbol_orders
                    if str(item.get("client_order_id") or "").strip()
                }
                if {take_profit_client_order_id, stop_loss_client_order_id}.issubset(open_client_order_ids):
                    issues.append(f"existing protective order on {symbol} already covers this position")
                elif covers_full_position and has_take_profit_order and has_stop_loss_order:
                    issues.append(f"existing protective order on {symbol} already covers this position")
            elif covers_full_position and has_take_profit_order and has_stop_loss_order:
                issues.append(f"existing protective order on {symbol} already covers this position")

        if action_type == "close_position" and abs(self._to_float(managed_position.get("amount"), 0.0)) <= 0:
            issues.append(f"bot does not manage an open position on {symbol}")

        drawdown_reason = self.drawdown_breach_reason(policy=normalized, runtime_state=runtime_state)
        if drawdown_reason is not None:
            issues.append(drawdown_reason)

        cooldown_seconds = int(normalized["cooldown_seconds"])
        last_executed_at = runtime_state.get("last_executed_at")
        if cooldown_seconds > 0 and isinstance(last_executed_at, str):
            try:
                last_dt = datetime.fromisoformat(last_executed_at.replace("Z", "+00:00"))
                elapsed = (datetime.now(tz=UTC) - last_dt).total_seconds()
                if elapsed < cooldown_seconds:
                    issues.append(f"cooldown active for {int(cooldown_seconds - elapsed)} more seconds")
            except ValueError:
                pass

        return issues

    def mark_execution(
        self,
        *,
        policy: dict[str, Any],
        success: bool,
    ) -> dict[str, Any]:
        normalized = self.normalize_policy(policy)
        state = normalized.get("_runtime_state") or {}
        if not isinstance(state, dict):
            state = {}

        now_iso = datetime.now(tz=UTC).isoformat()
        state["last_executed_at"] = now_iso
        state["executions_total"] = int(state.get("executions_total") or 0) + 1
        if not success:
            state["failures_total"] = int(state.get("failures_total") or 0) + 1

        normalized["_runtime_state"] = state
        return normalized

    def sync_performance(
        self,
        *,
        policy: dict[str, Any],
        pnl_total: float,
        pnl_realized: float,
        pnl_unrealized: float,
    ) -> dict[str, Any]:
        normalized = self.normalize_policy(policy)
        state = normalized.get("_runtime_state") or {}
        if not isinstance(state, dict):
            state = {}

        allocated_capital = normalized["allocated_capital_usd"]
        drawdown_amount = max(0.0, -pnl_total)
        drawdown_pct = (drawdown_amount / allocated_capital * 100.0) if allocated_capital > 0 else 0.0
        state["allocated_capital_usd"] = round(allocated_capital, 4)
        state["realized_pnl_usd"] = round(pnl_realized, 4)
        state["unrealized_pnl_usd"] = round(pnl_unrealized, 4)
        state["pnl_total_usd"] = round(pnl_total, 4)
        state["drawdown_amount_usd"] = round(drawdown_amount, 4)
        state["drawdown_pct"] = round(drawdown_pct, 4)
        normalized["_runtime_state"] = state
        return normalized

    def drawdown_breach_reason(
        self,
        *,
        policy: dict[str, Any],
        runtime_state: dict[str, Any],
    ) -> str | None:
        normalized = self.normalize_policy(policy)
        drawdown_pct = self._to_float(runtime_state.get("drawdown_pct"), 0.0)
        if drawdown_pct < normalized["max_drawdown_pct"]:
            return None
        drawdown_amount = self._to_float(runtime_state.get("drawdown_amount_usd"), 0.0)
        allocated_capital = normalized["allocated_capital_usd"]
        return (
            f"runtime drawdown ${drawdown_amount:.2f} ({drawdown_pct:.2f}%) "
            f"has reached the allocation-based max_drawdown_pct {normalized['max_drawdown_pct']:.2f}% "
            f"on ${allocated_capital:.2f} allocated capital"
        )

    @staticmethod
    def _to_float(value: Any, default: float) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_bool(value: Any, default: bool) -> bool:
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

    def _is_reduce_only_order_action(self, action: dict[str, Any]) -> bool:
        action_type = str(action.get("type") or "")
        if action_type not in {"place_market_order", "place_limit_order", "place_twap_order"}:
            return False
        return self._to_bool(action.get("reduce_only"), False)

    def _resolve_order_value_usd(
        self,
        *,
        action: dict[str, Any],
        market: dict[str, Any] | None,
    ) -> float:
        quantity = self._to_float(action.get("quantity"), 0.0)
        if quantity > 0:
            reference_price = self._to_float(action.get("price"), 0.0)
            if reference_price <= 0 and isinstance(market, dict):
                reference_price = self._to_float(market.get("mark_price"), 0.0)
            if reference_price <= 0:
                return 0.0
            return quantity * reference_price
        size_usd = self._to_float(action.get("size_usd"), 0.0)
        if size_usd <= 0:
            return 0.0
        return size_usd

    def _is_take_profit_order(self, order: dict[str, Any]) -> bool:
        if not self._to_bool(order.get("reduce_only"), False):
            return False
        order_type = str(order.get("order_type") or order.get("kind") or "").strip().lower()
        return "take_profit" in order_type or order_type.startswith("tp")

    def _is_stop_loss_order(self, order: dict[str, Any]) -> bool:
        if not self._to_bool(order.get("reduce_only"), False):
            return False
        order_type = str(order.get("order_type") or order.get("kind") or "").strip().lower()
        return "stop_loss" in order_type or order_type.startswith("sl")

    def _live_position_symbols(
        self,
        *,
        position_lookup: dict[str, dict[str, Any]],
        allowed_symbols: list[str],
    ) -> set[str]:
        allowed = {str(symbol).upper().replace("-PERP", "") for symbol in allowed_symbols if str(symbol).strip()}
        live_symbols: set[str] = set()
        for raw_symbol, position in position_lookup.items():
            if not isinstance(position, dict):
                continue
            symbol = str(position.get("symbol") or raw_symbol).upper().replace("-PERP", "")
            if not symbol or (allowed and symbol not in allowed):
                continue
            if abs(self._to_float(position.get("amount"), 0.0)) <= 0:
                continue
            live_symbols.add(symbol)
        return live_symbols

    def _reserved_entry_symbols(
        self,
        *,
        managed_positions: dict[str, Any],
        pending_entries: dict[str, Any],
        live_position_symbols: set[str],
    ) -> set[str]:
        reserved_symbols = {
            str(item.get("symbol") or symbol).strip().upper().replace("-PERP", "")
            for symbol, item in managed_positions.items()
            if isinstance(item, dict) and abs(self._to_float(item.get("amount"), 0.0)) > 0
        }
        reserved_symbols.update(
            str(symbol).strip().upper().replace("-PERP", "")
            for symbol in pending_entries
            if str(symbol).strip()
        )
        reserved_symbols.update(live_position_symbols)
        reserved_symbols.discard("")
        return reserved_symbols
