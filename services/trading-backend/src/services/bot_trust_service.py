from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.services.bot_builder_service import BotBuilderService
from src.services.bot_risk_service import BotRiskService
from src.services.supabase_rest import SupabaseRestClient, SupabaseRestError


class BotTrustService:
    HEALTH_UPTIME_MAP = {
        "healthy": 99.2,
        "degraded": 93.0,
        "paused": 88.0,
        "stale": 81.0,
        "offline": 63.0,
        "failed": 41.0,
        "stopped": 38.0,
    }

    def __init__(self) -> None:
        self.supabase = SupabaseRestClient()
        self.risk_service = BotRiskService()
        self.builder_service = BotBuilderService()

    def build_public_runtime_context(
        self,
        *,
        runtime: dict[str, Any],
        definition: dict[str, Any],
        latest_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        health_metrics = self._runtime_health_metrics(runtime)
        drift = self._build_drift(definition=definition, runtime=runtime, latest_snapshot=latest_snapshot)
        trust = self._build_trust(
            runtime=runtime,
            latest_snapshot=latest_snapshot,
            health_metrics=health_metrics,
            drift=drift,
        )
        passport = self._build_passport(definition=definition)
        return {
            "trust": trust,
            "drift": drift,
            "passport": passport,
        }

    def get_creator_profile(self, *, creator_id: str, include_bots: bool = False) -> dict[str, Any]:
        user = self.supabase.maybe_one("users", filters={"id": creator_id})
        if user is None:
            raise ValueError("Creator not found")

        definitions = self.supabase.select(
            "bot_definitions",
            filters={"user_id": creator_id, "visibility": "public"},
            order="updated_at.desc",
        )
        definition_ids = [row["id"] for row in definitions]
        runtimes = self.supabase.select("bot_runtimes", filters={"bot_definition_id": ("in", definition_ids)}) if definition_ids else []
        runtime_by_definition = {row["bot_definition_id"]: row for row in runtimes}
        runtime_ids = [row["id"] for row in runtimes]
        relationships = (
            self.supabase.select("bot_copy_relationships", filters={"source_runtime_id": ("in", runtime_ids)})
            if runtime_ids
            else []
        )
        clones = (
            self.supabase.select("bot_clones", filters={"source_bot_definition_id": ("in", definition_ids)})
            if definition_ids
            else []
        )

        public_bots: list[dict[str, Any]] = []
        trust_scores: list[int] = []
        best_rank: int | None = None
        for definition in definitions:
            runtime = runtime_by_definition.get(definition["id"])
            if runtime is None:
                continue
            latest_snapshot = self.supabase.maybe_one(
                "bot_leaderboard_snapshots",
                filters={"runtime_id": runtime["id"]},
                order="captured_at.desc",
            )
            context = self.build_public_runtime_context(
                runtime=runtime,
                definition=definition,
                latest_snapshot=latest_snapshot,
            )
            trust = context["trust"]
            drift = context["drift"]
            trust_scores.append(int(trust["trust_score"]))
            rank = int(latest_snapshot["rank"]) if latest_snapshot and latest_snapshot.get("rank") is not None else None
            if rank is not None:
                best_rank = rank if best_rank is None else min(best_rank, rank)
            public_bots.append(
                {
                    "runtime_id": runtime["id"],
                    "bot_definition_id": definition["id"],
                    "bot_name": definition["name"],
                    "strategy_type": definition["strategy_type"],
                    "rank": rank,
                    "pnl_total": float(latest_snapshot.get("pnl_total", 0.0) if latest_snapshot else 0.0),
                    "drawdown": float(latest_snapshot.get("drawdown", 0.0) if latest_snapshot else 0.0),
                    "trust_score": trust["trust_score"],
                    "risk_grade": trust["risk_grade"],
                    "drift_status": drift["status"],
                    "captured_at": latest_snapshot["captured_at"] if latest_snapshot else None,
                }
            )

        mirror_count = len(relationships)
        active_mirror_count = len([row for row in relationships if str(row.get("status") or "") == "active"])
        clone_count = len(clones)
        public_bot_count = len(definitions)
        active_runtime_count = len([row for row in runtimes if str(row.get("status") or "") == "active"])
        average_trust_score = round(sum(trust_scores) / len(trust_scores)) if trust_scores else 0
        reputation_score = self._creator_reputation_score(
            average_trust_score=average_trust_score,
            active_mirror_count=active_mirror_count,
            mirror_count=mirror_count,
            clone_count=clone_count,
            public_bot_count=public_bot_count,
            best_rank=best_rank,
        )
        reputation_label = self._reputation_label(reputation_score)
        tags = self._creator_tags(
            reputation_label=reputation_label,
            best_rank=best_rank,
            active_mirror_count=active_mirror_count,
            public_bot_count=public_bot_count,
        )

        payload = {
            "creator_id": creator_id,
            "wallet_address": user["wallet_address"],
            "display_name": user.get("display_name") or str(user["wallet_address"])[:8],
            "public_bot_count": public_bot_count,
            "active_runtime_count": active_runtime_count,
            "mirror_count": mirror_count,
            "active_mirror_count": active_mirror_count,
            "clone_count": clone_count,
            "average_trust_score": average_trust_score,
            "best_rank": best_rank,
            "reputation_score": reputation_score,
            "reputation_label": reputation_label,
            "summary": self._creator_summary(
                display_name=user.get("display_name") or str(user["wallet_address"])[:8],
                public_bot_count=public_bot_count,
                active_mirror_count=active_mirror_count,
                average_trust_score=average_trust_score,
            ),
            "tags": tags,
        }
        if include_bots:
            payload["bots"] = sorted(
                public_bots,
                key=lambda item: (
                    9999 if item["rank"] is None else item["rank"],
                    -float(item["trust_score"]),
                    str(item["bot_name"]),
                ),
            )
        return payload

    def _build_passport(self, *, definition: dict[str, Any]) -> dict[str, Any]:
        version_history = self.builder_service.list_strategy_versions(bot_id=str(definition["id"]), limit=6)
        publish_history = self.builder_service.list_publish_snapshots(bot_id=str(definition["id"]), limit=6)
        latest_backtest = self._latest_backtest(str(definition["id"]))
        public_since = publish_history[-1]["created_at"] if publish_history else None
        last_published_at = publish_history[0]["created_at"] if publish_history else None
        release_count = len(publish_history)
        current_version = int(version_history[0]["version_number"]) if version_history else max(1, int(definition.get("rules_version") or 1))
        return {
            "market_scope": definition["market_scope"],
            "strategy_type": definition["strategy_type"],
            "authoring_mode": definition["authoring_mode"],
            "rules_version": int(definition.get("rules_version") or 1),
            "current_version": current_version,
            "release_count": release_count,
            "public_since": public_since,
            "last_published_at": last_published_at,
            "latest_backtest_at": latest_backtest.get("completed_at") if latest_backtest else None,
            "latest_backtest_run_id": latest_backtest.get("id") if latest_backtest else None,
            "version_history": version_history,
            "publish_history": publish_history,
        }

    def _build_trust(
        self,
        *,
        runtime: dict[str, Any],
        latest_snapshot: dict[str, Any] | None,
        health_metrics: dict[str, Any],
        drift: dict[str, Any],
    ) -> dict[str, Any]:
        policy = self.risk_service.normalize_policy(
            runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
        )
        runtime_state = policy.get("_runtime_state") if isinstance(policy.get("_runtime_state"), dict) else {}
        drawdown_pct = self._to_float(runtime_state.get("drawdown_pct"), self._to_float((latest_snapshot or {}).get("drawdown")))
        failure_rate_pct = float(health_metrics["failure_rate_pct"])
        risk_grade, risk_score = self._risk_grade(policy=policy, drawdown_pct=drawdown_pct)
        drift_score = int(drift["score"])
        uptime_score = int(round(float(health_metrics["uptime_pct"])))
        execution_score = max(0, min(100, int(round(100 - min(60.0, failure_rate_pct * 2.2)))))
        trust_score = max(
            0,
            min(
                100,
                round((uptime_score * 0.35) + (execution_score * 0.25) + (drift_score * 0.2) + (risk_score * 0.2)),
            ),
        )
        badges = self._build_badges(
            health=str(health_metrics["health"]),
            failure_rate_pct=failure_rate_pct,
            drift=drift,
            risk_grade=risk_grade,
        )
        return {
            "trust_score": trust_score,
            "uptime_pct": round(float(health_metrics["uptime_pct"]), 2),
            "failure_rate_pct": round(failure_rate_pct, 2),
            "health": health_metrics["health"],
            "heartbeat_age_seconds": health_metrics["heartbeat_age_seconds"],
            "risk_grade": risk_grade,
            "risk_score": risk_score,
            "summary": self._trust_summary(
                trust_score=trust_score,
                health=str(health_metrics["health"]),
                risk_grade=risk_grade,
                drift_status=str(drift["status"]),
            ),
            "badges": badges,
        }

    def _build_drift(
        self,
        *,
        definition: dict[str, Any],
        runtime: dict[str, Any],
        latest_snapshot: dict[str, Any] | None,
    ) -> dict[str, Any]:
        benchmark = self._latest_backtest(str(definition["id"]))
        if benchmark is None:
            return {
                "status": "unverified",
                "score": 48,
                "summary": "No completed backtest is attached to this public strategy yet.",
                "live_pnl_pct": self._live_pnl_pct(runtime=runtime, latest_snapshot=latest_snapshot),
                "benchmark_pnl_pct": None,
                "return_gap_pct": None,
                "live_drawdown_pct": self._live_drawdown_pct(runtime=runtime, latest_snapshot=latest_snapshot),
                "benchmark_drawdown_pct": None,
                "drawdown_gap_pct": None,
                "benchmark_run_id": None,
                "benchmark_completed_at": None,
            }

        live_pnl_pct = self._live_pnl_pct(runtime=runtime, latest_snapshot=latest_snapshot)
        live_drawdown_pct = self._live_drawdown_pct(runtime=runtime, latest_snapshot=latest_snapshot)
        benchmark_pnl_pct = self._to_float(benchmark.get("pnl_total_pct"))
        benchmark_drawdown_pct = self._to_float(benchmark.get("max_drawdown_pct"))
        return_gap_pct = abs(live_pnl_pct - benchmark_pnl_pct)
        drawdown_gap_pct = abs(live_drawdown_pct - benchmark_drawdown_pct)
        score = max(0, min(100, round(100 - (return_gap_pct * 1.8) - (drawdown_gap_pct * 2.3))))
        if score >= 82:
            status = "aligned"
            summary = "Live behavior is tracking close to the latest replay benchmark."
        elif score >= 63:
            status = "watch"
            summary = "Live behavior is still inside a workable band, but it has started to drift from replay expectations."
        else:
            status = "elevated"
            summary = "Live behavior is materially diverging from the latest replay benchmark."
        return {
            "status": status,
            "score": score,
            "summary": summary,
            "live_pnl_pct": round(live_pnl_pct, 4),
            "benchmark_pnl_pct": round(benchmark_pnl_pct, 4),
            "return_gap_pct": round(return_gap_pct, 4),
            "live_drawdown_pct": round(live_drawdown_pct, 4),
            "benchmark_drawdown_pct": round(benchmark_drawdown_pct, 4),
            "drawdown_gap_pct": round(drawdown_gap_pct, 4),
            "benchmark_run_id": benchmark["id"],
            "benchmark_completed_at": benchmark.get("completed_at"),
        }

    def _runtime_health_metrics(self, runtime: dict[str, Any]) -> dict[str, Any]:
        events = self.supabase.select(
            "bot_execution_events",
            columns="id,event_type,status,error_reason,created_at",
            filters={"runtime_id": runtime["id"]},
            order="created_at.desc",
            limit=250,
        )
        latest_event_at = self._as_datetime(events[0]["created_at"]) if events else None
        runtime_updated_at = self._as_datetime(runtime["updated_at"])
        heartbeat_reference = runtime_updated_at if latest_event_at is None or runtime_updated_at > latest_event_at else latest_event_at
        heartbeat_age_seconds = max(0, int((datetime.now(tz=UTC) - heartbeat_reference).total_seconds()))
        action_events = [event for event in events if str(event.get("event_type") or "").startswith("action.")]
        action_error_count = len([event for event in action_events if str(event.get("status") or "") == "error"])
        failure_rate_pct = (action_error_count / len(action_events) * 100.0) if action_events else 0.0
        health = self._health_label(
            runtime_status=str(runtime.get("status") or "draft"),
            heartbeat_age_seconds=heartbeat_age_seconds,
            failure_rate_pct=failure_rate_pct,
        )
        base_uptime = self.HEALTH_UPTIME_MAP.get(health, 56.0)
        penalty = min(14.0, failure_rate_pct * 0.45)
        uptime_pct = max(0.0, min(99.9, base_uptime - penalty))
        return {
            "health": health,
            "heartbeat_age_seconds": heartbeat_age_seconds,
            "latest_event_at": latest_event_at.isoformat() if latest_event_at else None,
            "failure_rate_pct": failure_rate_pct,
            "actions_total": len(action_events),
            "action_error_count": action_error_count,
            "uptime_pct": uptime_pct,
        }

    def _latest_backtest(self, bot_definition_id: str) -> dict[str, Any] | None:
        try:
            return self.supabase.maybe_one(
                "bot_backtest_runs",
                columns="id,pnl_total_pct,max_drawdown_pct,completed_at,status",
                filters={"bot_definition_id": bot_definition_id, "status": "completed"},
                order="completed_at.desc",
            )
        except SupabaseRestError:
            return None

    @staticmethod
    def _health_label(*, runtime_status: str, heartbeat_age_seconds: int, failure_rate_pct: float) -> str:
        if runtime_status in {"stopped", "failed"}:
            return runtime_status
        if runtime_status == "paused":
            return "paused"
        if heartbeat_age_seconds > 600:
            return "offline"
        if heartbeat_age_seconds > 150:
            return "stale"
        if failure_rate_pct >= 35.0:
            return "degraded"
        return "healthy"

    def _risk_grade(self, *, policy: dict[str, Any], drawdown_pct: float) -> tuple[str, int]:
        leverage = self._to_float(policy.get("max_leverage"))
        max_drawdown_pct = self._to_float(policy.get("max_drawdown_pct"))
        allocated_capital = max(1.0, self._to_float(policy.get("allocated_capital_usd"), 1.0))
        max_order_size = self._to_float(policy.get("max_order_size_usd"))
        order_concentration = max_order_size / allocated_capital
        risk_score = 100
        risk_score -= min(30, max(0, leverage - 3) * 6)
        risk_score -= min(24, max(0.0, max_drawdown_pct - 10.0) * 1.2)
        risk_score -= min(18, max(0.0, drawdown_pct - 6.0) * 1.6)
        risk_score -= min(18, max(0.0, order_concentration - 0.25) * 55)
        if risk_score >= 82:
            return "A", int(round(risk_score))
        if risk_score >= 67:
            return "B", int(round(risk_score))
        if risk_score >= 48:
            return "C", int(round(risk_score))
        return "D", int(round(max(0, risk_score)))

    def _build_badges(
        self,
        *,
        health: str,
        failure_rate_pct: float,
        drift: dict[str, Any],
        risk_grade: str,
    ) -> list[dict[str, str]]:
        badges: list[dict[str, str]] = []
        if health == "healthy":
            badges.append({"label": "Live", "tone": "green", "detail": "Heartbeat and execution flow are stable."})
        elif health in {"stale", "degraded"}:
            badges.append({"label": "Watch", "tone": "amber", "detail": "The runtime is showing elevated operational risk."})
        else:
            badges.append({"label": "Risk", "tone": "rose", "detail": "The runtime is not in a stable operating state."})

        if failure_rate_pct <= 8.0:
            badges.append({"label": "Clean fills", "tone": "green", "detail": "Recent execution failures are limited."})
        elif failure_rate_pct <= 20.0:
            badges.append({"label": "Slippage watch", "tone": "amber", "detail": "Execution quality needs monitoring."})
        else:
            badges.append({"label": "Failure heavy", "tone": "rose", "detail": "Recent execution failures are materially elevated."})

        drift_status = str(drift.get("status") or "unverified")
        if drift_status == "aligned":
            badges.append({"label": "Low drift", "tone": "green", "detail": "Live results still resemble replay expectations."})
        elif drift_status == "watch":
            badges.append({"label": "Replay gap", "tone": "amber", "detail": "Live results are drifting away from replay."})
        else:
            badges.append({"label": "Unverified", "tone": "slate" if drift_status == "unverified" else "rose", "detail": drift["summary"]})

        badges.append(
            {
                "label": f"Risk {risk_grade}",
                "tone": "green" if risk_grade == "A" else "amber" if risk_grade == "B" else "rose",
                "detail": "Risk guardrails are derived from leverage, concentration, and drawdown limits.",
            }
        )
        return badges

    @staticmethod
    def _trust_summary(*, trust_score: int, health: str, risk_grade: str, drift_status: str) -> str:
        return (
            f"Trust {trust_score}/100 with {health} runtime health, "
            f"risk grade {risk_grade}, and {drift_status} replay drift."
        )

    @staticmethod
    def _creator_reputation_score(
        *,
        average_trust_score: int,
        active_mirror_count: int,
        mirror_count: int,
        clone_count: int,
        public_bot_count: int,
        best_rank: int | None,
    ) -> int:
        audience_score = min(100, (active_mirror_count * 12) + (mirror_count * 3) + (clone_count * 2))
        catalogue_score = min(100, public_bot_count * 18)
        ranking_bonus = 18 if best_rank == 1 else 12 if best_rank is not None and best_rank <= 3 else 8 if best_rank is not None and best_rank <= 10 else 0
        return max(
            0,
            min(
                100,
                round((average_trust_score * 0.58) + (audience_score * 0.22) + (catalogue_score * 0.14) + ranking_bonus),
            ),
        )

    @staticmethod
    def _reputation_label(score: int) -> str:
        if score >= 85:
            return "Proven"
        if score >= 68:
            return "Trusted"
        if score >= 52:
            return "Emerging"
        return "New"

    @staticmethod
    def _creator_summary(
        *,
        display_name: str,
        public_bot_count: int,
        active_mirror_count: int,
        average_trust_score: int,
    ) -> str:
        return (
            f"{display_name} runs {public_bot_count} public strategies, "
            f"holds {active_mirror_count} active mirrors, and averages {average_trust_score}/100 on trust."
        )

    @staticmethod
    def _creator_tags(
        *,
        reputation_label: str,
        best_rank: int | None,
        active_mirror_count: int,
        public_bot_count: int,
    ) -> list[str]:
        tags = [reputation_label]
        if best_rank is not None and best_rank <= 10:
            tags.append("Top 10")
        if active_mirror_count >= 5:
            tags.append("Actively mirrored")
        if public_bot_count >= 3:
            tags.append("Multi-strategy")
        return tags

    def _live_pnl_pct(self, *, runtime: dict[str, Any], latest_snapshot: dict[str, Any] | None) -> float:
        policy = self.risk_service.normalize_policy(
            runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
        )
        capital = max(1.0, self._to_float(policy.get("allocated_capital_usd"), 1.0))
        snapshot_pnl = self._to_float((latest_snapshot or {}).get("pnl_total"))
        runtime_state = policy.get("_runtime_state") if isinstance(policy.get("_runtime_state"), dict) else {}
        live_pnl = self._to_float(runtime_state.get("pnl_total_usd"), snapshot_pnl)
        return (live_pnl / capital) * 100.0

    def _live_drawdown_pct(self, *, runtime: dict[str, Any], latest_snapshot: dict[str, Any] | None) -> float:
        policy = self.risk_service.normalize_policy(
            runtime.get("risk_policy_json") if isinstance(runtime.get("risk_policy_json"), dict) else {}
        )
        runtime_state = policy.get("_runtime_state") if isinstance(policy.get("_runtime_state"), dict) else {}
        if "drawdown_pct" in runtime_state:
            return self._to_float(runtime_state.get("drawdown_pct"))
        return self._to_float((latest_snapshot or {}).get("drawdown"))

    @staticmethod
    def _as_datetime(value: str | datetime) -> datetime:
        if isinstance(value, datetime):
            return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default
