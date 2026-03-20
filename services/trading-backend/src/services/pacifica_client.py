import asyncio
import uuid
from time import time
from typing import Any

import httpx

try:
    import base58
    from solders.keypair import Keypair
except ImportError:  # pragma: no cover - surfaced as runtime config error
    base58 = None
    Keypair = None

from src.core.settings import get_settings
from src.services.pacifica_rate_limiter import get_pacifica_rate_limiter
from src.services.pacifica_signing import prepare_message


CLIENT_ORDER_ID_NAMESPACE = uuid.UUID("d98f4ee8-e7ed-4d37-8f62-d3f87d22dcff")


class PacificaClientError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class PacificaClient:
    def __init__(self) -> None:
        self.settings = get_settings()
        self._lock = asyncio.Lock()
        self._connected = False
        self._rate_limit_interval = 0.05
        self._rate_limiter = get_pacifica_rate_limiter()
        default_headers: dict[str, str] = {}
        if self.settings.pacifica_api_key:
            default_headers["PF-API-KEY"] = self.settings.pacifica_api_key
        self._http = httpx.AsyncClient(timeout=20.0, headers=default_headers)

    async def connect_ws(self) -> None:
        self._connected = True

    async def close_ws(self) -> None:
        self._connected = False
        await self._http.aclose()

    async def _throttle(self, *, bucket: str = "public", units: int = 1) -> None:
        await self._rate_limiter.acquire(bucket=bucket, units=units)
        async with self._lock:
            await asyncio.sleep(self._rate_limit_interval)

    def _ensure_crypto_runtime(self) -> None:
        if base58 is None or Keypair is None:
            raise PacificaClientError(
                "Pacifica signing dependencies are missing. Install the backend dependencies again to add solders and base58."
            )

    def _build_endpoint_url(self, request_type: str) -> str:
        endpoint_map = {
            "bind_agent_wallet": "/agent/bind",
            "cancel_all_orders": "/orders/cancel_all",
            "cancel_order": "/orders/cancel",
            "cancel_twap_order": "/orders/twap/cancel",
            "create_market_order": "/orders/create_market",
            "create_order": "/orders/create",
            "create_twap_order": "/orders/twap/create",
            "set_position_tpsl": "/positions/tpsl",
            "update_leverage": "/account/leverage",
        }
        try:
            return f"{self.settings.pacifica_rest_url}{endpoint_map[request_type]}"
        except KeyError as exc:  # pragma: no cover - defensive guard
            raise PacificaClientError(f"Unsupported Pacifica request type: {request_type}") from exc

    def _uses_builder_code(self, request_type: str) -> bool:
        return request_type in {
            "create_market_order",
            "create_order",
            "create_twap_order",
            "set_position_tpsl",
        }

    def _infer_request_type(self, order_payload: dict[str, Any]) -> str:
        explicit_type = str(order_payload.get("type", "")).strip()
        if explicit_type in {
            "bind_agent_wallet",
            "cancel_all_orders",
            "cancel_order",
            "cancel_twap_order",
            "create_market_order",
            "create_order",
            "create_twap_order",
            "set_position_tpsl",
            "update_leverage",
        }:
            return explicit_type
        if "price" in order_payload or "tif" in order_payload:
            return "create_order"
        return "create_market_order"

    @staticmethod
    def canonicalize_client_order_id(
        value: Any,
        *,
        account: str | None = None,
        symbol: str | None = None,
        scope: str = "client_order_id",
    ) -> str | None:
        text = str(value or "").strip()
        if not text:
            return None
        try:
            return str(uuid.UUID(text))
        except (TypeError, ValueError, AttributeError):
            seed = "|".join((scope, account or "", symbol or "", text))
            return str(uuid.uuid5(CLIENT_ORDER_ID_NAMESPACE, seed))

    def _normalize_payload(
        self,
        request_type: str,
        order_payload: dict[str, Any],
        *,
        account: str | None = None,
    ) -> dict[str, Any]:
        ignored_keys = {
            "account",
            "agent_wallet",
            "__agent_private_key",
            "network",
            "request_id",
            "response",
            "source_user_id",
            "type",
        }
        payload = {key: value for key, value in order_payload.items() if key not in ignored_keys and value is not None}

        if request_type in {"create_market_order", "create_order", "create_twap_order"}:
            payload.setdefault("reduce_only", False)
            payload.setdefault("client_order_id", str(uuid.uuid4()))
            if request_type in {"create_market_order", "create_twap_order"}:
                payload.setdefault("slippage_percent", "0.5")

        if self.settings.pacifica_builder_code and self._uses_builder_code(request_type):
            payload["builder_code"] = self.settings.pacifica_builder_code

        for key in ("amount", "price", "slippage_percent", "shares"):
            if key in payload:
                payload[key] = str(payload[key])

        symbol = str(payload.get("symbol") or "").strip() or None
        if "client_order_id" in payload:
            normalized_client_order_id = self.canonicalize_client_order_id(
                payload.get("client_order_id"),
                account=account,
                symbol=symbol,
            )
            if normalized_client_order_id is None:
                payload.pop("client_order_id", None)
            else:
                payload["client_order_id"] = normalized_client_order_id

        take_profit = payload.get("take_profit")
        if isinstance(take_profit, dict):
            payload["take_profit"] = {
                nested_key: (
                    str(nested_value)
                    if nested_key in {"stop_price", "limit_price", "amount"}
                    else self.canonicalize_client_order_id(
                        nested_value,
                        account=account,
                        symbol=symbol,
                        scope="take_profit.client_order_id",
                    )
                    if nested_key == "client_order_id"
                    else nested_value
                )
                for nested_key, nested_value in take_profit.items()
                if nested_value is not None
            }
        stop_loss = payload.get("stop_loss")
        if isinstance(stop_loss, dict):
            payload["stop_loss"] = {
                nested_key: (
                    str(nested_value)
                    if nested_key in {"stop_price", "limit_price", "amount"}
                    else self.canonicalize_client_order_id(
                        nested_value,
                        account=account,
                        symbol=symbol,
                        scope="stop_loss.client_order_id",
                    )
                    if nested_key == "client_order_id"
                    else nested_value
                )
                for nested_key, nested_value in stop_loss.items()
                if nested_value is not None
            }

        return payload

    def _resolve_signer(
        self,
        requested_account: str | None,
        *,
        signer_private_key_override: str | None = None,
        agent_wallet_override: str | None = None,
    ) -> tuple[str, Keypair, str | None]:
        self._ensure_crypto_runtime()
        if signer_private_key_override:
            signer = Keypair.from_base58_string(signer_private_key_override)
            agent_wallet = agent_wallet_override or str(signer.pubkey())
            derived_agent = str(signer.pubkey())
            if agent_wallet != derived_agent:
                raise PacificaClientError(
                    f"Configured agent wallet {agent_wallet} does not match the delegated signer public key {derived_agent}."
                )
            if not requested_account:
                raise PacificaClientError("An account address is required when using delegated Pacifica agent credentials.")
            return requested_account, signer, agent_wallet

        configured_account = self.settings.pacifica_account_address
        if not configured_account:
            raise PacificaClientError("PACIFICA_ACCOUNT_ADDRESS is not configured")
        if requested_account and requested_account != configured_account:
            raise PacificaClientError(
                f"Pacifica live signing is only configured for {configured_account}. Received order for {requested_account}."
            )

        if self.settings.pacifica_agent_private_key:
            if not self.settings.pacifica_agent_wallet_public_key:
                raise PacificaClientError("PACIFICA_AGENT_WALLET_PUBLIC_KEY must be set when PACIFICA_AGENT_PRIVATE_KEY is configured")
            signer = Keypair.from_base58_string(self.settings.pacifica_agent_private_key)
            return configured_account, signer, self.settings.pacifica_agent_wallet_public_key

        if not self.settings.pacifica_private_key:
            raise PacificaClientError(
                "Pacifica live signing is not configured. Set PACIFICA_PRIVATE_KEY or PACIFICA_AGENT_PRIVATE_KEY."
            )
        signer = Keypair.from_base58_string(self.settings.pacifica_private_key)
        derived_account = str(signer.pubkey())
        if configured_account != derived_account:
            raise PacificaClientError(
                f"PACIFICA_ACCOUNT_ADDRESS does not match the configured PACIFICA_PRIVATE_KEY public key ({derived_account})."
            )
        return configured_account, signer, None

    def _sign_request(
        self,
        request_type: str,
        signature_payload: dict[str, Any],
        requested_account: str | None,
        *,
        signer_private_key_override: str | None = None,
        agent_wallet_override: str | None = None,
    ) -> tuple[dict[str, Any], str]:
        account, signer, agent_wallet = self._resolve_signer(
            requested_account,
            signer_private_key_override=signer_private_key_override,
            agent_wallet_override=agent_wallet_override,
        )
        signature_header = {
            "timestamp": int(time() * 1_000),
            "expiry_window": self.settings.pacifica_expiry_window_ms,
            "type": request_type,
        }
        message = prepare_message(signature_header, signature_payload)
        signature = base58.b58encode(bytes(signer.sign_message(message.encode("utf-8")))).decode("ascii")
        request_header: dict[str, Any] = {
            "account": account,
            "signature": signature,
            "timestamp": signature_header["timestamp"],
            "expiry_window": signature_header["expiry_window"],
        }
        if agent_wallet is not None:
            request_header["agent_wallet"] = agent_wallet
        return request_header, message

    @staticmethod
    def _extract_response_payload(response_json: dict[str, Any]) -> Any:
        if "data" in response_json:
            return response_json["data"]
        return response_json

    @staticmethod
    def _raise_http_error(context: str, exc: httpx.HTTPStatusError) -> None:
        status_code = exc.response.status_code
        body = exc.response.text
        raise PacificaClientError(f"Pacifica {context} request failed ({status_code}): {body}", status_code=status_code) from exc

    @staticmethod
    def _coerce_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_int(value: Any, default: int = 0) -> int:
        try:
            if value is None or value == "":
                return default
            return int(float(value))
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_bool(value: Any, default: bool = False) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "y"}:
                return True
            if normalized in {"false", "0", "no", "n"}:
                return False
        return bool(value)

    async def place_order(self, order_payload: dict[str, Any]) -> dict[str, Any]:
        await self._throttle(bucket="write")
        request_type = self._infer_request_type(order_payload)
        requested_account = str(order_payload.get("account", "")).strip() or None
        normalized_payload = self._normalize_payload(
            request_type,
            order_payload,
            account=requested_account,
        )
        signer_private_key_override = str(order_payload.get("__agent_private_key", "")).strip() or None
        agent_wallet_override = str(order_payload.get("agent_wallet", "")).strip() or None
        request_header, signed_message = self._sign_request(
            request_type,
            normalized_payload,
            requested_account,
            signer_private_key_override=signer_private_key_override,
            agent_wallet_override=agent_wallet_override,
        )
        request = {**request_header, **normalized_payload}

        response = await self._http.post(
            self._build_endpoint_url(request_type),
            json=request,
            headers={"Content-Type": "application/json"},
        )
        response_json: dict[str, Any]
        try:
            response_json = response.json()
        except ValueError:
            response_json = {"success": False, "raw": response.text}

        if response.is_error or response_json.get("success") is False:
            detail = response_json.get("message") or response_json.get("error") or response.text
            raise PacificaClientError(f"Pacifica order request failed ({response.status_code}): {detail}", status_code=response.status_code)

        response_payload = self._extract_response_payload(response_json)
        client_order_id = normalized_payload.get("client_order_id")
        request_id = None
        if isinstance(response_payload, dict):
            request_id = (
                response_payload.get("request_id")
                or response_payload.get("order_id")
                or response_payload.get("client_order_id")
            )
        if request_id is None:
            request_id = str(client_order_id or uuid.uuid4())

        return {
            "status": "submitted",
            "request_id": str(request_id),
            "network": self.settings.pacifica_network,
            "payload": normalized_payload,
            "response": response_payload,
            "signed_message": signed_message,
        }

    async def place_batch_orders(self, order_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not order_payloads:
            return []
        actions: list[dict[str, Any]] = []
        normalized_payloads: list[dict[str, Any]] = []
        for order_payload in order_payloads:
            request_type = self._infer_request_type(order_payload)
            if request_type not in {"create_order", "cancel_order"}:
                raise PacificaClientError(f"Pacifica batch order request does not support {request_type}")
            requested_account = str(order_payload.get("account", "")).strip() or None
            normalized_payload = self._normalize_payload(
                request_type,
                order_payload,
                account=requested_account,
            )
            signer_private_key_override = str(order_payload.get("__agent_private_key", "")).strip() or None
            agent_wallet_override = str(order_payload.get("agent_wallet", "")).strip() or None
            request_header, signed_message = self._sign_request(
                request_type,
                normalized_payload,
                requested_account,
                signer_private_key_override=signer_private_key_override,
                agent_wallet_override=agent_wallet_override,
            )
            request = {**request_header, **normalized_payload}
            actions.append(
                {
                    "type": "Create" if request_type == "create_order" else "Cancel",
                    "data": request,
                }
            )
            normalized_payloads.append({**normalized_payload, "_signed_message": signed_message})

        await self._throttle(bucket="write")
        response = await self._http.post(
            f"{self.settings.pacifica_rest_url}/orders/batch",
            json={"actions": actions},
            headers={"Content-Type": "application/json"},
        )
        response_json: dict[str, Any]
        try:
            response_json = response.json()
        except ValueError:
            response_json = {"success": False, "raw": response.text}
        if response.is_error or response_json.get("success") is False:
            detail = response_json.get("message") or response_json.get("error") or response.text
            raise PacificaClientError(
                f"Pacifica batch order request failed ({response.status_code}): {detail}",
                status_code=response.status_code,
            )
        payload = self._extract_response_payload(response_json)
        results = payload.get("results") if isinstance(payload, dict) else payload
        if not isinstance(results, list):
            results = []

        responses: list[dict[str, Any]] = []
        for index, normalized_payload in enumerate(normalized_payloads):
            result = results[index] if index < len(results) and isinstance(results[index], dict) else {}
            request_id = (
                result.get("request_id")
                or result.get("order_id")
                or result.get("client_order_id")
                or normalized_payload.get("client_order_id")
                or str(uuid.uuid4())
            )
            responses.append(
                {
                    "status": "submitted",
                    "request_id": str(request_id),
                    "network": self.settings.pacifica_network,
                    "payload": {key: value for key, value in normalized_payload.items() if key != "_signed_message"},
                    "response": result,
                    "signed_message": normalized_payload.get("_signed_message"),
                }
            )
        return responses

    async def get_account_info(self, wallet_address: str) -> dict[str, Any]:
        await self._throttle(bucket="private")
        response = await self._http.get(
            f"{self.settings.pacifica_rest_url}/account",
            params={"account": wallet_address},
            headers={"Accept": "*/*"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return {"balance": 0.0, "equity": 0.0, "fee_level": 0}
            self._raise_http_error("account", exc)
        payload = self._extract_response_payload(response.json())
        if not isinstance(payload, dict):
            raise PacificaClientError("Pacifica account API returned an unexpected payload shape")
        balance = self._coerce_float(payload.get("balance"), 0.0)
        equity = self._coerce_float(
            payload.get("equity", payload.get("account_equity", payload.get("accountEquity"))),
            balance,
        )
        return {
            "balance": balance,
            "equity": equity,
            "fee_level": self._coerce_int(payload.get("feeLevel", payload.get("fee_level", 0)), 0),
        }

    async def get_account_settings(self, wallet_address: str) -> list[dict[str, Any]]:
        await self._throttle(bucket="private")
        response = await self._http.get(
            f"{self.settings.pacifica_rest_url}/account/settings",
            params={"account": wallet_address},
            headers={"Accept": "*/*"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            self._raise_http_error("account-settings", exc)

        payload = self._extract_response_payload(response.json())
        if not isinstance(payload, dict):
            raise PacificaClientError("Pacifica account settings API returned an unexpected payload shape")

        margin_settings = payload.get("margin_settings", payload.get("marginSettings"))
        if not isinstance(margin_settings, list):
            return []

        normalized_settings: list[dict[str, Any]] = []
        for item in margin_settings:
            if not isinstance(item, dict):
                continue
            symbol = item.get("symbol")
            if symbol is None:
                continue
            normalized_settings.append(
                {
                    "symbol": str(symbol),
                    "isolated": self._coerce_bool(item.get("isolated"), False),
                    "leverage": self._coerce_int(item.get("leverage"), 0),
                    "created_at": item.get("created_at") or item.get("createdAt"),
                    "updated_at": item.get("updated_at") or item.get("updatedAt"),
                }
            )
        return normalized_settings

    async def get_market_info(self) -> list[dict[str, Any]]:
        await self._throttle(bucket="public")
        info_response = await self._http.get(
            f"{self.settings.pacifica_rest_url}/info",
            headers={"Accept": "*/*"},
        )
        try:
            info_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._raise_http_error("market-info", exc)
        info_payload = self._extract_response_payload(info_response.json())
        if not isinstance(info_payload, list):
            raise PacificaClientError("Pacifica market-info API returned an unexpected payload shape")
        return [row for row in info_payload if isinstance(row, dict)]

    async def get_prices(self) -> list[dict[str, Any]]:
        await self._throttle(bucket="public")
        price_response = await self._http.get(
            f"{self.settings.pacifica_rest_url}/info/prices",
            headers={"Accept": "*/*"},
        )
        try:
            price_response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            self._raise_http_error("price-info", exc)
        price_payload = self._extract_response_payload(price_response.json())
        if not isinstance(price_payload, list):
            raise PacificaClientError("Pacifica price-info API returned an unexpected payload shape")
        prices: list[dict[str, Any]] = []
        for row in price_payload:
            if not isinstance(row, dict):
                continue
            symbol = row.get("symbol")
            if symbol is None:
                continue
            prices.append(
                {
                    "symbol": str(symbol),
                    "mark_price": self._coerce_float(row.get("mark", row.get("mid", row.get("oracle"))), 0.0),
                    "mid_price": self._coerce_float(row.get("mid"), 0.0),
                    "oracle_price": self._coerce_float(row.get("oracle"), 0.0),
                    "funding_rate": self._coerce_float(row.get("funding", row.get("funding_rate")), 0.0),
                    "next_funding_rate": self._coerce_float(row.get("next_funding", row.get("next_funding_rate")), 0.0),
                    "open_interest": self._coerce_float(row.get("open_interest", row.get("openInterest")), 0.0),
                    "volume_24h": self._coerce_float(row.get("volume_24h", row.get("volume24h")), 0.0),
                    "yesterday_price": self._coerce_float(row.get("yesterday_price", row.get("yesterdayPrice")), 0.0),
                    "updated_at": row.get("timestamp") or row.get("updated_at") or row.get("updatedAt"),
                }
            )
        return prices

    async def get_markets(self) -> list[dict[str, Any]]:
        info_payload, price_payload = await asyncio.gather(
            self.get_market_info(),
            self.get_prices(),
        )

        price_lookup: dict[str, dict[str, Any]] = {}
        for row in price_payload:
            symbol_key = str(row.get("symbol") or "")
            if not symbol_key:
                continue
            price_lookup[symbol_key] = row

        markets: list[dict[str, Any]] = []
        for row in info_payload:
            symbol = row.get("symbol")
            if symbol is None:
                continue
            symbol_key = str(symbol)
            live_price = price_lookup.get(symbol_key, {})
            markets.append(
                {
                    "symbol": symbol_key,
                    "display_symbol": f"{symbol}-PERP",
                    "mark_price": self._coerce_float(live_price.get("mark_price"), self._coerce_float(row.get("mark_price", row.get("markPrice")), 0.0)),
                    "mid_price": self._coerce_float(live_price.get("mid_price"), 0.0),
                    "oracle_price": self._coerce_float(live_price.get("oracle_price"), 0.0),
                    "funding_rate": self._coerce_float(live_price.get("funding_rate"), self._coerce_float(row.get("funding_rate", row.get("fundingRate")), 0.0)),
                    "next_funding_rate": self._coerce_float(live_price.get("next_funding_rate"), self._coerce_float(row.get("next_funding_rate", row.get("nextFundingRate")), 0.0)),
                    "min_order_size": self._coerce_float(row.get("min_order_size", row.get("minOrderSize")), 0.0),
                    "max_order_size": self._coerce_float(row.get("max_order_size", row.get("maxOrderSize")), 0.0),
                    "max_leverage": self._coerce_int(row.get("max_leverage", row.get("maxLeverage")), 0),
                    "isolated_only": self._coerce_bool(row.get("isolated_only", row.get("isolatedOnly")), False),
                    "tick_size": self._coerce_float(row.get("tick_size", row.get("tickSize")), 0.0),
                    "lot_size": self._coerce_float(row.get("lot_size", row.get("lotSize")), 0.0),
                    "open_interest": self._coerce_float(live_price.get("open_interest"), 0.0),
                    "volume_24h": self._coerce_float(live_price.get("volume_24h"), 0.0),
                    "yesterday_price": self._coerce_float(live_price.get("yesterday_price"), 0.0),
                    "updated_at": live_price.get("updated_at") or row.get("updated_at") or row.get("updatedAt") or row.get("created_at") or row.get("createdAt"),
                }
            )
        markets.sort(key=lambda item: item.get("volume_24h", 0), reverse=True)
        return markets

    async def get_kline(
        self,
        symbol: str,
        *,
        interval: str = "15m",
        start_time: int,
        end_time: int | None = None,
    ) -> list[dict[str, Any]]:
        await self._throttle(bucket="public")
        response = await self._http.get(
            f"{self.settings.pacifica_rest_url}/kline",
            params={
                "symbol": symbol,
                "interval": interval,
                "start_time": start_time,
                "end_time": end_time,
            },
            headers={"Accept": "*/*"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            self._raise_http_error("kline", exc)

        payload = self._extract_response_payload(response.json())
        if not isinstance(payload, list):
            raise PacificaClientError("Pacifica kline API returned an unexpected payload shape")

        candles: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            open_time = item.get("t") or item.get("open_time") or item.get("openTime")
            close_time = item.get("T") or item.get("close_time") or item.get("closeTime")
            if open_time is None or close_time is None:
                continue
            candles.append(
                {
                    "open_time": int(open_time),
                    "close_time": int(close_time),
                    "symbol": str(item.get("s") or item.get("symbol") or symbol),
                    "interval": str(item.get("i") or item.get("interval") or interval),
                    "open": self._coerce_float(item.get("o") or item.get("open"), 0.0),
                    "close": self._coerce_float(item.get("c") or item.get("close"), 0.0),
                    "high": self._coerce_float(item.get("h") or item.get("high"), 0.0),
                    "low": self._coerce_float(item.get("l") or item.get("low"), 0.0),
                    "volume": self._coerce_float(item.get("v") or item.get("volume"), 0.0),
                    "trade_count": self._coerce_int(item.get("n") or item.get("trade_count") or item.get("tradeCount"), 0),
                }
            )
        candles.sort(key=lambda item: item["open_time"])
        return candles

    async def get_portfolio_history(
        self,
        wallet_address: str,
        *,
        limit: int = 90,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        await self._throttle(bucket="private")
        response = await self._http.get(
            f"{self.settings.pacifica_rest_url}/portfolio",
            params={"account": wallet_address, "limit": limit, "offset": offset},
            headers={"Accept": "*/*"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            self._raise_http_error("portfolio-history", exc)
        payload = self._extract_response_payload(response.json())
        if not isinstance(payload, list):
            raise PacificaClientError("Pacifica portfolio API returned an unexpected payload shape")

        points: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            timestamp = item.get("timestamp")
            equity = item.get("account_equity") or item.get("accountEquity")
            if timestamp is None or equity is None:
                continue
            points.append({"timestamp": timestamp, "equity": float(equity)})
        points.sort(key=lambda item: str(item["timestamp"]))
        return points

    async def get_positions(
        self,
        wallet_address: str,
        *,
        price_lookup: dict[str, float] | None = None,
    ) -> list[dict[str, Any]]:
        await self._throttle(bucket="private")
        positions_url = self.settings.pacifica_positions_api_url or f"{self.settings.pacifica_rest_url}/positions"

        response = await self._http.get(
            positions_url,
            params={"account": wallet_address},
            headers={"Content-Type": "application/json"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            self._raise_http_error("positions", exc)
        response_json = response.json()
        payload = self._extract_response_payload(response_json)
        if not isinstance(payload, list):
            raise PacificaClientError("Pacifica positions API returned an unexpected payload shape")

        resolved_price_lookup = dict(price_lookup or {})
        if not resolved_price_lookup:
            prices = await self.get_prices()
            for row in prices:
                symbol = row.get("symbol")
                reference_price = row.get("mark_price") or row.get("mid_price") or row.get("oracle_price")
                if symbol in (None, "") or reference_price in (None, ""):
                    continue
                try:
                    resolved_price_lookup[str(symbol)] = float(reference_price)
                except (TypeError, ValueError):
                    continue

        positions: list[dict[str, Any]] = []
        for raw_position in payload:
            if not isinstance(raw_position, dict):
                continue
            amount = raw_position.get("amount") or raw_position.get("size") or raw_position.get("position_size")
            symbol = raw_position.get("symbol")
            side = raw_position.get("side")
            mark_price = raw_position.get("mark_price") or raw_position.get("markPrice") or resolved_price_lookup.get(str(symbol))
            entry_price = raw_position.get("entry_price") or raw_position.get("entryPrice")
            if amount is None or symbol is None or side is None or mark_price is None or entry_price is None:
                continue
            positions.append(
                {
                    "wallet": wallet_address,
                    "symbol": str(symbol),
                    "side": str(side),
                    "amount": float(amount),
                    "entry_price": float(entry_price),
                    "mark_price": float(mark_price),
                    "margin": float(raw_position.get("margin", 0) or 0),
                    "leverage": raw_position.get("leverage"),
                    "isolated": bool(raw_position.get("isolated", False)),
                    "created_at": raw_position.get("created_at") or raw_position.get("createdAt"),
                    "updated_at": raw_position.get("updated_at") or raw_position.get("updatedAt"),
                }
            )
        return positions

    async def get_open_orders(self, wallet_address: str) -> list[dict[str, Any]]:
        await self._throttle(bucket="private")
        response = await self._http.get(
            f"{self.settings.pacifica_rest_url}/orders",
            params={"account": wallet_address},
            headers={"Accept": "*/*"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            self._raise_http_error("open-orders", exc)
        response_json = response.json()
        payload = self._extract_response_payload(response_json)
        if not isinstance(payload, list):
            raise PacificaClientError("Pacifica open-orders API returned an unexpected payload shape")

        orders: list[dict[str, Any]] = []
        for raw_order in payload:
            if not isinstance(raw_order, dict):
                continue
            orders.append(
                {
                    "order_id": raw_order.get("order_id") or raw_order.get("orderId"),
                    "client_order_id": raw_order.get("client_order_id") or raw_order.get("clientOrderId"),
                    "symbol": raw_order.get("symbol"),
                    "side": raw_order.get("side"),
                    "price": raw_order.get("price") or raw_order.get("tickLevel"),
                    "initial_amount": raw_order.get("initial_amount") or raw_order.get("initialAmount"),
                    "filled_amount": raw_order.get("filled_amount") or raw_order.get("filledAmount"),
                    "cancelled_amount": raw_order.get("cancelled_amount") or raw_order.get("cancelledAmount"),
                    "remaining_amount": raw_order.get("remaining_amount") or raw_order.get("remainingAmount"),
                    "stop_price": raw_order.get("stop_price") or raw_order.get("stopTickLevel"),
                    "order_type": raw_order.get("order_type") or raw_order.get("orderType"),
                    "stop_parent_order_id": raw_order.get("stop_parent_order_id") or raw_order.get("stopParentOrderId"),
                    "reduce_only": raw_order.get("reduce_only") if raw_order.get("reduce_only") is not None else raw_order.get("reduceOnly"),
                    "created_at": raw_order.get("created_at") or raw_order.get("createdAt"),
                    "updated_at": raw_order.get("updated_at") or raw_order.get("updatedAt"),
                }
            )
        return orders

    async def get_position_history(
        self,
        wallet_address: str,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        await self._throttle(bucket="private")
        response = await self._http.get(
            f"{self.settings.pacifica_rest_url}/positions/history",
            params={"account": wallet_address, "limit": limit, "offset": offset},
            headers={"Accept": "*/*"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            self._raise_http_error("position-history", exc)
        payload = self._extract_response_payload(response.json())
        if not isinstance(payload, list):
            raise PacificaClientError("Pacifica position-history API returned an unexpected payload shape")

        history: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            history.append(
                {
                    "history_id": item.get("historyId") or item.get("history_id"),
                    "symbol": item.get("symbol"),
                    "amount": float(item.get("amount", 0) or 0),
                    "price": float(item.get("price", 0) or 0),
                    "entry_price": float(item.get("entryPrice", item.get("entry_price", 0)) or 0),
                    "fee": float(item.get("fee", 0) or 0),
                    "pnl": float(item.get("pnl", 0) or 0),
                    "is_maker": bool(item.get("isMaker", item.get("is_maker", False))),
                    "event_type": str(item.get("eventType", item.get("event_type", "")) or ""),
                    "created_at": item.get("createdAt") or item.get("created_at"),
                }
            )
        return history

    async def get_order_history_by_id(self, order_id: int) -> list[dict[str, Any]]:
        await self._throttle(bucket="private")
        response = await self._http.get(
            f"{self.settings.pacifica_rest_url}/orders/history_by_id",
            params={"order_id": order_id},
            headers={"Accept": "*/*"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                return []
            self._raise_http_error("order-history-by-id", exc)
        payload = self._extract_response_payload(response.json())
        if not isinstance(payload, list):
            raise PacificaClientError("Pacifica order-history-by-id API returned an unexpected payload shape")

        history: list[dict[str, Any]] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            history.append(
                {
                    "history_id": item.get("historyId") or item.get("history_id"),
                    "order_id": item.get("orderId") or item.get("order_id"),
                    "symbol": item.get("symbol"),
                    "side": item.get("side"),
                    "price": float(item.get("price", 0) or 0),
                    "amount": float(item.get("amount", 0) or 0),
                    "order_type": item.get("orderType") or item.get("order_type"),
                    "reduce_only": bool(item.get("reduceOnly", item.get("reduce_only", False))),
                    "event_type": str(item.get("eventType", item.get("event_type", "")) or ""),
                    "created_at": item.get("createdAt") or item.get("created_at"),
                }
            )
        return history
