from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class BotRiskService:
    DEFAULT_POLICY = {
        "max_leverage": 5,
        "max_order_size_usd": 200,
        "allocated_capital_usd": 200,
        "max_open_positions": 1,
        "cooldown_seconds": 30,
        "max_drawdown_pct": 25,
        "allowed_symbols": [],
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
    ) -> list[str]:
        issues: list[str] = []
        normalized = self.normalize_policy(policy)
        action_type = str(action.get("type") or "")
        symbol = str(action.get("symbol") or "").upper().replace("-PERP", "")
        positions = position_lookup if isinstance(position_lookup, dict) else {}

        allowed_symbols = normalized.get("allowed_symbols") or []
        if symbol and allowed_symbols and symbol not in allowed_symbols:
            issues.append(f"symbol {symbol} is not in allowed_symbols policy")

        leverage = self._to_float(action.get("leverage"), 1.0)
        if action_type in {
            "open_long",
            "open_short",
            "place_market_order",
            "place_limit_order",
            "place_twap_order",
            "update_leverage",
        } and leverage > normalized["max_leverage"]:
            issues.append(f"requested leverage {leverage:g} exceeds max_leverage {normalized['max_leverage']}")

        size_usd = self._to_float(action.get("size_usd"), 0.0)
        if action_type in {"open_long", "open_short", "place_market_order", "place_limit_order", "place_twap_order"} and size_usd > normalized["max_order_size_usd"]:
            issues.append(
                f"requested size_usd {size_usd:g} exceeds max_order_size_usd {normalized['max_order_size_usd']:g}"
            )
        if action_type in {"open_long", "open_short", "place_market_order", "place_limit_order", "place_twap_order"}:
            open_positions = sum(1 for item in positions.values() if self._to_float(item.get("amount"), 0.0) > 0)
            if open_positions >= normalized["max_open_positions"]:
                issues.append(
                    f"max_open_positions {normalized['max_open_positions']} reached"
                )

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
