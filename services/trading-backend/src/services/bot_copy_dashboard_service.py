from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from src.services.bot_copy_engine import BotCopyEngine
from src.services.creator_marketplace_service import CreatorMarketplaceService
from src.services.pacifica_client import PacificaClientError
from src.services.pacifica_readiness_service import PacificaReadinessService
from src.services.portfolio_allocator_service import PortfolioAllocatorService
from src.services.supabase_rest import SupabaseRestClient
from src.services.trading_service import TradingService


_COPY_OPEN_ACTIONS = {
    "open_long",
    "open_short",
    "place_market_order",
    "place_limit_order",
    "place_twap_order",
}
_COPY_POSITION_ACTIONS = _COPY_OPEN_ACTIONS | {"close_position"}


class BotCopyDashboardService:
    def __init__(self) -> None:
        self.supabase = SupabaseRestClient()
        self.copy_engine = BotCopyEngine()
        self.marketplace_service = CreatorMarketplaceService()
        self.portfolio_service = PortfolioAllocatorService()
        self.trading_service = TradingService()
        self.readiness_service = PacificaReadinessService()

    async def get_dashboard(self, *, wallet_address: str) -> dict[str, Any]:
        relationships = self.copy_engine.list_relationships(None, follower_wallet_address=wallet_address)
        relationship_ids = [str(item["id"]) for item in relationships]
        runtime_ids = [str(item["source_runtime_id"]) for item in relationships]

        runtime_profiles = await self._load_runtime_profiles(runtime_ids)
        activity_rows = self._load_activity_rows(relationship_ids=relationship_ids, wallet_address=wallet_address)
        trading_snapshot = await self.trading_service.get_account_snapshot(None, wallet_address)
        manual_history_rows = await self._load_manual_history_rows(wallet_address=wallet_address)
        copy_state = self._build_copy_state(
            activity_rows=activity_rows,
            manual_history_rows=manual_history_rows,
        )
        readiness = await self.readiness_service.get_readiness(None, wallet_address)
        baskets = self.portfolio_service.list_portfolios(wallet_address=wallet_address)
        discover_rows = await self.marketplace_service.discover_public_bots(limit=6)

        attributed_positions, unattributed_details = self._build_attributed_positions(
            copy_state=copy_state,
            trading_snapshot=trading_snapshot,
        )
        follows = self._build_follows(
            relationships=relationships,
            runtime_profiles=runtime_profiles,
            copy_state=copy_state,
            attributed_positions=attributed_positions,
        )
        alerts = self._build_alerts(
            follows=follows,
            baskets=baskets,
            readiness=readiness,
            unattributed_details=unattributed_details,
            activity_rows=activity_rows,
        )

        return {
            "summary": self._build_summary(
                follows=follows,
                positions=attributed_positions,
                copy_state=copy_state,
                readiness=readiness,
            ),
            "readiness": {
                "can_copy": bool(readiness.get("ready")),
                "authorization_status": (readiness.get("metrics") or {}).get("authorization_status", "inactive"),
                "blockers": list(readiness.get("blockers") or []),
            },
            "alerts": alerts,
            "follows": follows,
            "positions": attributed_positions,
            "activity": [self._serialize_activity_row(row) for row in activity_rows[:18]],
            "discover": [self._serialize_discover_row(row) for row in discover_rows],
            "baskets_summary": [self._serialize_basket_summary(item) for item in baskets],
        }

    async def _load_runtime_profiles(self, runtime_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not runtime_ids:
            return {}
        snapshot_rows = self.supabase.select(
            "marketplace_runtime_snapshots",
            columns="runtime_id,detail_json,row_json",
            filters={"runtime_id": ("in", runtime_ids)},
        )
        profiles: dict[str, dict[str, Any]] = {}
        for row in snapshot_rows:
            runtime_id = str(row.get("runtime_id") or "").strip()
            detail = row.get("detail_json")
            fallback = row.get("row_json")
            if runtime_id and isinstance(detail, dict) and detail:
                profiles[runtime_id] = detail
            elif runtime_id and isinstance(fallback, dict) and fallback:
                profiles[runtime_id] = fallback
        for runtime_id in runtime_ids:
            if runtime_id in profiles:
                continue
            try:
                profiles[runtime_id] = await self.marketplace_service.get_runtime_profile(runtime_id=runtime_id)
            except ValueError:
                continue
        return profiles

    def _load_activity_rows(self, *, relationship_ids: list[str], wallet_address: str) -> list[dict[str, Any]]:
        filters: dict[str, Any] = {"follower_wallet_address": wallet_address}
        if relationship_ids:
            filters["relationship_id"] = ("in", relationship_ids)
        return self.supabase.select(
            "bot_copy_execution_events",
            filters=filters,
            order="created_at.desc",
            limit=80,
        )

    async def _load_manual_history_rows(self, *, wallet_address: str, limit: int = 200) -> list[dict[str, Any]]:
        pacifica = getattr(self.trading_service, "pacifica", None)
        if pacifica is None:
            return []
        try:
            order_history, position_history = await self._load_manual_history_pages(
                pacifica=pacifica,
                wallet_address=wallet_address,
                limit=limit,
            )
        except (AttributeError, TypeError, PacificaClientError):
            return []

        position_groups: dict[tuple[str, Any], dict[str, float]] = defaultdict(
            lambda: {"amount": 0.0, "pnl": 0.0, "price_notional": 0.0}
        )
        for row in position_history:
            symbol = str(row.get("symbol") or "").strip().upper().replace("-PERP", "")
            created_at = row.get("created_at") or row.get("createdAt")
            amount = self._to_float(row.get("amount"))
            price = self._to_float(row.get("price"))
            if not symbol or created_at in (None, "") or amount <= 1e-12:
                continue
            key = (symbol, created_at)
            position_groups[key]["amount"] += amount
            position_groups[key]["pnl"] += self._to_float(row.get("pnl"))
            if price > 0:
                position_groups[key]["price_notional"] += amount * price

        grouped_order_rows: dict[tuple[str, Any, str, str], dict[str, Any]] = {}
        for row in order_history:
            normalized = self._normalize_manual_history_row(row)
            if normalized is None:
                continue
            key = (
                str(normalized["symbol"]),
                normalized["created_at"],
                str(normalized["event_kind"]),
                str(normalized["position_side"]),
            )
            existing = grouped_order_rows.get(key)
            if existing is None:
                grouped_order_rows[key] = dict(normalized)
                grouped_order_rows[key]["_price_notional"] = (
                    self._to_float(normalized.get("amount")) * self._to_float(normalized.get("price"))
                )
                continue
            amount = self._to_float(normalized.get("amount"))
            existing["amount"] = self._to_float(existing.get("amount")) + amount
            existing["_price_notional"] = self._to_float(existing.get("_price_notional")) + (
                amount * self._to_float(normalized.get("price"))
            )

        normalized_rows: list[dict[str, Any]] = []
        for row in grouped_order_rows.values():
            amount = self._to_float(row.get("amount"))
            if amount <= 1e-12:
                continue
            row["price"] = self._to_float(row.get("_price_notional")) / amount
            row.pop("_price_notional", None)
            position_group = position_groups.get((str(row.get("symbol")), row.get("created_at")))
            if position_group is not None and self._to_float(position_group.get("amount")) > 1e-12:
                row["exchange_realized_pnl"] = self._to_float(position_group.get("pnl"))
            normalized_rows.append(row)
        normalized_rows.sort(key=lambda row: self._timestamp_value(row.get("created_at")))
        return normalized_rows

    async def _load_manual_history_pages(
        self,
        *,
        pacifica: Any,
        wallet_address: str,
        limit: int,
        max_pages: int = 10,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        order_rows: list[dict[str, Any]] = []
        position_rows: list[dict[str, Any]] = []
        page_size = max(1, int(limit))
        page_offset = 0

        for _ in range(max_pages):
            batch = await pacifica.get_order_history(wallet_address, limit=page_size, offset=page_offset)
            if not batch:
                break
            order_rows.extend(batch)
            if len(batch) < page_size:
                break
            page_offset += page_size

        page_offset = 0
        for _ in range(max_pages):
            batch = await pacifica.get_position_history(wallet_address, limit=page_size, offset=page_offset)
            if not batch:
                break
            position_rows.extend(batch)
            if len(batch) < page_size:
                break
            page_offset += page_size

        return order_rows, position_rows

    def _build_copy_state(
        self,
        *,
        activity_rows: list[dict[str, Any]],
        manual_history_rows: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ordered_rows = sorted(
            activity_rows,
            key=lambda row: self._timestamp_value(row.get("created_at")),
        )
        open_lots_by_key: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
        recorded_close_markers: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        recorded_open_markers: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        realized_24h = 0.0
        realized_7d = 0.0
        now = datetime.now(tz=UTC)

        for row in ordered_rows:
            if str(row.get("status") or "") != "mirrored":
                continue
            action_type = str(row.get("action_type") or "")
            if action_type not in _COPY_POSITION_ACTIONS:
                continue
            relationship_id = str(row.get("relationship_id") or "").strip()
            symbol = str(row.get("symbol") or "").strip().upper()
            position_side = str(row.get("position_side") or "").strip().lower()
            quantity = self._to_float(row.get("copied_quantity"))
            price = self._to_float(row.get("reference_price"))
            created_at = self._as_datetime(row.get("created_at")) or now
            if not relationship_id or not symbol or position_side not in {"long", "short"} or quantity <= 0:
                continue

            key = (relationship_id, symbol, position_side)
            reduce_only = bool(row.get("reduce_only")) or action_type == "close_position"
            if action_type in _COPY_OPEN_ACTIONS and not reduce_only:
                open_lots_by_key[key].append(
                    {
                        "quantity": quantity,
                        "entry_price": price,
                        "opened_at": created_at,
                        "last_activity_at": created_at,
                    }
                )
                recorded_open_markers[(symbol, position_side)].append(
                    {
                        "relationship_id": relationship_id,
                        "created_at": created_at,
                        "remaining_quantity": quantity,
                    }
                )
                continue

            recorded_close_markers[(symbol, position_side)].append(
                {
                    "created_at": created_at,
                    "remaining_quantity": quantity,
                }
            )
            pnl = self._consume_lots(
                open_lots_by_key=open_lots_by_key,
                relationship_id=relationship_id,
                symbol=symbol,
                position_side=position_side,
                quantity=quantity,
                price=price,
                created_at=created_at,
            )
            if created_at >= now - timedelta(days=1):
                realized_24h += pnl
            if created_at >= now - timedelta(days=7):
                realized_7d += pnl

        for history_row in manual_history_rows or []:
            symbol = str(history_row.get("symbol") or "").strip().upper()
            position_side = str(history_row.get("position_side") or "").strip().lower()
            quantity = self._to_float(history_row.get("amount"))
            price = self._to_float(history_row.get("price"))
            created_at = self._as_datetime(history_row.get("created_at")) or now
            exchange_realized_pnl = self._to_float(history_row.get("exchange_realized_pnl"))
            event_kind = str(history_row.get("event_kind") or "").strip().lower()
            if not symbol or position_side not in {"long", "short"} or quantity <= 0:
                continue
            if event_kind == "open":
                if self._consume_recorded_close_markers(
                    markers=recorded_open_markers[(symbol, position_side)],
                    quantity=quantity,
                    created_at=created_at,
                ):
                    if created_at >= now - timedelta(days=1):
                        realized_24h += exchange_realized_pnl
                    if created_at >= now - timedelta(days=7):
                        realized_7d += exchange_realized_pnl
                continue
            if event_kind != "close" or price <= 0:
                continue
            if self._consume_recorded_close_markers(
                markers=recorded_close_markers[(symbol, position_side)],
                quantity=quantity,
                created_at=created_at,
            ):
                continue
            fallback_pnl = self._consume_lots(
                open_lots_by_key=open_lots_by_key,
                relationship_id=None,
                symbol=symbol,
                position_side=position_side,
                quantity=quantity,
                price=price,
                created_at=created_at,
            )
            pnl = exchange_realized_pnl if history_row.get("exchange_realized_pnl") is not None else fallback_pnl
            if created_at >= now - timedelta(days=1):
                realized_24h += pnl
            if created_at >= now - timedelta(days=7):
                realized_7d += pnl

        positions: list[dict[str, Any]] = []
        for (relationship_id, symbol, position_side), lots in open_lots_by_key.items():
            quantity = sum(self._to_float(item.get("quantity")) for item in lots)
            if quantity <= 1e-9:
                continue
            weighted_entry = (
                sum(self._to_float(item.get("quantity")) * self._to_float(item.get("entry_price")) for item in lots) / quantity
            )
            opened_at = min((item.get("opened_at") for item in lots if item.get("opened_at") is not None), default=None)
            last_activity_at = max(
                (item.get("last_activity_at") for item in lots if item.get("last_activity_at") is not None),
                default=opened_at,
            )
            positions.append(
                {
                    "relationship_id": relationship_id,
                    "symbol": symbol,
                    "side": position_side,
                    "quantity": round(quantity, 8),
                    "entry_price": round(weighted_entry, 8),
                    "opened_at": opened_at.isoformat() if isinstance(opened_at, datetime) else None,
                    "last_synced_at": last_activity_at.isoformat() if isinstance(last_activity_at, datetime) else None,
                }
            )

        return {
            "positions": positions,
            "realized_pnl_24h_usd": round(realized_24h, 2),
            "realized_pnl_7d_usd": round(realized_7d, 2),
            "activity_by_relationship": self._group_activity_by_relationship(activity_rows),
        }

    def _consume_lots(
        self,
        *,
        open_lots_by_key: dict[tuple[str, str, str], list[dict[str, Any]]],
        relationship_id: str | None,
        symbol: str,
        position_side: str,
        quantity: float,
        price: float,
        created_at: datetime,
    ) -> float:
        remaining = max(0.0, quantity)
        realized_pnl = 0.0

        if relationship_id:
            candidate_keys = [(relationship_id, symbol, position_side)]
        else:
            candidate_keys = [
                key
                for key, lots in open_lots_by_key.items()
                if key[1] == symbol and key[2] == position_side and lots
            ]
            candidate_keys.sort(
                key=lambda key: min(
                    self._timestamp_value(item.get("opened_at"))
                    for item in open_lots_by_key.get(key, [])
                ),
            )

        for key in candidate_keys:
            lots = open_lots_by_key.get(key, [])
            while remaining > 1e-9 and lots:
                lot = lots[0]
                close_qty = min(remaining, self._to_float(lot.get("quantity")))
                entry_price = self._to_float(lot.get("entry_price"))
                if close_qty <= 0:
                    lots.pop(0)
                    continue
                if entry_price > 0 and price > 0:
                    if position_side == "long":
                        realized_pnl += (price - entry_price) * close_qty
                    else:
                        realized_pnl += (entry_price - price) * close_qty
                lot["quantity"] = max(0.0, self._to_float(lot.get("quantity")) - close_qty)
                lot["last_activity_at"] = created_at
                if lot["quantity"] <= 1e-9:
                    lots.pop(0)
                remaining -= close_qty
            if remaining <= 1e-9:
                break

        return realized_pnl

    def _consume_recorded_close_markers(
        self,
        *,
        markers: list[dict[str, Any]],
        quantity: float,
        created_at: datetime,
    ) -> bool:
        if quantity <= 1e-9 or not markers:
            return False

        tolerance_seconds = 180.0
        tolerance_quantity = max(0.000001, quantity * 0.02)
        remaining = quantity
        applied: list[tuple[dict[str, Any], float]] = []

        for marker in markers:
            marker_remaining = self._to_float(marker.get("remaining_quantity"))
            marker_created_at = self._as_datetime(marker.get("created_at"))
            if marker_remaining <= 1e-9 or marker_created_at is None:
                continue
            if abs((marker_created_at - created_at).total_seconds()) > tolerance_seconds:
                continue
            matched_quantity = min(marker_remaining, remaining)
            if matched_quantity <= 1e-9:
                continue
            marker["remaining_quantity"] = max(0.0, marker_remaining - matched_quantity)
            applied.append((marker, matched_quantity))
            remaining -= matched_quantity
            if remaining <= tolerance_quantity:
                return True

        for marker, matched_quantity in applied:
            marker["remaining_quantity"] = self._to_float(marker.get("remaining_quantity")) + matched_quantity
        return False

    def _build_attributed_positions(
        self,
        *,
        copy_state: dict[str, Any],
        trading_snapshot: dict[str, Any],
    ) -> tuple[list[dict[str, Any]], list[str]]:
        wallet_positions = trading_snapshot.get("positions") if isinstance(trading_snapshot.get("positions"), list) else []
        positions_loaded = self._positions_loaded(trading_snapshot)
        wallet_position_lookup = {
            (str(item.get("symbol") or "").upper(), str(item.get("side") or "").lower()): item
            for item in wallet_positions
            if str(item.get("symbol") or "").strip() and str(item.get("side") or "").strip()
        }
        markets = trading_snapshot.get("markets") if isinstance(trading_snapshot.get("markets"), list) else []
        market_lookup = {
            str(item.get("symbol") or "").upper(): self._to_float(item.get("mark_price"))
            for item in markets
        }

        attributed_positions: list[dict[str, Any]] = []
        used_wallet_keys: set[tuple[str, str]] = set()
        for item in copy_state["positions"]:
            symbol = str(item["symbol"]).upper()
            side = str(item["side"]).lower()
            wallet_position = wallet_position_lookup.get((symbol, side))
            if positions_loaded and self._position_size(wallet_position) <= 0:
                continue
            mark_price = self._to_float((wallet_position or {}).get("mark_price")) or market_lookup.get(symbol, 0.0)
            if positions_loaded and mark_price <= 0:
                continue
            quantity = self._to_float(item["quantity"])
            entry_price = self._to_float(item["entry_price"])
            notional_usd = quantity * mark_price if mark_price > 0 else 0.0
            unrealized_pnl = 0.0
            if mark_price > 0 and entry_price > 0:
                unrealized_pnl = (mark_price - entry_price) * quantity if side == "long" else (entry_price - mark_price) * quantity
            attributed_positions.append(
                {
                    **item,
                    "mark_price": round(mark_price, 8),
                    "notional_usd": round(notional_usd, 2),
                    "unrealized_pnl_usd": round(unrealized_pnl, 2),
                }
            )
            if wallet_position is not None:
                used_wallet_keys.add((symbol, side))

        unattributed_details: list[str] = []
        if not positions_loaded:
            return attributed_positions, unattributed_details

        for wallet_position in wallet_positions:
            symbol = str(wallet_position.get("symbol") or "").upper()
            side = str(wallet_position.get("side") or "").lower()
            key = (symbol, side)
            if key in used_wallet_keys:
                wallet_qty = self._position_size(wallet_position)
                copy_qty = sum(
                    self._to_float(item["quantity"])
                    for item in attributed_positions
                    if (str(item["symbol"]).upper(), str(item["side"]).lower()) == key
                )
                if abs(wallet_qty - copy_qty) > max(0.001, wallet_qty * 0.15):
                    unattributed_details.append(
                        f"{symbol} {side} has wallet size {wallet_qty:.4f} while copy-attributed size is {copy_qty:.4f}."
                    )
                continue
            if self._position_size(wallet_position) > 0:
                unattributed_details.append(
                    f"{symbol} {side} exposure is present in the wallet but not attributable to mirrored activity."
                )

        return attributed_positions, unattributed_details

    def _build_follows(
        self,
        *,
        relationships: list[dict[str, Any]],
        runtime_profiles: dict[str, dict[str, Any]],
        copy_state: dict[str, Any],
        attributed_positions: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        positions_by_relationship: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in attributed_positions:
            positions_by_relationship[str(item["relationship_id"])].append(item)

        follows: list[dict[str, Any]] = []
        for relationship in relationships:
            relationship_id = str(relationship["id"])
            profile = runtime_profiles.get(str(relationship["source_runtime_id"])) or {}
            trust = profile.get("trust") if isinstance(profile.get("trust"), dict) else {}
            creator = profile.get("creator") if isinstance(profile.get("creator"), dict) else {}
            drift = profile.get("drift") if isinstance(profile.get("drift"), dict) else {}
            relationship_positions = positions_by_relationship.get(relationship_id, [])
            relationship_activity = copy_state["activity_by_relationship"].get(relationship_id, [])
            exposure_usd = sum(self._to_float(item["notional_usd"]) for item in relationship_positions)
            unrealized_pnl = sum(self._to_float(item["unrealized_pnl_usd"]) for item in relationship_positions)
            last_execution = relationship_activity[0] if relationship_activity else None
            follows.append(
                {
                    "id": relationship_id,
                    "source_runtime_id": relationship["source_runtime_id"],
                    "source_bot_definition_id": relationship["source_bot_definition_id"],
                    "source_bot_name": relationship["source_bot_name"],
                    "source_rank": profile.get("rank"),
                    "source_drawdown_pct": self._to_float(profile.get("drawdown")),
                    "source_trust_score": int(self._to_float(trust.get("trust_score"), 0)),
                    "source_risk_grade": trust.get("risk_grade"),
                    "source_health": trust.get("health"),
                    "source_drift_status": drift.get("status"),
                    "creator_display_name": creator.get("display_name"),
                    "scale_bps": int(self._to_float(relationship.get("scale_bps"), 0)),
                    "status": relationship["status"],
                    "confirmed_at": relationship["confirmed_at"],
                    "updated_at": relationship["updated_at"],
                    "copied_open_notional_usd": round(exposure_usd, 2),
                    "copied_unrealized_pnl_usd": round(unrealized_pnl, 2),
                    "copied_position_count": len(relationship_positions),
                    "positions": relationship_positions,
                    "last_execution_at": last_execution.get("created_at") if isinstance(last_execution, dict) else None,
                    "last_execution_status": last_execution.get("status") if isinstance(last_execution, dict) else None,
                    "last_execution_symbol": last_execution.get("symbol") if isinstance(last_execution, dict) else None,
                    "max_notional_usd": relationship.get("max_notional_usd"),
                }
            )
        return follows

    def _build_alerts(
        self,
        *,
        follows: list[dict[str, Any]],
        baskets: list[dict[str, Any]],
        readiness: dict[str, Any],
        unattributed_details: list[str],
        activity_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        alerts: list[dict[str, Any]] = []
        for follow in follows:
            if str(follow.get("source_health") or "") in {"stale", "offline", "failed"}:
                alerts.append(
                    {
                        "kind": "stale_leader",
                        "title": f"{follow['source_bot_name']} is stale",
                        "detail": "Source runtime health is no longer stable. Review the follow before the next mirrored action.",
                        "severity": "warning",
                    }
                )
            if str(follow.get("status") or "") != "active":
                alerts.append(
                    {
                        "kind": "follow_paused",
                        "title": f"{follow['source_bot_name']} is not active",
                        "detail": "This follow is paused or stopped and will not mirror new source actions.",
                        "severity": "neutral",
                    }
                )

        recent_failures = [
            row for row in activity_rows
            if str(row.get("status") or "") == "error"
        ][:4]
        for row in recent_failures:
            alerts.append(
                {
                    "kind": "execution_failure",
                    "title": f"Mirrored {str(row.get('action_type') or 'action').replace('_', ' ')} failed",
                    "detail": str(row.get("error_reason") or "The follower order did not complete successfully."),
                    "severity": "critical",
                }
            )

        for detail in unattributed_details[:3]:
            alerts.append(
                {
                    "kind": "unattributed_exposure",
                    "title": "Unattributed exposure detected",
                    "detail": detail,
                    "severity": "warning",
                }
            )

        for basket in baskets:
            health = ((basket.get("health") or {}).get("health")) if isinstance(basket.get("health"), dict) else None
            if health in {"risk", "killed"}:
                alerts.append(
                    {
                        "kind": "portfolio_risk",
                        "title": f"{basket.get('name') or 'Portfolio basket'} needs attention",
                        "detail": ", ".join(((basket.get("health") or {}).get("alerts") or [])[:2]) or "Portfolio risk limits were breached.",
                        "severity": "critical" if health == "killed" else "warning",
                    }
                )

        if not readiness.get("ready"):
            for blocker in list(readiness.get("blockers") or [])[:2]:
                alerts.append(
                    {
                        "kind": "readiness_blocker",
                        "title": "Copy setup is blocked",
                        "detail": blocker,
                        "severity": "neutral",
                    }
                )

        return alerts[:10]

    def _build_summary(
        self,
        *,
        follows: list[dict[str, Any]],
        positions: list[dict[str, Any]],
        copy_state: dict[str, Any],
        readiness: dict[str, Any],
    ) -> dict[str, Any]:
        active_follows = [item for item in follows if str(item.get("status") or "") == "active"]
        copied_open_notional_usd = sum(self._to_float(item.get("notional_usd")) for item in positions)
        copied_unrealized_pnl_usd = sum(self._to_float(item.get("unrealized_pnl_usd")) for item in positions)
        return {
            "active_follows": len(active_follows),
            "open_positions": len(positions),
            "copied_open_notional_usd": round(copied_open_notional_usd, 2),
            "copied_unrealized_pnl_usd": round(copied_unrealized_pnl_usd, 2),
            "copied_realized_pnl_usd_24h": round(self._to_float(copy_state.get("realized_pnl_24h_usd")), 2),
            "copied_realized_pnl_usd_7d": round(self._to_float(copy_state.get("realized_pnl_7d_usd")), 2),
            "readiness_status": "ready" if readiness.get("ready") else "blocked",
        }

    def _group_activity_by_relationship(self, activity_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in activity_rows:
            relationship_id = str(row.get("relationship_id") or "").strip()
            if relationship_id:
                grouped[relationship_id].append(row)
        return grouped

    def _serialize_activity_row(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row.get("id"),
            "relationship_id": row.get("relationship_id"),
            "source_runtime_id": row.get("source_runtime_id"),
            "source_event_id": row.get("source_event_id"),
            "symbol": row.get("symbol"),
            "side": row.get("position_side") or row.get("side"),
            "action_type": row.get("action_type"),
            "copied_quantity": round(self._to_float(row.get("copied_quantity")), 8),
            "reference_price": round(self._to_float(row.get("reference_price")), 8),
            "notional_estimate_usd": round(self._to_float(row.get("notional_estimate_usd")), 2),
            "status": row.get("status"),
            "error_reason": row.get("error_reason"),
            "created_at": row.get("created_at"),
            "updated_at": row.get("updated_at"),
        }

    def _serialize_discover_row(self, row: dict[str, Any]) -> dict[str, Any]:
        creator = row.get("creator") if isinstance(row.get("creator"), dict) else {}
        trust = row.get("trust") if isinstance(row.get("trust"), dict) else {}
        return {
            "runtime_id": row.get("runtime_id"),
            "bot_definition_id": row.get("bot_definition_id"),
            "bot_name": row.get("bot_name"),
            "strategy_type": row.get("strategy_type"),
            "rank": row.get("rank"),
            "drawdown": round(self._to_float(row.get("drawdown")), 2),
            "trust_score": int(self._to_float(trust.get("trust_score"), 0)),
            "creator_display_name": creator.get("display_name"),
            "creator_id": creator.get("creator_id"),
        }

    def _serialize_basket_summary(self, basket: dict[str, Any]) -> dict[str, Any]:
        health = basket.get("health") if isinstance(basket.get("health"), dict) else {}
        return {
            "id": basket.get("id"),
            "name": basket.get("name"),
            "status": basket.get("status"),
            "member_count": len(basket.get("members") or []),
            "target_notional_usd": round(self._to_float(basket.get("target_notional_usd")), 2),
            "current_notional_usd": round(self._to_float(basket.get("current_notional_usd")), 2),
            "health": health.get("health"),
            "alert_count": int(self._to_float(health.get("alert_count"), 0)),
            "aggregate_live_pnl_usd": round(self._to_float(health.get("aggregate_live_pnl_usd")), 2),
            "aggregate_drawdown_pct": round(self._to_float(health.get("aggregate_drawdown_pct")), 2),
            "last_rebalanced_at": basket.get("last_rebalanced_at"),
        }

    @staticmethod
    def _as_datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, (int, float)):
            numeric = float(value)
            if numeric > 10_000_000_000:
                numeric /= 1000.0
            try:
                return datetime.fromtimestamp(numeric, tz=UTC)
            except (OverflowError, OSError, ValueError):
                return None
        text = str(value).strip()
        if not text:
            return None
        try:
            numeric = float(text)
        except ValueError:
            numeric = None
        if numeric is not None:
            if numeric > 10_000_000_000:
                numeric /= 1000.0
            try:
                return datetime.fromtimestamp(numeric, tz=UTC)
            except (OverflowError, OSError, ValueError):
                return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    @classmethod
    def _normalize_manual_history_row(cls, row: dict[str, Any]) -> dict[str, Any] | None:
        event_kind, position_side = cls._position_history_event_kind(row)
        amount = cls._to_float(row.get("amount"))
        price = cls._to_float(row.get("price"))
        symbol = str(row.get("symbol") or "").strip().upper().replace("-PERP", "")
        if event_kind not in {"open", "close"} or position_side not in {"long", "short"}:
            return None
        if amount <= 1e-12 or price <= 0 or not symbol:
            return None
        return {
            "history_id": row.get("history_id") or row.get("historyId"),
            "order_id": row.get("order_id") or row.get("orderId"),
            "symbol": symbol,
            "event_kind": event_kind,
            "position_side": position_side,
            "amount": amount,
            "price": price,
            "created_at": row.get("created_at") or row.get("createdAt"),
        }

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
        if amount <= 1e-12 or price <= 0:
            return None, None
        if reduce_only:
            return "close", "short" if side == "long" else "long"
        return "open", side

    @staticmethod
    def _normalize_position_side(value: Any) -> str | None:
        normalized = str(value or "").lower().strip()
        if normalized in {"bid", "long"}:
            return "long"
        if normalized in {"ask", "short"}:
            return "short"
        return None

    @staticmethod
    def _timestamp_value(value: Any) -> float:
        if isinstance(value, (int, float)):
            numeric = float(value)
            return numeric / 1000.0 if numeric > 10_000_000_000 else numeric
        text = str(value or "").strip()
        if not text:
            return 0.0
        try:
            numeric = float(text)
        except ValueError:
            numeric = None
        if numeric is not None:
            return numeric / 1000.0 if numeric > 10_000_000_000 else numeric
        try:
            return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
        except ValueError:
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

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value in (None, ""):
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _positions_loaded(trading_snapshot: dict[str, Any]) -> bool:
        if "positions_loaded" in trading_snapshot:
            return bool(trading_snapshot.get("positions_loaded"))
        return "positions" in trading_snapshot

    def _position_size(self, position: dict[str, Any] | None) -> float:
        if not isinstance(position, dict):
            return 0.0
        return abs(
            self._to_float(position.get("quantity"))
            or self._to_float(position.get("amount"))
        )
