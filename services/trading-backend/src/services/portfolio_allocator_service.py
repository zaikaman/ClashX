from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.models.portfolio_allocation_member import PortfolioAllocationMemberRecord
from src.models.portfolio_basket import PortfolioBasketRecord
from src.models.portfolio_rebalance_event import PortfolioRebalanceEventRecord
from src.models.portfolio_risk_policy import PortfolioRiskPolicyRecord
from src.services.bot_copy_engine import BotCopyEngine
from src.services.bot_trust_service import BotTrustService
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.portfolio_risk_service import PortfolioRiskService
from src.services.supabase_rest import SupabaseRestClient


class PortfolioAllocatorService:
    def __init__(self) -> None:
        self.supabase = SupabaseRestClient()
        self.copy_engine = BotCopyEngine()
        self.trust_service = BotTrustService()
        self.auth_service = PacificaAuthService()
        self.portfolio_risk_service = PortfolioRiskService()

    def list_portfolios(self, *, wallet_address: str) -> list[dict[str, Any]]:
        baskets = self.supabase.select("portfolio_baskets", filters={"wallet_address": wallet_address}, order="updated_at.desc")
        return self._build_portfolio_payloads(baskets)

    def get_portfolio(self, *, portfolio_id: str, wallet_address: str | None = None) -> dict[str, Any]:
        basket = self._require_basket(portfolio_id=portfolio_id, wallet_address=wallet_address)
        return self._build_portfolio_payload(basket)

    async def create_portfolio(
        self,
        *,
        owner_user_id: str,
        wallet_address: str,
        name: str,
        description: str,
        rebalance_mode: str,
        rebalance_interval_minutes: int,
        drift_threshold_pct: float,
        target_notional_usd: float,
        members: list[dict[str, Any]],
        risk_policy: dict[str, Any] | None,
        activate_on_create: bool,
    ) -> dict[str, Any]:
        basket = self.supabase.insert(
            "portfolio_baskets",
            PortfolioBasketRecord.create(
                owner_user_id=owner_user_id,
                wallet_address=wallet_address,
                name=name,
                description=description,
                status="active" if activate_on_create else "draft",
                rebalance_mode=rebalance_mode,
                rebalance_interval_minutes=rebalance_interval_minutes,
                drift_threshold_pct=drift_threshold_pct,
                target_notional_usd=target_notional_usd,
            ).to_row(),
        )[0]
        self.supabase.insert(
            "portfolio_risk_policies",
            self._build_policy_record(portfolio_basket_id=basket["id"], risk_policy=risk_policy).to_row(),
        )
        member_rows = self._build_member_rows(basket=basket, members=members, existing_members_by_runtime={})
        self.supabase.insert("portfolio_allocation_members", member_rows)
        self._record_rebalance_event(
            portfolio_basket_id=basket["id"],
            trigger="created",
            status="pending" if activate_on_create else "draft",
            summary_json={"member_count": len(member_rows), "target_notional_usd": basket["target_notional_usd"]},
        )
        if activate_on_create:
            return await self.rebalance_portfolio(portfolio_id=basket["id"], wallet_address=wallet_address, trigger="created")
        return self.get_portfolio(portfolio_id=basket["id"], wallet_address=wallet_address)

    async def update_portfolio(self, *, portfolio_id: str, wallet_address: str, payload: dict[str, Any]) -> dict[str, Any]:
        basket = self._require_basket(portfolio_id=portfolio_id, wallet_address=wallet_address)
        updates: dict[str, Any] = {"updated_at": datetime.now(tz=UTC).isoformat()}
        for field in ("name", "description", "status", "rebalance_mode"):
            value = payload.get(field)
            if isinstance(value, str) and value.strip():
                updates[field] = value.strip()
        for field in ("rebalance_interval_minutes", "drift_threshold_pct", "target_notional_usd"):
            if payload.get(field) not in (None, ""):
                updates[field] = payload[field]
        basket = self.supabase.update("portfolio_baskets", updates, filters={"id": basket["id"]})[0]
        if isinstance(payload.get("risk_policy"), dict):
            self._upsert_risk_policy(portfolio_basket_id=basket["id"], risk_policy=payload["risk_policy"])
        if isinstance(payload.get("members"), list):
            existing_members = self.supabase.select("portfolio_allocation_members", filters={"portfolio_basket_id": basket["id"]})
            existing_members_by_runtime = {str(member["source_runtime_id"]): member for member in existing_members}
            next_runtime_ids = {str(member.get("source_runtime_id") or "").strip() for member in payload["members"]}
            retired_members = [
                member for member in existing_members
                if str(member.get("source_runtime_id") or "").strip() not in next_runtime_ids
            ]
            await self._pause_member_relationships(retired_members)
            self.supabase.delete("portfolio_allocation_members", filters={"portfolio_basket_id": basket["id"]})
            self.supabase.insert(
                "portfolio_allocation_members",
                self._build_member_rows(
                    basket=basket,
                    members=payload["members"],
                    existing_members_by_runtime=existing_members_by_runtime,
                ),
            )
        if payload.get("status") == "active":
            return await self.rebalance_portfolio(portfolio_id=basket["id"], wallet_address=wallet_address, trigger="updated")
        return self.get_portfolio(portfolio_id=basket["id"], wallet_address=wallet_address)

    async def rebalance_portfolio(self, *, portfolio_id: str, wallet_address: str | None, trigger: str) -> dict[str, Any]:
        basket = self._require_basket(portfolio_id=portfolio_id, wallet_address=wallet_address)
        self.auth_service.require_active_authorization(None, basket["wallet_address"])
        members = self.supabase.select("portfolio_allocation_members", filters={"portfolio_basket_id": basket["id"]}, order="created_at.asc")
        policy = self.portfolio_risk_service.normalize_policy(
            self.supabase.maybe_one("portfolio_risk_policies", filters={"portfolio_basket_id": basket["id"]}) or {}
        )
        contexts = self._build_member_contexts(basket=basket, members=members)
        now = datetime.now(tz=UTC).isoformat()
        member_updates: list[dict[str, Any]] = []
        for index, context in enumerate(contexts):
            member = context["member"]
            relationship = context.get("relationship")
            desired_status = "active" if index < policy["max_active_members"] and basket["status"] == "active" else "paused"
            relationship_payload = relationship
            if desired_status == "active":
                relationship_payload = await self.copy_engine.activate_mirror(
                    None,
                    runtime_id=str(member["source_runtime_id"]),
                    follower_wallet_address=basket["wallet_address"],
                    follower_display_name=None,
                    scale_bps=int(member["target_scale_bps"]),
                    risk_ack_version="portfolio_v1",
                    portfolio_basket_id=basket["id"],
                    max_notional_usd=float(member["target_notional_usd"]),
                )
            elif isinstance(relationship, dict):
                relationship_payload = await self.copy_engine.update_relationship(
                    None,
                    relationship_id=str(relationship["id"]),
                    scale_bps=int(member["target_scale_bps"]),
                    status="paused",
                )
            self.supabase.update(
                "portfolio_allocation_members",
                {
                    "relationship_id": relationship_payload["id"] if isinstance(relationship_payload, dict) else member.get("relationship_id"),
                    "status": desired_status,
                    "latest_scale_bps": int(member["target_scale_bps"]),
                    "last_rebalanced_at": now,
                    "updated_at": now,
                },
                filters={"id": member["id"]},
            )
            member_updates.append(
                {
                    "source_runtime_id": member["source_runtime_id"],
                    "target_scale_bps": member["target_scale_bps"],
                    "status": desired_status,
                }
            )
        self.supabase.update(
            "portfolio_baskets",
            {
                "status": "active",
                "current_notional_usd": basket["target_notional_usd"],
                "kill_switch_reason": None,
                "last_rebalanced_at": now,
                "updated_at": now,
            },
            filters={"id": basket["id"]},
        )
        self._record_rebalance_event(
            portfolio_basket_id=basket["id"],
            trigger=trigger,
            status="completed",
            summary_json={"member_updates": member_updates, "target_notional_usd": basket["target_notional_usd"]},
        )
        await broadcaster.publish(
            channel=f"user:{basket['owner_user_id']}",
            event="portfolio.rebalanced",
            payload={"portfolio_id": basket["id"], "trigger": trigger},
        )
        return self.get_portfolio(portfolio_id=basket["id"], wallet_address=basket["wallet_address"])

    async def set_kill_switch(
        self,
        *,
        portfolio_id: str,
        wallet_address: str | None,
        engaged: bool,
        reason: str | None,
        trigger: str,
    ) -> dict[str, Any]:
        basket = self._require_basket(portfolio_id=portfolio_id, wallet_address=wallet_address)
        members = self.supabase.select("portfolio_allocation_members", filters={"portfolio_basket_id": basket["id"]})
        now = datetime.now(tz=UTC).isoformat()
        if engaged:
            await self._pause_member_relationships(members)
            for member in members:
                self.supabase.update("portfolio_allocation_members", {"status": "paused", "updated_at": now}, filters={"id": member["id"]})
            self.supabase.update(
                "portfolio_baskets",
                {"status": "killed", "kill_switch_reason": (reason or "Portfolio risk policy breach").strip(), "updated_at": now},
                filters={"id": basket["id"]},
            )
        else:
            self.supabase.update(
                "portfolio_baskets",
                {"status": "active", "kill_switch_reason": None, "updated_at": now},
                filters={"id": basket["id"]},
            )
            return await self.rebalance_portfolio(portfolio_id=basket["id"], wallet_address=basket["wallet_address"], trigger="kill_switch_release")
        self._record_rebalance_event(
            portfolio_basket_id=basket["id"],
            trigger=trigger,
            status="killed" if engaged else "resumed",
            summary_json={"reason": (reason or "").strip()},
        )
        await broadcaster.publish(
            channel=f"user:{basket['owner_user_id']}",
            event="portfolio.kill_switch",
            payload={"portfolio_id": basket["id"], "engaged": engaged, "reason": reason},
        )
        return self.get_portfolio(portfolio_id=basket["id"], wallet_address=basket["wallet_address"])

    def refresh_portfolio_metrics(self, *, portfolio_id: str) -> dict[str, Any]:
        detail = self.get_portfolio(portfolio_id=portfolio_id)
        self.supabase.update(
            "portfolio_baskets",
            {"current_notional_usd": detail["health"]["current_total_notional_usd"], "updated_at": datetime.now(tz=UTC).isoformat()},
            filters={"id": portfolio_id},
        )
        return detail

    def _build_portfolio_payload(self, basket: dict[str, Any]) -> dict[str, Any]:
        return self._build_portfolio_payloads([basket])[0]

    def _build_portfolio_payloads(self, baskets: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not baskets:
            return []
        basket_ids = [str(basket["id"]) for basket in baskets]
        policies = self.supabase.select("portfolio_risk_policies", filters={"portfolio_basket_id": ("in", basket_ids)})
        policies_by_basket = {str(policy["portfolio_basket_id"]): policy for policy in policies}
        members = self.supabase.select(
            "portfolio_allocation_members",
            filters={"portfolio_basket_id": ("in", basket_ids)},
            order="created_at.asc",
        )
        contexts_by_basket = self._build_member_contexts_by_basket(baskets=baskets, members=members)
        history_rows = self.supabase.select(
            "portfolio_rebalance_events",
            filters={"portfolio_basket_id": ("in", basket_ids)},
            order="created_at.desc",
        )
        history_by_basket: dict[str, list[dict[str, Any]]] = {}
        for event in history_rows:
            basket_id = str(event["portfolio_basket_id"])
            if len(history_by_basket.setdefault(basket_id, [])) < 8:
                history_by_basket[basket_id].append(event)
        payloads: list[dict[str, Any]] = []
        for basket in baskets:
            basket_id = str(basket["id"])
            policy = policies_by_basket.get(basket_id) or {}
            contexts = contexts_by_basket.get(basket_id, [])
            health = self.portfolio_risk_service.evaluate_portfolio(
                basket=basket,
                risk_policy=policy,
                member_contexts=contexts,
            )
            payloads.append(
                {
                    "id": basket["id"],
                    "owner_user_id": basket["owner_user_id"],
                    "wallet_address": basket["wallet_address"],
                    "name": basket["name"],
                    "description": basket.get("description") or "",
                    "status": basket["status"],
                    "rebalance_mode": basket["rebalance_mode"],
                    "rebalance_interval_minutes": int(basket.get("rebalance_interval_minutes") or 60),
                    "drift_threshold_pct": float(basket.get("drift_threshold_pct") or 6.0),
                    "target_notional_usd": float(basket.get("target_notional_usd") or 0.0),
                    "current_notional_usd": float(basket.get("current_notional_usd") or 0.0),
                    "kill_switch_reason": basket.get("kill_switch_reason"),
                    "last_rebalanced_at": basket.get("last_rebalanced_at"),
                    "created_at": basket["created_at"],
                    "updated_at": basket["updated_at"],
                    "risk_policy": self.portfolio_risk_service.normalize_policy(policy),
                    "members": [self._serialize_member_context(context) for context in contexts],
                    "health": health,
                    "rebalance_history": history_by_basket.get(basket_id, []),
                }
            )
        return payloads

    def _serialize_member_context(self, context: dict[str, Any]) -> dict[str, Any]:
        member = context["member"]
        relationship = context.get("relationship")
        return {
            "id": member["id"],
            "source_runtime_id": member["source_runtime_id"],
            "source_bot_definition_id": context["definition"]["id"] if isinstance(context.get("definition"), dict) else "",
            "source_bot_name": context.get("bot_name") or "Unknown",
            "target_weight_pct": float(member.get("target_weight_pct") or 0.0),
            "target_notional_usd": float(member.get("target_notional_usd") or 0.0),
            "max_scale_bps": int(member.get("max_scale_bps") or 0),
            "target_scale_bps": int(member.get("target_scale_bps") or 0),
            "latest_scale_bps": int(member.get("latest_scale_bps") or member.get("target_scale_bps") or 0),
            "status": member["status"],
            "relationship_id": relationship.get("id") if isinstance(relationship, dict) else member.get("relationship_id"),
            "relationship_status": relationship.get("status") if isinstance(relationship, dict) else None,
            "trust_score": int(context.get("trust_score") or 0),
            "risk_grade": context.get("risk_grade") or "N/A",
            "drift_status": context.get("drift_status") or "unverified",
            "member_live_pnl_pct": float(context.get("member_live_pnl_pct") or 0.0),
            "member_drawdown_pct": float(context.get("member_drawdown_pct") or 0.0),
            "scale_drift_pct": float(context.get("scale_drift_pct") or 0.0),
            "last_rebalanced_at": member.get("last_rebalanced_at"),
        }

    def _build_member_contexts(self, *, basket: dict[str, Any], members: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return self._build_member_contexts_by_basket(baskets=[basket], members=members).get(str(basket["id"]), [])

    def _build_member_contexts_by_basket(
        self,
        *,
        baskets: list[dict[str, Any]],
        members: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        if not members:
            return {str(basket["id"]): [] for basket in baskets}
        baskets_by_id = {str(basket["id"]): basket for basket in baskets}
        runtime_ids = list({str(member["source_runtime_id"]) for member in members})
        runtimes = (
            {row["id"]: row for row in self.supabase.select("bot_runtimes", filters={"id": ("in", runtime_ids)})}
            if runtime_ids
            else {}
        )
        definition_ids = list({str(runtime["bot_definition_id"]) for runtime in runtimes.values()})
        definitions = (
            {row["id"]: row for row in self.supabase.select("bot_definitions", filters={"id": ("in", definition_ids)})}
            if definition_ids
            else {}
        )
        relationship_ids = [str(member["relationship_id"]) for member in members if member.get("relationship_id")]
        relationships = (
            {row["id"]: row for row in self.supabase.select("bot_copy_relationships", filters={"id": ("in", relationship_ids)})}
            if relationship_ids
            else {}
        )
        snapshots = {row["runtime_id"]: row for row in self._load_latest_snapshots(runtime_ids)}
        contexts_by_basket: dict[str, list[dict[str, Any]]] = {str(basket["id"]): [] for basket in baskets}
        for member in members:
            basket = baskets_by_id.get(str(member["portfolio_basket_id"]))
            if basket is None:
                continue
            runtime = runtimes.get(member["source_runtime_id"])
            definition = definitions.get(runtime["bot_definition_id"]) if isinstance(runtime, dict) else None
            latest_snapshot = snapshots.get(member["source_runtime_id"])
            public_context = (
                self.trust_service.build_runtime_overview(
                    runtime=runtime,
                    definition=definition,
                    latest_snapshot=latest_snapshot,
                )
                if isinstance(runtime, dict) and isinstance(definition, dict)
                else {"trust": {}, "drift": {}}
            )
            member_snapshot = (
                self.portfolio_risk_service.build_member_snapshot(member=member, runtime=runtime, latest_snapshot=latest_snapshot)
                if isinstance(runtime, dict)
                else {"member_live_pnl_pct": 0.0, "member_drawdown_pct": 0.0, "scale_drift_pct": 0.0}
            )
            contexts_by_basket[str(basket["id"])].append(
                {
                    "basket": basket,
                    "member": member,
                    "runtime": runtime or {},
                    "definition": definition or {},
                    "relationship": relationships.get(member.get("relationship_id")) if member.get("relationship_id") else None,
                    "bot_name": definition.get("name") if isinstance(definition, dict) else "Unknown",
                    "trust_score": ((public_context.get("trust") or {}).get("trust_score")) if isinstance(public_context.get("trust"), dict) else 0,
                    "trust_health": ((public_context.get("trust") or {}).get("health")) if isinstance(public_context.get("trust"), dict) else None,
                    "risk_grade": ((public_context.get("trust") or {}).get("risk_grade")) if isinstance(public_context.get("trust"), dict) else None,
                    "drift_status": ((public_context.get("drift") or {}).get("status")) if isinstance(public_context.get("drift"), dict) else None,
                    **member_snapshot,
                }
            )
        return contexts_by_basket

    def _build_member_rows(
        self,
        *,
        basket: dict[str, Any],
        members: list[dict[str, Any]],
        existing_members_by_runtime: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        normalized_specs = self._normalize_member_specs(members)
        runtime_map = self._load_runtime_map([spec["source_runtime_id"] for spec in normalized_specs])
        rows: list[dict[str, Any]] = []
        for spec in normalized_specs:
            runtime = runtime_map.get(spec["source_runtime_id"])
            if runtime is None:
                raise ValueError("Source runtime not found")
            definition = self.supabase.maybe_one("bot_definitions", filters={"id": runtime["bot_definition_id"]})
            if definition is None or definition["visibility"] not in {"public", "unlisted"}:
                raise ValueError("Portfolio members must reference public or unlisted bots")
            target_notional = round(float(basket["target_notional_usd"]) * (float(spec["target_weight_pct"]) / 100.0), 4)
            target_scale_bps = self.portfolio_risk_service.resolve_target_scale_bps(
                target_notional_usd=target_notional,
                source_runtime=runtime,
                max_scale_bps=int(spec["max_scale_bps"]),
            )
            existing = existing_members_by_runtime.get(spec["source_runtime_id"], {})
            row = PortfolioAllocationMemberRecord.create(
                portfolio_basket_id=str(basket["id"]),
                source_runtime_id=spec["source_runtime_id"],
                target_weight_pct=float(spec["target_weight_pct"]),
                target_notional_usd=target_notional,
                max_scale_bps=int(spec["max_scale_bps"]),
                target_scale_bps=target_scale_bps,
            ).to_row()
            if existing:
                row["id"] = existing["id"]
                row["relationship_id"] = existing.get("relationship_id")
                row["latest_scale_bps"] = existing.get("latest_scale_bps")
                row["last_rebalanced_at"] = existing.get("last_rebalanced_at")
            rows.append(row)
        return rows

    def _normalize_member_specs(self, members: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not members:
            raise ValueError("Portfolio basket requires at least one member")
        specs: list[dict[str, Any]] = []
        seen_runtime_ids: set[str] = set()
        total_weight = 0.0
        for member in members:
            runtime_id = str(member.get("source_runtime_id") or "").strip()
            if not runtime_id or runtime_id in seen_runtime_ids:
                continue
            seen_runtime_ids.add(runtime_id)
            weight = max(0.1, float(member.get("target_weight_pct") or 0.0))
            max_scale_bps = max(500, int(float(member.get("max_scale_bps") or 20_000)))
            specs.append({"source_runtime_id": runtime_id, "target_weight_pct": weight, "max_scale_bps": max_scale_bps})
            total_weight += weight
        if not specs or total_weight <= 0:
            raise ValueError("Portfolio basket requires valid member weights")
        for spec in specs:
            spec["target_weight_pct"] = round((float(spec["target_weight_pct"]) / total_weight) * 100.0, 4)
        return specs

    def _build_policy_record(self, *, portfolio_basket_id: str, risk_policy: dict[str, Any] | None) -> PortfolioRiskPolicyRecord:
        normalized = self.portfolio_risk_service.normalize_policy(risk_policy)
        return PortfolioRiskPolicyRecord.create(
            portfolio_basket_id=portfolio_basket_id,
            max_drawdown_pct=float(normalized["max_drawdown_pct"]),
            max_member_drawdown_pct=float(normalized["max_member_drawdown_pct"]),
            min_trust_score=int(normalized["min_trust_score"]),
            max_active_members=int(normalized["max_active_members"]),
            auto_pause_on_source_stale=bool(normalized["auto_pause_on_source_stale"]),
            kill_switch_on_breach=bool(normalized["kill_switch_on_breach"]),
        )

    def _upsert_risk_policy(self, *, portfolio_basket_id: str, risk_policy: dict[str, Any]) -> None:
        current = self.supabase.maybe_one("portfolio_risk_policies", filters={"portfolio_basket_id": portfolio_basket_id})
        normalized = self.portfolio_risk_service.normalize_policy({**(current or {}), **risk_policy})
        values = {**normalized, "updated_at": datetime.now(tz=UTC).isoformat()}
        if current is None:
            self.supabase.insert("portfolio_risk_policies", self._build_policy_record(portfolio_basket_id=portfolio_basket_id, risk_policy=normalized).to_row())
        else:
            self.supabase.update("portfolio_risk_policies", values, filters={"portfolio_basket_id": portfolio_basket_id})

    async def _pause_member_relationships(self, members: list[dict[str, Any]]) -> None:
        for member in members:
            relationship_id = member.get("relationship_id")
            if not relationship_id:
                continue
            await self.copy_engine.update_relationship(
                None,
                relationship_id=str(relationship_id),
                scale_bps=int(member.get("target_scale_bps") or member.get("latest_scale_bps") or 10_000),
                status="paused",
            )

    def _require_basket(self, *, portfolio_id: str, wallet_address: str | None) -> dict[str, Any]:
        basket = self.supabase.maybe_one("portfolio_baskets", filters={"id": portfolio_id})
        if basket is None or (wallet_address is not None and basket["wallet_address"] != wallet_address):
            raise ValueError("Portfolio basket not found")
        return basket

    def _load_runtime_map(self, runtime_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not runtime_ids:
            return {}
        rows = self.supabase.select("bot_runtimes", filters={"id": ("in", runtime_ids)})
        return {row["id"]: row for row in rows}

    def _load_latest_snapshots(self, runtime_ids: list[str]) -> list[dict[str, Any]]:
        if not runtime_ids:
            return []
        rows = self.supabase.select(
            "bot_leaderboard_snapshots",
            columns="runtime_id,rank,pnl_total,pnl_unrealized,win_streak,drawdown,captured_at",
            filters={"runtime_id": ("in", runtime_ids)},
            order="captured_at.desc",
        )
        snapshots_by_runtime: dict[str, dict[str, Any]] = {}
        for row in rows:
            runtime_id = str(row["runtime_id"])
            if runtime_id not in snapshots_by_runtime:
                snapshots_by_runtime[runtime_id] = row
        return list(snapshots_by_runtime.values())

    def _record_rebalance_event(self, *, portfolio_basket_id: str, trigger: str, status: str, summary_json: dict[str, Any]) -> None:
        self.supabase.insert(
            "portfolio_rebalance_events",
            PortfolioRebalanceEventRecord.create(
                portfolio_basket_id=portfolio_basket_id,
                trigger=trigger,
                status=status,
                summary_json=summary_json,
            ).to_row(),
        )
