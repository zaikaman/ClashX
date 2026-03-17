from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from src.core.settings import get_settings
from src.models.audit_event import AuditEvent
from src.models.bot_clone import BotClone
from src.models.bot_copy_relationship import BotCopyRelationship
from src.models.bot_definition import BotDefinition
from src.models.bot_execution_event import BotExecutionEvent
from src.models.bot_leaderboard_snapshot import BotLeaderboardSnapshot
from src.models.bot_runtime import BotRuntime
from src.models.user import User
from src.services.bot_builder_service import BotBuilderService
from src.services.bot_leaderboard_engine import BotLeaderboardEngine
from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClient
from src.services.supabase_rest import SupabaseRestClient


class BotCopyEngine:
    def __init__(
        self,
        *,
        leaderboard_engine: BotLeaderboardEngine | None = None,
        pacifica_client: PacificaClient | None = None,
    ) -> None:
        self.settings = get_settings()
        self.supabase = SupabaseRestClient() if self.settings.use_supabase_api else None
        self.leaderboard_engine = leaderboard_engine or BotLeaderboardEngine(pacifica_client=pacifica_client)
        self.pacifica_client = pacifica_client or PacificaClient()
        self.auth_service = PacificaAuthService()
        self.builder_service = BotBuilderService()

    async def get_or_refresh_leaderboard(self, db: Session, *, limit: int) -> list[dict]:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            latest = self.supabase.maybe_one("bot_leaderboard_snapshots", order="captured_at.desc")
            if latest is None:
                return await self.leaderboard_engine.refresh_public_leaderboard(db, limit=limit)

            snapshots = self.supabase.select(
                "bot_leaderboard_snapshots",
                filters={"captured_at": latest["captured_at"]},
                order="rank.asc",
                limit=limit,
            )
            runtime_ids = [row["runtime_id"] for row in snapshots]
            runtimes = {
                row["id"]: row
                for row in self.supabase.select("bot_runtimes", filters={"id": ("in", runtime_ids)})
            } if runtime_ids else {}
            definition_ids = [runtime["bot_definition_id"] for runtime in runtimes.values()]
            definitions = {
                row["id"]: row
                for row in self.supabase.select("bot_definitions", filters={"id": ("in", definition_ids)})
            } if definition_ids else {}

            rows: list[dict] = []
            for snapshot in snapshots:
                runtime = runtimes.get(snapshot["runtime_id"])
                if runtime is None:
                    continue
                definition = definitions.get(runtime["bot_definition_id"])
                if definition is None or definition["visibility"] != "public":
                    continue
                rows.append(
                    {
                        "runtime_id": runtime["id"],
                        "bot_definition_id": definition["id"],
                        "bot_name": definition["name"],
                        "strategy_type": definition["strategy_type"],
                        "authoring_mode": definition["authoring_mode"],
                        "rank": snapshot["rank"],
                        "pnl_total": snapshot["pnl_total"],
                        "pnl_unrealized": snapshot["pnl_unrealized"],
                        "win_streak": snapshot["win_streak"],
                        "drawdown": snapshot["drawdown"],
                        "captured_at": snapshot["captured_at"],
                    }
                )
            return rows

        latest = db.scalar(
            select(BotLeaderboardSnapshot.captured_at)
            .order_by(desc(BotLeaderboardSnapshot.captured_at))
            .limit(1)
        )
        if latest is None:
            return await self.leaderboard_engine.refresh_public_leaderboard(db, limit=limit)

        snapshots = list(
            db.scalars(
                select(BotLeaderboardSnapshot)
                .where(BotLeaderboardSnapshot.captured_at == latest)
                .order_by(BotLeaderboardSnapshot.rank)
                .limit(limit)
            ).all()
        )
        rows: list[dict] = []
        for snapshot in snapshots:
            runtime = db.get(BotRuntime, snapshot.runtime_id)
            if runtime is None:
                continue
            definition = db.get(BotDefinition, runtime.bot_definition_id)
            if definition is None or definition.visibility != "public":
                continue
            rows.append(
                {
                    "runtime_id": runtime.id,
                    "bot_definition_id": definition.id,
                    "bot_name": definition.name,
                    "strategy_type": definition.strategy_type,
                    "authoring_mode": definition.authoring_mode,
                    "rank": snapshot.rank,
                    "pnl_total": snapshot.pnl_total,
                    "pnl_unrealized": snapshot.pnl_unrealized,
                    "win_streak": snapshot.win_streak,
                    "drawdown": snapshot.drawdown,
                    "captured_at": snapshot.captured_at,
                }
            )
        return rows

    def runtime_profile(self, db: Session, *, runtime_id: str) -> dict:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            runtime = self.supabase.maybe_one("bot_runtimes", filters={"id": runtime_id})
            if runtime is None:
                raise ValueError("Runtime not found")
            definition = self.supabase.maybe_one("bot_definitions", filters={"id": runtime["bot_definition_id"]})
            if definition is None:
                raise ValueError("Bot definition not found")
            latest_snapshot = self.supabase.maybe_one(
                "bot_leaderboard_snapshots",
                filters={"runtime_id": runtime_id},
                order="captured_at.desc",
            )
            recent_events = self.supabase.select(
                "bot_execution_events",
                filters={"runtime_id": runtime_id},
                order="created_at.desc",
                limit=12,
            )
            return {
                "runtime_id": runtime["id"],
                "bot_definition_id": definition["id"],
                "bot_name": definition["name"],
                "description": definition["description"],
                "strategy_type": definition["strategy_type"],
                "authoring_mode": definition["authoring_mode"],
                "status": runtime["status"],
                "mode": runtime["mode"],
                "risk_policy_json": runtime["risk_policy_json"],
                "rank": latest_snapshot["rank"] if latest_snapshot else None,
                "pnl_total": latest_snapshot["pnl_total"] if latest_snapshot else 0.0,
                "pnl_unrealized": latest_snapshot["pnl_unrealized"] if latest_snapshot else 0.0,
                "win_streak": latest_snapshot["win_streak"] if latest_snapshot else 0,
                "drawdown": latest_snapshot["drawdown"] if latest_snapshot else 0.0,
                "recent_events": [
                    {
                        "id": event["id"],
                        "event_type": event["event_type"],
                        "decision_summary": event["decision_summary"],
                        "status": event["status"],
                        "created_at": event["created_at"],
                    }
                    for event in recent_events
                ],
            }

        runtime = db.get(BotRuntime, runtime_id)
        if runtime is None:
            raise ValueError("Runtime not found")
        definition = db.get(BotDefinition, runtime.bot_definition_id)
        if definition is None:
            raise ValueError("Bot definition not found")

        latest_snapshot = db.scalar(
            select(BotLeaderboardSnapshot)
            .where(BotLeaderboardSnapshot.runtime_id == runtime_id)
            .order_by(desc(BotLeaderboardSnapshot.captured_at))
            .limit(1)
        )
        recent_events = list(
            db.scalars(
                select(BotExecutionEvent)
                .where(BotExecutionEvent.runtime_id == runtime_id)
                .order_by(desc(BotExecutionEvent.created_at))
                .limit(12)
            ).all()
        )
        return {
            "runtime_id": runtime.id,
            "bot_definition_id": definition.id,
            "bot_name": definition.name,
            "description": definition.description,
            "strategy_type": definition.strategy_type,
            "authoring_mode": definition.authoring_mode,
            "status": runtime.status,
            "mode": runtime.mode,
            "risk_policy_json": runtime.risk_policy_json,
            "rank": latest_snapshot.rank if latest_snapshot else None,
            "pnl_total": latest_snapshot.pnl_total if latest_snapshot else 0.0,
            "pnl_unrealized": latest_snapshot.pnl_unrealized if latest_snapshot else 0.0,
            "win_streak": latest_snapshot.win_streak if latest_snapshot else 0,
            "drawdown": latest_snapshot.drawdown if latest_snapshot else 0.0,
            "recent_events": [
                {
                    "id": event.id,
                    "event_type": event.event_type,
                    "decision_summary": event.decision_summary,
                    "status": event.status,
                    "created_at": event.created_at,
                }
                for event in recent_events
            ],
        }

    async def preview_mirror(self, db: Session, *, runtime_id: str, follower_wallet_address: str, scale_bps: int) -> dict:
        self._validate_scale_bps(scale_bps)
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            runtime = self.supabase.maybe_one("bot_runtimes", filters={"id": runtime_id})
            if runtime is None:
                raise ValueError("Source runtime not found")
            source_definition = self.supabase.maybe_one("bot_definitions", filters={"id": runtime["bot_definition_id"]})
            if source_definition is None or source_definition["visibility"] != "public":
                raise ValueError("Source bot is not available for mirroring")
            if runtime["wallet_address"] == follower_wallet_address:
                raise ValueError("You cannot mirror your own runtime")

            positions = await self.pacifica_client.get_positions(runtime["wallet_address"])
            mirrored_positions: list[dict] = []
            total_notional = 0.0
            for position in positions:
                mirrored_size = round(float(position.get("amount", 0) or 0) * (scale_bps / 10_000), 4)
                mark_price = float(position.get("mark_price", 0) or 0)
                notional = round(mirrored_size * mark_price, 2)
                total_notional += notional
                mirrored_positions.append(
                    {
                        "symbol": str(position.get("symbol") or ""),
                        "side": str(position.get("side") or ""),
                        "size_source": float(position.get("amount", 0) or 0),
                        "size_mirrored": mirrored_size,
                        "mark_price": mark_price,
                        "notional_estimate": notional,
                    }
                )

            return {
                "source_runtime_id": runtime["id"],
                "source_bot_definition_id": source_definition["id"],
                "source_bot_name": source_definition["name"],
                "source_wallet_address": runtime["wallet_address"],
                "follower_wallet_address": follower_wallet_address,
                "mode": "mirror",
                "scale_bps": scale_bps,
                "warnings": self._build_mirror_warnings(total_notional=total_notional, position_count=len(mirrored_positions)),
                "mirrored_positions": mirrored_positions,
            }

        runtime = db.get(BotRuntime, runtime_id)
        if runtime is None:
            raise ValueError("Source runtime not found")

        source_definition = db.get(BotDefinition, runtime.bot_definition_id)
        if source_definition is None or source_definition.visibility != "public":
            raise ValueError("Source bot is not available for mirroring")
        if runtime.wallet_address == follower_wallet_address:
            raise ValueError("You cannot mirror your own runtime")

        positions = await self.pacifica_client.get_positions(runtime.wallet_address)
        mirrored_positions: list[dict] = []
        total_notional = 0.0
        for position in positions:
            mirrored_size = round(float(position.get("amount", 0) or 0) * (scale_bps / 10_000), 4)
            mark_price = float(position.get("mark_price", 0) or 0)
            notional = round(mirrored_size * mark_price, 2)
            total_notional += notional
            mirrored_positions.append(
                {
                    "symbol": str(position.get("symbol") or ""),
                    "side": str(position.get("side") or ""),
                    "size_source": float(position.get("amount", 0) or 0),
                    "size_mirrored": mirrored_size,
                    "mark_price": mark_price,
                    "notional_estimate": notional,
                }
            )

        return {
            "source_runtime_id": runtime.id,
            "source_bot_definition_id": source_definition.id,
            "source_bot_name": source_definition.name,
            "source_wallet_address": runtime.wallet_address,
            "follower_wallet_address": follower_wallet_address,
            "mode": "mirror",
            "scale_bps": scale_bps,
            "warnings": self._build_mirror_warnings(total_notional=total_notional, position_count=len(mirrored_positions)),
            "mirrored_positions": mirrored_positions,
        }

    async def activate_mirror(
        self,
        db: Session,
        *,
        runtime_id: str,
        follower_wallet_address: str,
        follower_display_name: str | None,
        scale_bps: int,
        risk_ack_version: str,
    ) -> dict:
        self.auth_service.require_active_authorization(db, follower_wallet_address)
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            preview = await self.preview_mirror(
                db,
                runtime_id=runtime_id,
                follower_wallet_address=follower_wallet_address,
                scale_bps=scale_bps,
            )
            follower = self._find_or_create_follower(db, wallet_address=follower_wallet_address, display_name=follower_display_name)
            active = self.supabase.select(
                "bot_copy_relationships",
                filters={"follower_user_id": follower["id"], "status": "active"},
            )
            now = datetime.now(tz=UTC).isoformat()
            for relationship in active:
                if relationship["source_runtime_id"] != runtime_id:
                    self.supabase.update(
                        "bot_copy_relationships",
                        {"status": "stopped", "updated_at": now},
                        filters={"id": relationship["id"]},
                    )

            relationship = self.supabase.maybe_one(
                "bot_copy_relationships",
                filters={"follower_user_id": follower["id"], "source_runtime_id": runtime_id},
            )
            if relationship is None:
                relationship = self.supabase.insert(
                    "bot_copy_relationships",
                    {
                        "id": str(uuid.uuid4()),
                        "source_runtime_id": runtime_id,
                        "follower_user_id": follower["id"],
                        "follower_wallet_address": follower_wallet_address,
                        "mode": "mirror",
                        "scale_bps": scale_bps,
                        "status": "active",
                        "risk_ack_version": risk_ack_version,
                        "confirmed_at": now,
                        "updated_at": now,
                    },
                )[0]
            else:
                relationship = self.supabase.update(
                    "bot_copy_relationships",
                    {
                        "mode": "mirror",
                        "scale_bps": scale_bps,
                        "status": "active",
                        "risk_ack_version": risk_ack_version,
                        "confirmed_at": now,
                        "updated_at": now,
                    },
                    filters={"id": relationship["id"]},
                )[0]

            self.supabase.insert(
                "audit_events",
                {
                    "id": str(uuid.uuid4()),
                    "user_id": follower["id"],
                    "action": "bot_copy.mirror.activated",
                    "payload": {
                        "relationship_id": relationship["id"],
                        "source_runtime_id": runtime_id,
                        "scale_bps": scale_bps,
                    },
                    "created_at": now,
                },
            )
            await broadcaster.publish(
                channel=f"user:{follower['id']}",
                event="bot.copy.updated",
                payload={
                    "relationship_id": relationship["id"],
                    "status": relationship["status"],
                    "source_runtime_id": relationship["source_runtime_id"],
                    "scale_bps": relationship["scale_bps"],
                    "preview": preview,
                },
            )
            return self.serialize_relationship(db, relationship)

        preview = await self.preview_mirror(
            db,
            runtime_id=runtime_id,
            follower_wallet_address=follower_wallet_address,
            scale_bps=scale_bps,
        )
        follower = self._find_or_create_follower(db, wallet_address=follower_wallet_address, display_name=follower_display_name)

        active = list(
            db.scalars(
                select(BotCopyRelationship)
                .where(BotCopyRelationship.follower_user_id == follower.id, BotCopyRelationship.status == "active")
            ).all()
        )
        for relationship in active:
            if relationship.source_runtime_id != runtime_id:
                relationship.status = "stopped"
                relationship.updated_at = datetime.now(tz=UTC)

        relationship = db.scalar(
            select(BotCopyRelationship).where(
                BotCopyRelationship.follower_user_id == follower.id,
                BotCopyRelationship.source_runtime_id == runtime_id,
            )
        )
        now = datetime.now(tz=UTC)
        if relationship is None:
            relationship = BotCopyRelationship(
                source_runtime_id=runtime_id,
                follower_user_id=follower.id,
                follower_wallet_address=follower_wallet_address,
                mode="mirror",
                scale_bps=scale_bps,
                status="active",
                risk_ack_version=risk_ack_version,
                confirmed_at=now,
                updated_at=now,
            )
            db.add(relationship)
            db.flush()
        else:
            relationship.mode = "mirror"
            relationship.scale_bps = scale_bps
            relationship.status = "active"
            relationship.risk_ack_version = risk_ack_version
            relationship.confirmed_at = now
            relationship.updated_at = now

        db.add(
            AuditEvent(
                user_id=follower.id,
                action="bot_copy.mirror.activated",
                payload={
                    "relationship_id": relationship.id,
                    "source_runtime_id": runtime_id,
                    "scale_bps": scale_bps,
                },
            )
        )
        db.commit()
        db.refresh(relationship)

        await broadcaster.publish(
            channel=f"user:{follower.id}",
            event="bot.copy.updated",
            payload={
                "relationship_id": relationship.id,
                "status": relationship.status,
                "source_runtime_id": relationship.source_runtime_id,
                "scale_bps": relationship.scale_bps,
                "preview": preview,
            },
        )
        return self.serialize_relationship(db, relationship)

    def create_clone(
        self,
        db: Session,
        *,
        runtime_id: str,
        wallet_address: str,
        name: str | None,
        description: str | None,
        visibility: str,
    ) -> dict:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            runtime = self.supabase.maybe_one("bot_runtimes", filters={"id": runtime_id})
            if runtime is None:
                raise ValueError("Source runtime not found")
            source_definition = self.supabase.maybe_one("bot_definitions", filters={"id": runtime["bot_definition_id"]})
            if source_definition is None:
                raise ValueError("Source bot definition not found")
            if source_definition["visibility"] not in {"public", "unlisted"}:
                raise ValueError("Source bot is not cloneable")

            clone_name = (name or f"{source_definition['name']} Clone").strip()
            clone_description = (description or source_definition["description"] or "Cloned bot draft").strip()
            cloned = self.builder_service.create_bot(
                db,
                wallet_address=wallet_address,
                name=clone_name,
                description=clone_description,
                visibility=visibility,
                market_scope=source_definition["market_scope"],
                strategy_type=source_definition["strategy_type"],
                authoring_mode=source_definition["authoring_mode"],
                rules_version=source_definition["rules_version"],
                rules_json=source_definition["rules_json"],
            )
            follower = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
            if follower is None:
                raise ValueError("Follower user not found")
            clone_record = self.supabase.insert(
                "bot_clones",
                {
                    "id": str(uuid.uuid4()),
                    "source_bot_definition_id": source_definition["id"],
                    "new_bot_definition_id": cloned["id"],
                    "created_by_user_id": follower["id"],
                    "created_at": datetime.now(tz=UTC).isoformat(),
                },
            )[0]
            self.supabase.insert(
                "audit_events",
                {
                    "id": str(uuid.uuid4()),
                    "user_id": follower["id"],
                    "action": "bot_copy.clone.created",
                    "payload": {
                        "runtime_id": runtime_id,
                        "source_bot_definition_id": source_definition["id"],
                        "new_bot_definition_id": cloned["id"],
                    },
                    "created_at": datetime.now(tz=UTC).isoformat(),
                },
            )
            return {
                "clone_id": clone_record["id"],
                "source_runtime_id": runtime_id,
                "source_bot_definition_id": source_definition["id"],
                "new_bot_definition_id": cloned["id"],
                "created_by_user_id": follower["id"],
                "created_at": clone_record["created_at"],
            }

        runtime = db.get(BotRuntime, runtime_id)
        if runtime is None:
            raise ValueError("Source runtime not found")
        source_definition = db.get(BotDefinition, runtime.bot_definition_id)
        if source_definition is None:
            raise ValueError("Source bot definition not found")
        if source_definition.visibility not in {"public", "unlisted"}:
            raise ValueError("Source bot is not cloneable")

        clone_name = (name or f"{source_definition.name} Clone").strip()
        clone_description = (description or source_definition.description or "Cloned bot draft").strip()
        cloned = self.builder_service.create_bot(
            db,
            wallet_address=wallet_address,
            name=clone_name,
            description=clone_description,
            visibility=visibility,
            market_scope=source_definition.market_scope,
            strategy_type=source_definition.strategy_type,
            authoring_mode=source_definition.authoring_mode,
            rules_version=source_definition.rules_version,
            rules_json=source_definition.rules_json,
        )

        follower = db.scalar(select(User).where(User.wallet_address == wallet_address).limit(1))
        if follower is None:
            raise ValueError("Follower user not found")

        clone_record = BotClone(
            source_bot_definition_id=source_definition.id,
            new_bot_definition_id=cloned["id"],
            created_by_user_id=follower.id,
        )
        db.add(clone_record)
        db.add(
            AuditEvent(
                user_id=follower.id,
                action="bot_copy.clone.created",
                payload={
                    "runtime_id": runtime_id,
                    "source_bot_definition_id": source_definition.id,
                    "new_bot_definition_id": cloned["id"],
                },
            )
        )
        db.commit()
        db.refresh(clone_record)

        return {
            "clone_id": clone_record.id,
            "source_runtime_id": runtime_id,
            "source_bot_definition_id": source_definition.id,
            "new_bot_definition_id": cloned["id"],
            "created_by_user_id": follower.id,
            "created_at": clone_record.created_at,
        }

    def list_relationships(self, db: Session, *, follower_wallet_address: str) -> list[dict]:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            rows = self.supabase.select(
                "bot_copy_relationships",
                filters={"follower_wallet_address": follower_wallet_address},
                order="updated_at.desc",
            )
            return [self.serialize_relationship(db, row) for row in rows]

        rows = list(
            db.scalars(
                select(BotCopyRelationship)
                .where(BotCopyRelationship.follower_wallet_address == follower_wallet_address)
                .order_by(desc(BotCopyRelationship.updated_at))
            ).all()
        )
        return [self.serialize_relationship(db, row) for row in rows]

    def list_clones(self, db: Session, *, wallet_address: str) -> list[dict]:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            follower = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
            if follower is None:
                return []
            rows = self.supabase.select(
                "bot_clones",
                filters={"created_by_user_id": follower["id"]},
                order="created_at.desc",
            )
            definition_ids = [
                *[row["source_bot_definition_id"] for row in rows],
                *[row["new_bot_definition_id"] for row in rows],
            ]
            definitions = {
                row["id"]: row
                for row in self.supabase.select("bot_definitions", filters={"id": ("in", definition_ids)})
            } if definition_ids else {}
            return [
                {
                    "clone_id": row["id"],
                    "source_bot_definition_id": row["source_bot_definition_id"],
                    "source_bot_name": definitions.get(row["source_bot_definition_id"], {}).get("name", "Unknown"),
                    "new_bot_definition_id": row["new_bot_definition_id"],
                    "new_bot_name": definitions.get(row["new_bot_definition_id"], {}).get("name", "Unknown"),
                    "created_at": row["created_at"],
                }
                for row in rows
            ]

        follower = db.scalar(select(User).where(User.wallet_address == wallet_address).limit(1))
        if follower is None:
            return []

        rows = list(
            db.scalars(
                select(BotClone)
                .where(BotClone.created_by_user_id == follower.id)
                .order_by(desc(BotClone.created_at))
            ).all()
        )
        clones: list[dict] = []
        for row in rows:
            source = db.get(BotDefinition, row.source_bot_definition_id)
            target = db.get(BotDefinition, row.new_bot_definition_id)
            clones.append(
                {
                    "clone_id": row.id,
                    "source_bot_definition_id": row.source_bot_definition_id,
                    "source_bot_name": source.name if source else "Unknown",
                    "new_bot_definition_id": row.new_bot_definition_id,
                    "new_bot_name": target.name if target else "Unknown",
                    "created_at": row.created_at,
                }
            )
        return clones

    async def update_relationship(self, db: Session, *, relationship_id: str, scale_bps: int | None, status: str | None) -> dict:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            relationship = self.supabase.maybe_one("bot_copy_relationships", filters={"id": relationship_id})
            if relationship is None:
                raise ValueError("Bot copy relationship not found")
            values: dict[str, object] = {"updated_at": datetime.now(tz=UTC).isoformat()}
            if scale_bps is not None:
                self._validate_scale_bps(scale_bps)
                values["scale_bps"] = scale_bps
            if status is not None:
                values["status"] = status
            relationship = self.supabase.update("bot_copy_relationships", values, filters={"id": relationship_id})[0]
            self.supabase.insert(
                "audit_events",
                {
                    "id": str(uuid.uuid4()),
                    "user_id": relationship["follower_user_id"],
                    "action": "bot_copy.mirror.updated",
                    "payload": {
                        "relationship_id": relationship["id"],
                        "scale_bps": relationship["scale_bps"],
                        "status": relationship["status"],
                    },
                    "created_at": datetime.now(tz=UTC).isoformat(),
                },
            )
            await broadcaster.publish(
                channel=f"user:{relationship['follower_user_id']}",
                event="bot.copy.updated",
                payload={
                    "relationship_id": relationship["id"],
                    "status": relationship["status"],
                    "scale_bps": relationship["scale_bps"],
                },
            )
            return self.serialize_relationship(db, relationship)

        relationship = db.get(BotCopyRelationship, relationship_id)
        if relationship is None:
            raise ValueError("Bot copy relationship not found")
        if scale_bps is not None:
            self._validate_scale_bps(scale_bps)
            relationship.scale_bps = scale_bps
        if status is not None:
            relationship.status = status
        relationship.updated_at = datetime.now(tz=UTC)
        db.add(
            AuditEvent(
                user_id=relationship.follower_user_id,
                action="bot_copy.mirror.updated",
                payload={
                    "relationship_id": relationship.id,
                    "scale_bps": relationship.scale_bps,
                    "status": relationship.status,
                },
            )
        )
        db.commit()
        await broadcaster.publish(
            channel=f"user:{relationship.follower_user_id}",
            event="bot.copy.updated",
            payload={
                "relationship_id": relationship.id,
                "status": relationship.status,
                "scale_bps": relationship.scale_bps,
            },
        )
        return self.serialize_relationship(db, relationship)

    async def stop_relationship(self, db: Session, *, relationship_id: str) -> dict:
        return await self.update_relationship(db, relationship_id=relationship_id, scale_bps=None, status="stopped")

    def serialize_relationship(self, db: Session, relationship: BotCopyRelationship | dict) -> dict:
        if self.settings.use_supabase_api and isinstance(relationship, dict):
            assert self.supabase is not None
            source_runtime = self.supabase.maybe_one("bot_runtimes", filters={"id": relationship["source_runtime_id"]})
            source_definition = self.supabase.maybe_one("bot_definitions", filters={"id": source_runtime["bot_definition_id"]}) if source_runtime else None
            follower = self.supabase.maybe_one("users", filters={"id": relationship["follower_user_id"]})
            return {
                "id": relationship["id"],
                "source_runtime_id": relationship["source_runtime_id"],
                "source_bot_definition_id": source_definition["id"] if source_definition else "",
                "source_bot_name": source_definition["name"] if source_definition else "Unknown",
                "follower_user_id": relationship["follower_user_id"],
                "follower_wallet_address": relationship["follower_wallet_address"],
                "mode": relationship["mode"],
                "scale_bps": relationship["scale_bps"],
                "status": relationship["status"],
                "risk_ack_version": relationship["risk_ack_version"],
                "confirmed_at": relationship["confirmed_at"],
                "updated_at": relationship["updated_at"],
                "follower_display_name": follower.get("display_name") if follower else None,
            }

        source_runtime = db.get(BotRuntime, relationship.source_runtime_id)
        source_definition = db.get(BotDefinition, source_runtime.bot_definition_id) if source_runtime else None
        follower = db.get(User, relationship.follower_user_id)
        return {
            "id": relationship.id,
            "source_runtime_id": relationship.source_runtime_id,
            "source_bot_definition_id": source_definition.id if source_definition else "",
            "source_bot_name": source_definition.name if source_definition else "Unknown",
            "follower_user_id": relationship.follower_user_id,
            "follower_wallet_address": relationship.follower_wallet_address,
            "mode": relationship.mode,
            "scale_bps": relationship.scale_bps,
            "status": relationship.status,
            "risk_ack_version": relationship.risk_ack_version,
            "confirmed_at": relationship.confirmed_at,
            "updated_at": relationship.updated_at,
            "follower_display_name": follower.display_name if follower else None,
        }

    @staticmethod
    def _validate_scale_bps(scale_bps: int) -> None:
        if scale_bps < 500 or scale_bps > 30_000:
            raise ValueError("scale_bps must be between 500 and 30000")

    @staticmethod
    def _build_mirror_warnings(*, total_notional: float, position_count: int) -> list[str]:
        warnings = [
            "Mirroring executes live orders on your delegated wallet.",
            "Slippage, fees, and liquidations can deviate from source runtime performance.",
        ]
        if total_notional > 0:
            warnings.append(f"Estimated mirrored notional from current positions: ${total_notional:,.2f}.")
        if position_count == 0:
            warnings.append("Source runtime currently has no open positions to mirror.")
        return warnings

    def _find_or_create_follower(self, db: Session, *, wallet_address: str, display_name: str | None) -> User | dict:
        if self.settings.use_supabase_api:
            assert self.supabase is not None
            follower = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
            if follower is None:
                follower = self.supabase.insert(
                    "users",
                    {
                        "id": str(uuid.uuid4()),
                        "wallet_address": wallet_address,
                        "display_name": (display_name or wallet_address[:8]).strip(),
                        "auth_provider": "privy",
                        "created_at": datetime.now(tz=UTC).isoformat(),
                    },
                    upsert=True,
                    on_conflict="wallet_address",
                )[0]
                return follower
            if display_name:
                follower = self.supabase.update(
                    "users",
                    {"display_name": display_name.strip()},
                    filters={"id": follower["id"]},
                )[0]
            return follower

        follower = db.scalar(select(User).where(User.wallet_address == wallet_address).limit(1))
        if follower is None:
            follower = User(
                wallet_address=wallet_address,
                display_name=(display_name or wallet_address[:8]).strip(),
            )
            db.add(follower)
            db.flush()
            return follower
        if display_name:
            follower.display_name = display_name.strip()
        return follower
