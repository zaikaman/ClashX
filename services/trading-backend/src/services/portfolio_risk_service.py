from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from src.services.bot_risk_service import BotRiskService


class PortfolioRiskService:
    DEFAULT_POLICY = {
        "max_drawdown_pct": 18.0,
        "max_member_drawdown_pct": 22.0,
        "min_trust_score": 55,
        "max_active_members": 5,
        "auto_pause_on_source_stale": True,
        "kill_switch_on_breach": True,
    }

    def __init__(self) -> None:
        self._bot_risk = BotRiskService()

    def normalize_policy(self, policy: dict[str, Any] | None) -> dict[str, Any]:
        merged = dict(self.DEFAULT_POLICY)
        if isinstance(policy, dict):
            merged.update(policy)
        return {
            "max_drawdown_pct": max(5.0, self._to_float(merged.get("max_drawdown_pct"), 18.0)),
            "max_member_drawdown_pct": max(5.0, self._to_float(merged.get("max_member_drawdown_pct"), 22.0)),
            "min_trust_score": max(0, min(100, int(self._to_float(merged.get("min_trust_score"), 55)))),
            "max_active_members": max(1, int(self._to_float(merged.get("max_active_members"), 5))),
            "auto_pause_on_source_stale": self._to_bool(merged.get("auto_pause_on_source_stale"), True),
            "kill_switch_on_breach": self._to_bool(merged.get("kill_switch_on_breach"), True),
        }

    def resolve_target_scale_bps(
        self,
        *,
        target_notional_usd: float,
        source_runtime: dict[str, Any],
        max_scale_bps: int,
    ) -> int:
        source_policy = self._bot_risk.normalize_policy(
            source_runtime.get("risk_policy_json") if isinstance(source_runtime.get("risk_policy_json"), dict) else {}
        )
        source_capital = max(1.0, self._to_float(source_policy.get("allocated_capital_usd"), 200.0))
        raw_scale = int(round(((max(1.0, target_notional_usd) / source_capital) * 10_000) / 500.0) * 500)
        return max(500, min(max(500, int(max_scale_bps)), raw_scale))

    def should_rebalance(
        self,
        *,
        basket: dict[str, Any],
        member_contexts: list[dict[str, Any]],
    ) -> bool:
        if str(basket.get("status") or "") != "active":
            return False
        mode = str(basket.get("rebalance_mode") or "drift")
        drift_threshold_pct = max(0.5, self._to_float(basket.get("drift_threshold_pct"), 6.0))
        if any(self._member_scale_drift_pct(context) >= drift_threshold_pct for context in member_contexts):
            return True
        if mode == "manual":
            return False
        interval_minutes = max(5, int(self._to_float(basket.get("rebalance_interval_minutes"), 60)))
        last_rebalanced_at = self._as_datetime(basket.get("last_rebalanced_at"))
        if last_rebalanced_at is None:
            return True
        return datetime.now(tz=UTC) - last_rebalanced_at >= timedelta(minutes=interval_minutes)

    def evaluate_portfolio(
        self,
        *,
        basket: dict[str, Any],
        risk_policy: dict[str, Any],
        member_contexts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        normalized_policy = self.normalize_policy(risk_policy)
        active_members = [context for context in member_contexts if str(context["member"].get("status") or "") == "active"]
        total_target_notional = sum(self._to_float(context["member"].get("target_notional_usd")) for context in active_members)
        current_total_notional = sum(
            self._to_float(context["relationship"].get("max_notional_usd"))
            or self._to_float(context["member"].get("target_notional_usd"))
            for context in active_members
            if isinstance(context.get("relationship"), dict) and str(context["relationship"].get("status") or "") == "active"
        )
        aggregate_live_pnl_usd = 0.0
        weighted_drawdown = 0.0
        alerts: list[str] = []
        worst_member_drawdown = 0.0
        trust_breach = False
        stale_source = False

        for context in active_members:
            member = context["member"]
            allocated_notional = max(1.0, self._to_float(member.get("target_notional_usd")))
            member_pnl_pct = self._to_float(context.get("member_live_pnl_pct"))
            member_drawdown_pct = self._to_float(context.get("member_drawdown_pct"))
            aggregate_live_pnl_usd += allocated_notional * (member_pnl_pct / 100.0)
            weighted_drawdown += allocated_notional * member_drawdown_pct
            worst_member_drawdown = max(worst_member_drawdown, member_drawdown_pct)
            trust_score = int(self._to_float(context.get("trust_score"), 0))
            trust_health = str(context.get("trust_health") or "")
            bot_name = str(context.get("bot_name") or "bot")
            if trust_score < normalized_policy["min_trust_score"]:
                trust_breach = True
                alerts.append(f"{bot_name} trust score fell below the portfolio floor.")
            if normalized_policy["auto_pause_on_source_stale"] and trust_health in {"stale", "offline", "failed"}:
                stale_source = True
                alerts.append(f"{bot_name} is no longer in a stable source runtime state.")
            if member_drawdown_pct >= normalized_policy["max_member_drawdown_pct"]:
                alerts.append(f"{bot_name} breached the per-member drawdown ceiling.")

        aggregate_drawdown_pct = (weighted_drawdown / total_target_notional) if total_target_notional > 0 else 0.0
        risk_budget_used_pct = (
            aggregate_drawdown_pct / normalized_policy["max_drawdown_pct"] * 100.0
            if normalized_policy["max_drawdown_pct"] > 0
            else 0.0
        )
        if len(active_members) > normalized_policy["max_active_members"]:
            alerts.append("The basket has more active members than the risk policy allows.")
        drawdown_breach = aggregate_drawdown_pct >= normalized_policy["max_drawdown_pct"]
        should_kill_switch = bool(
            drawdown_breach
            or worst_member_drawdown >= normalized_policy["max_member_drawdown_pct"]
            or trust_breach
            or stale_source
        )
        needs_rebalance = self.should_rebalance(basket=basket, member_contexts=member_contexts)

        status = str(basket.get("status") or "draft")
        if status == "killed":
            health = "killed"
        elif status in {"paused", "draft"}:
            health = status
        elif should_kill_switch:
            health = "risk"
        elif alerts or needs_rebalance:
            health = "watch"
        else:
            health = "healthy"

        return {
            "health": health,
            "total_target_notional_usd": round(total_target_notional, 2),
            "current_total_notional_usd": round(current_total_notional, 2),
            "aggregate_live_pnl_usd": round(aggregate_live_pnl_usd, 2),
            "aggregate_drawdown_pct": round(aggregate_drawdown_pct, 2),
            "risk_budget_used_pct": round(risk_budget_used_pct, 2),
            "should_kill_switch": should_kill_switch and normalized_policy["kill_switch_on_breach"],
            "needs_rebalance": needs_rebalance,
            "alert_count": len(alerts),
            "alerts": alerts[:8],
        }

    def build_member_snapshot(self, *, member: dict[str, Any], runtime: dict[str, Any], latest_snapshot: dict[str, Any] | None) -> dict[str, Any]:
        source_policy = self._bot_risk.normalize_policy(
            runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
        )
        source_state = source_policy.get("_runtime_state") if isinstance(source_policy.get("_runtime_state"), dict) else {}
        source_capital = max(1.0, self._to_float(source_policy.get("allocated_capital_usd"), 200.0))
        source_pnl_pct = (self._to_float(source_state.get("pnl_total_usd")) / source_capital) * 100.0
        source_drawdown_pct = self._to_float(source_state.get("drawdown_pct"), self._to_float((latest_snapshot or {}).get("drawdown")))
        return {
            "member_live_pnl_pct": round(source_pnl_pct, 2),
            "member_drawdown_pct": round(source_drawdown_pct, 2),
            "scale_drift_pct": round(self._member_scale_drift_pct({"member": member}), 2),
        }

    def _member_scale_drift_pct(self, context: dict[str, Any]) -> float:
        member = context["member"]
        target_scale = max(1.0, self._to_float(member.get("target_scale_bps"), 0.0))
        latest_scale = self._to_float(member.get("latest_scale_bps"), target_scale)
        relationship = context.get("relationship")
        if isinstance(relationship, dict):
            latest_scale = self._to_float(relationship.get("scale_bps"), latest_scale)
        return abs(latest_scale - target_scale) / target_scale * 100.0

    @staticmethod
    def _as_datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
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
