from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime
from decimal import ROUND_DOWN, ROUND_UP, Decimal
from typing import Any

from src.services.event_broadcaster import broadcaster
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_client import PacificaClient, PacificaClientError
from src.services.pacifica_market_data_service import get_pacifica_market_data_service
from src.services.supabase_rest import SupabaseRestClient
from src.services.trading_snapshot_cache_service import get_trading_snapshot_cache_service


class TradingService:
    def __init__(self) -> None:
        self.pacifica = PacificaClient()
        self.auth_service = PacificaAuthService()
        self.supabase = SupabaseRestClient()
        self.market_data = get_pacifica_market_data_service()
        self.snapshot_cache = get_trading_snapshot_cache_service()

    async def get_account_snapshot(self, db: Any, wallet_address: str) -> dict[str, Any]:
        return await self.snapshot_cache.get_or_load(wallet_address, lambda: self._load_account_snapshot(db, wallet_address))

    async def _load_account_snapshot(self, db: Any, wallet_address: str) -> dict[str, Any]:
        user = self._upsert_user(db, wallet_address)
        authorization = self.auth_service.get_authorization_by_wallet(None, wallet_address)
        markets = await self._load_markets()
        price_lookup = {
            str(item.get("symbol") or ""): float(item.get("mark_price") or 0.0)
            for item in markets
            if str(item.get("symbol") or "")
        }
        account_info, positions, orders, fills, portfolio = await asyncio.gather(
            self._safe_read(lambda: self.pacifica.get_account_info(wallet_address), {"balance": 0.0, "equity": 0.0, "fee_level": 0}),
            self._safe_read(lambda: self.pacifica.get_positions(wallet_address, price_lookup=price_lookup), []),
            self._safe_read(lambda: self.pacifica.get_open_orders(wallet_address), []),
            self._safe_read(lambda: self.pacifica.get_position_history(wallet_address, limit=60, offset=0), []),
            self._safe_read(lambda: self.pacifica.get_portfolio_history(wallet_address, limit=90, offset=0), []),
        )
        market_lookup = {item["symbol"]: item for item in markets}
        normalized_positions = [self._serialize_position(item) for item in positions]
        normalized_orders = [self._serialize_order(item, market_lookup) for item in orders]
        normalized_fills = [self._serialize_fill(item) for item in fills]
        recent_activity = self._list_recent_activity(user_id=user["id"])
        total_unrealized = sum(item["unrealized_pnl"] for item in normalized_positions)
        total_realized = sum(item["pnl"] for item in normalized_fills)
        open_notional = sum(item["notional_usd"] for item in normalized_positions)
        winning_fills = [item for item in normalized_fills if item["event_type"].startswith("close_")]
        win_rate = None if not winning_fills else sum(1 for item in winning_fills if item["pnl"] > 0) / len(winning_fills)
        balance = float(account_info.get("balance", 0) or 0)
        equity = float(account_info.get("equity", balance) or balance)
        portfolio_value = float(portfolio[-1]["equity"] if portfolio else equity)
        return {
            "user_id": user["id"],
            "wallet_address": wallet_address,
            "account_address": wallet_address,
            "agent_wallet_address": authorization.get("agent_wallet_address") if authorization else None,
            "authorization_status": authorization.get("status") if authorization else "inactive",
            "can_trade": bool(authorization and authorization.get("status") == "active"),
            "summary": {
                "balance": balance,
                "fee_level": int(account_info.get("fee_level", 0) or 0),
                "portfolio_value": portfolio_value,
                "total_unrealized_pnl": total_unrealized,
                "total_realized_pnl": total_realized,
                "open_notional": open_notional,
                "position_count": len(normalized_positions),
                "open_order_count": len(normalized_orders),
                "win_rate": win_rate,
            },
            "portfolio": portfolio,
            "markets": markets,
            "positions": normalized_positions,
            "orders": normalized_orders,
            "fills": normalized_fills,
            "activity": recent_activity,
            "updated_at": datetime.now(tz=UTC).isoformat(),
        }

    async def list_positions(self, db: Any, wallet_address: str) -> list[dict[str, Any]]:
        return (await self.get_account_snapshot(db, wallet_address))["positions"]

    async def list_orders(self, db: Any, wallet_address: str) -> list[dict[str, Any]]:
        return (await self.get_account_snapshot(db, wallet_address))["orders"]

    async def place_order(self, db: Any, *, wallet_address: str, symbol: str, side: str, order_type: str, leverage: int, size_usd: float | None = None, quantity: float | None = None, limit_price: float | None = None, reduce_only: bool = False, tif: str = "GTC", slippage_percent: float = 0.5) -> dict[str, Any]:
        credentials = self.auth_service.get_trading_credentials(None, wallet_address)
        if credentials is None:
            raise ValueError("Authorize a delegated Pacifica agent wallet before placing orders.")
        normalized_symbol = self._normalize_symbol(symbol)
        if order_type == "limit" and limit_price is None:
            raise ValueError("A limit price is required for limit orders.")
        market = await self._get_market(normalized_symbol)
        reference_price = limit_price if limit_price is not None else float(market.get("mark_price", 0) or 0)
        if reference_price <= 0:
            raise ValueError(f"No reference price available for {normalized_symbol}.")
        if quantity is None:
            if size_usd is None:
                raise ValueError("Either size_usd or quantity must be provided.")
            quantity = (size_usd * leverage) / reference_price
        quantity = self._normalize_order_quantity(
            quantity,
            lot_size=float(market.get("lot_size", 0) or 0),
            symbol=normalized_symbol,
        )
        if not reduce_only:
            self._validate_market_leverage(market=market, symbol=normalized_symbol, leverage=leverage)
            await self._ensure_leverage(
                wallet_address=wallet_address,
                credentials=credentials,
                symbol=normalized_symbol,
                leverage=leverage,
            )
        payload: dict[str, Any] = {
            "account": credentials["account_address"],
            "agent_wallet": credentials["agent_wallet_address"],
            "__agent_private_key": credentials["agent_private_key"],
            "symbol": normalized_symbol,
            "side": self._to_pacifica_side(side),
            "amount": quantity,
            "reduce_only": reduce_only,
            "slippage_percent": slippage_percent,
            "type": "create_order" if order_type == "limit" else "create_market_order",
        }
        if order_type == "limit":
            payload.update(
                self._build_limit_order_price_fields(
                    symbol=normalized_symbol,
                    side=side,
                    price=float(limit_price or 0),
                    market=market,
                )
            )
            payload["tif"] = tif
        response = await self.pacifica.place_order(payload)
        user = self._upsert_user(db, wallet_address)
        self._record_audit_event(db, user_id=user["id"], action="trading.order.submitted", payload={"symbol": normalized_symbol, "side": side, "order_type": order_type, "quantity": quantity, "size_usd": size_usd, "limit_price": limit_price, "reduce_only": reduce_only, "leverage": leverage, "request_id": response["request_id"]})
        self.snapshot_cache.invalidate(wallet_address)
        snapshot = await self.get_account_snapshot(db, wallet_address)
        await self._publish_snapshot(user_id=user["id"], event="trading.order.submitted", payload={"request_id": response["request_id"], "symbol": normalized_symbol, "side": side, "order_type": order_type}, snapshot=snapshot)
        return {"status": response["status"], "request_id": response["request_id"], "network": response["network"], "snapshot": snapshot}

    async def cancel_order(self, db: Any, *, wallet_address: str, symbol: str, order_id: str) -> dict[str, Any]:
        credentials = self.auth_service.get_trading_credentials(None, wallet_address)
        if credentials is None:
            raise ValueError("Authorize a delegated Pacifica agent wallet before cancelling orders.")
        normalized_symbol = self._normalize_symbol(symbol)
        open_orders = await self._safe_read(lambda: self.pacifica.get_open_orders(wallet_address), [])
        payload: dict[str, Any] = {
            "type": "cancel_order",
            "account": credentials["account_address"],
            "agent_wallet": credentials["agent_wallet_address"],
            "__agent_private_key": credentials["agent_private_key"],
            "symbol": normalized_symbol,
            **self._build_cancel_order_request_fields(
                order_id=order_id,
                symbol=normalized_symbol,
                market=await self._get_market(normalized_symbol),
                open_orders=open_orders,
            ),
        }
        response = await self.pacifica.place_order(payload)
        user = self._upsert_user(db, wallet_address)
        self._record_audit_event(db, user_id=user["id"], action="trading.order.cancelled", payload={"symbol": normalized_symbol, "order_id": order_id, "request_id": response["request_id"]})
        self.snapshot_cache.invalidate(wallet_address)
        snapshot = await self.get_account_snapshot(db, wallet_address)
        await self._publish_snapshot(user_id=user["id"], event="trading.order.cancelled", payload={"order_id": order_id, "symbol": normalized_symbol, "request_id": response["request_id"]}, snapshot=snapshot)
        return {"status": response["status"], "request_id": response["request_id"], "network": response["network"], "snapshot": snapshot}

    async def _publish_snapshot(self, *, user_id: str, event: str, payload: dict[str, Any], snapshot: dict[str, Any]) -> None:
        await broadcaster.publish(channel=f"user:{user_id}", event=event, payload=payload)
        await broadcaster.publish(channel=f"user:{user_id}", event="trading.account.updated", payload=snapshot)

    async def _safe_read(self, loader: Any, fallback: Any) -> Any:
        try:
            return await loader()
        except PacificaClientError:
            return fallback

    async def _ensure_leverage(
        self,
        *,
        wallet_address: str,
        credentials: dict[str, str],
        symbol: str,
        leverage: int,
    ) -> None:
        settings = await self._safe_read(lambda: self.pacifica.get_account_settings(wallet_address), [])
        current = next(
            (
                item
                for item in settings
                if self._normalize_symbol(str(item.get("symbol") or "")) == symbol
            ),
            None,
        )
        if isinstance(current, dict) and int(current.get("leverage") or 0) == leverage:
            return
        market = await self._get_market(symbol)
        self._validate_market_leverage(market=market, symbol=symbol, leverage=leverage)
        await self.pacifica.place_order(
            {
                "type": "update_leverage",
                "account": credentials["account_address"],
                "agent_wallet": credentials["agent_wallet_address"],
                "__agent_private_key": credentials["agent_private_key"],
                "symbol": symbol,
                "leverage": leverage,
            }
        )

    def _upsert_user(self, db: Any, wallet_address: str) -> dict[str, Any]:
        del db
        user = self.supabase.maybe_one("users", filters={"wallet_address": wallet_address})
        if user is not None:
            return user
        return self.supabase.insert("users", {"id": str(uuid.uuid4()), "wallet_address": wallet_address, "display_name": wallet_address[:8], "auth_provider": "privy", "created_at": datetime.now(tz=UTC).isoformat()})[0]

    def _record_audit_event(self, db: Any, *, user_id: str, action: str, payload: dict[str, Any]) -> None:
        del db
        self.supabase.insert("audit_events", {"id": str(uuid.uuid4()), "user_id": user_id, "action": action, "payload": payload, "created_at": datetime.now(tz=UTC).isoformat()})

    def _list_recent_activity(self, *, user_id: str) -> list[dict[str, Any]]:
        events = self.supabase.select("audit_events", filters={"user_id": user_id}, order="created_at.desc", limit=12)
        return [{"id": event.get("id"), "action": event.get("action"), "payload": event.get("payload") or {}, "created_at": event.get("created_at")} for event in events]

    def _normalize_symbol(self, symbol: str) -> str:
        return symbol.upper().removesuffix("-PERP")

    def _to_pacifica_side(self, side: str) -> str:
        normalized = side.lower().strip()
        if normalized == "long":
            return "bid"
        if normalized == "short":
            return "ask"
        raise ValueError("Order side must be either 'long' or 'short'.")

    async def _get_market(self, symbol: str) -> dict[str, Any]:
        markets = await self._load_markets()
        normalized_symbol = self._normalize_symbol(symbol)
        market = next((item for item in markets if self._normalize_symbol(item.get("symbol")) == normalized_symbol or self._normalize_symbol(item.get("display_symbol")) == normalized_symbol), None)
        if market is None:
            raise PacificaClientError(f"Unsupported Pacifica market: {normalized_symbol}")
        return market

    async def _load_markets(self) -> list[dict[str, Any]]:
        if isinstance(self.pacifica, PacificaClient):
            return await self.market_data.get_markets()
        return await self.pacifica.get_markets()

    def _normalize_order_quantity(self, quantity: float, *, lot_size: float, symbol: str) -> float:
        normalized = Decimal(str(quantity))
        if lot_size > 0:
            step = Decimal(str(lot_size))
            normalized = (normalized / step).to_integral_value(rounding=ROUND_DOWN) * step
        normalized_float = float(normalized)
        if normalized_float <= 0:
            raise ValueError(f"Order size is below the minimum tradable increment for {symbol}.")
        return normalized_float

    def _build_limit_order_price_fields(
        self,
        *,
        symbol: str,
        side: str,
        price: float,
        market: dict[str, Any],
    ) -> dict[str, Any]:
        tick_size = float(market.get("tick_size", 0) or 0)
        rounding = ROUND_DOWN if side.lower().strip() == "long" else ROUND_UP
        normalized_price = self._normalize_price_to_tick(price, tick_size=tick_size, rounding=rounding)
        fields: dict[str, Any] = {"price": normalized_price}
        tick_level = self._price_to_tick_level(normalized_price, tick_size=tick_size)
        if tick_level is not None:
            fields["tick_level"] = tick_level
        return fields

    def _build_cancel_order_request_fields(
        self,
        *,
        order_id: str,
        symbol: str,
        market: dict[str, Any],
        open_orders: list[dict[str, Any]],
    ) -> dict[str, Any]:
        identifier = self._extract_order_identifier(order_id)
        matched_order = self._find_open_order(
            identifier=identifier,
            symbol=symbol,
            open_orders=open_orders,
        )
        if not isinstance(matched_order, dict):
            return identifier
        request_fields = dict(identifier)
        side = str(matched_order.get("side") or "").strip()
        if side:
            request_fields["side"] = side
        tick_level = matched_order.get("tick_level")
        if tick_level in (None, ""):
            tick_level = self._price_to_tick_level(
                matched_order.get("price"),
                tick_size=float(market.get("tick_size", 0) or 0),
            )
        else:
            tick_level = self._to_int(tick_level)
        if tick_level is not None:
            request_fields["tick_level"] = tick_level
        return request_fields

    @staticmethod
    def _extract_order_identifier(order_id: str) -> dict[str, Any]:
        if order_id.isdigit():
            return {"order_id": int(order_id)}
        return {"client_order_id": order_id}

    def _find_open_order(
        self,
        *,
        identifier: dict[str, Any],
        symbol: str,
        open_orders: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        for order in open_orders:
            if self._normalize_symbol(str(order.get("symbol") or "")) != symbol:
                continue
            if "order_id" in identifier and str(order.get("order_id") or "").strip() == str(identifier["order_id"]):
                return order
            if "client_order_id" in identifier and str(order.get("client_order_id") or "").strip() == str(identifier["client_order_id"]):
                return order
        return None

    def _validate_market_leverage(self, *, market: dict[str, Any], symbol: str, leverage: int) -> None:
        market_max_leverage = self._to_int(market.get("max_leverage"))
        if market_max_leverage is None or market_max_leverage <= 0:
            return
        if leverage > market_max_leverage:
            raise ValueError(
                f"Requested leverage {leverage} exceeds {symbol} market max leverage {market_max_leverage}."
            )

    @staticmethod
    def _normalize_price_to_tick(price: float, *, tick_size: float, rounding: str) -> float:
        normalized = Decimal(str(price))
        if tick_size > 0:
            step = Decimal(str(tick_size))
            normalized = (normalized / step).to_integral_value(rounding=rounding) * step
        return float(normalized)

    @staticmethod
    def _price_to_tick_level(price: Any, *, tick_size: float) -> int | None:
        if tick_size <= 0:
            return None
        try:
            price_decimal = Decimal(str(price))
            tick_decimal = Decimal(str(tick_size))
            if tick_decimal <= 0:
                return None
            return int((price_decimal / tick_decimal).to_integral_value(rounding=ROUND_DOWN))
        except (ArithmeticError, TypeError, ValueError):
            return None

    @staticmethod
    def _to_int(value: Any) -> int | None:
        try:
            if value in (None, ""):
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _serialize_position(self, position: dict[str, Any]) -> dict[str, Any]:
        symbol = str(position["symbol"])
        direction = 1 if str(position["side"]).lower() in {"bid", "long"} else -1
        side = "long" if direction > 0 else "short"
        quantity = abs(float(position.get("amount", 0) or 0))
        entry_price = float(position.get("entry_price", 0) or 0)
        mark_price = float(position.get("mark_price", 0) or 0)
        margin = abs(float(position.get("margin", 0) or 0))
        unrealized_pnl = (mark_price - entry_price) * quantity * direction
        notional_usd = quantity * mark_price
        leverage = round(notional_usd / margin, 2) if margin > 0 else None
        pnl_pct = (unrealized_pnl / margin * 100) if margin > 0 else 0.0
        return {"id": f"{symbol}:{side}", "symbol": symbol, "display_symbol": f"{symbol}-PERP", "side": side, "quantity": quantity, "notional_usd": notional_usd, "entry_price": entry_price, "mark_price": mark_price, "margin": margin, "leverage": leverage, "isolated": bool(position.get("isolated", False)), "unrealized_pnl": unrealized_pnl, "unrealized_pnl_pct": pnl_pct, "updated_at": position.get("updated_at") or position.get("created_at")}

    def _serialize_order(self, order: dict[str, Any], market_lookup: dict[str, dict[str, Any]]) -> dict[str, Any]:
        symbol = str(order.get("symbol") or "")
        side = "long" if str(order.get("side", "")).lower() in {"bid", "long"} else "short"
        quantity = abs(float(order.get("initial_amount", 0) or 0))
        filled_quantity = abs(float(order.get("filled_amount", 0) or 0))
        remaining_quantity = abs(float(order.get("remaining_amount", 0) or 0))
        limit_price = order.get("price")
        mark_price = float((market_lookup.get(symbol) or {}).get("mark_price", 0) or 0)
        reference_price = float(limit_price or mark_price or 0)
        return {"id": str(order.get("order_id") or order.get("client_order_id") or uuid.uuid4()), "order_id": str(order.get("order_id") or ""), "client_order_id": order.get("client_order_id"), "symbol": symbol, "display_symbol": f"{symbol}-PERP", "side": side, "order_type": str(order.get("order_type") or "market"), "quantity": quantity, "filled_quantity": filled_quantity, "remaining_quantity": remaining_quantity, "notional_usd": quantity * reference_price if reference_price else 0.0, "limit_price": float(limit_price or 0) if limit_price is not None else None, "reduce_only": bool(order.get("reduce_only", False)), "created_at": order.get("created_at"), "updated_at": order.get("updated_at")}

    def _serialize_fill(self, fill: dict[str, Any]) -> dict[str, Any]:
        symbol = str(fill.get("symbol") or "")
        event_type = str(fill.get("event_type") or "")
        side = "long" if "long" in event_type else "short"
        quantity = abs(float(fill.get("amount", 0) or 0))
        price = float(fill.get("price", 0) or 0)
        return {"id": str(fill.get("history_id") or uuid.uuid4()), "symbol": symbol, "display_symbol": f"{symbol}-PERP", "side": side, "event_type": event_type, "quantity": quantity, "notional_usd": quantity * price, "fill_price": price, "fee": float(fill.get("fee", 0) or 0), "pnl": float(fill.get("pnl", 0) or 0), "liquidity": "maker" if bool(fill.get("is_maker", False)) else "taker", "filled_at": fill.get("created_at")}
