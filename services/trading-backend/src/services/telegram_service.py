from __future__ import annotations

from datetime import UTC, datetime, timedelta
import logging
import secrets
import uuid
from typing import TYPE_CHECKING, Any

import httpx

from src.core.settings import Settings, get_settings
from src.services.bot_builder_service import BotBuilderService
from src.services.bot_runtime_snapshot_service import BotRuntimeSnapshotService
from src.services.supabase_rest import SupabaseRestClient
from src.services.trading_service import TradingService

if TYPE_CHECKING:
    from src.services.bot_copy_dashboard_service import BotCopyDashboardService

logger = logging.getLogger(__name__)

DEFAULT_NOTIFICATION_PREFS = {
    "critical_alerts": True,
    "execution_failures": True,
    "copy_activity": True,
}
TELEGRAM_API_BASE_URL = "https://api.telegram.org"
NOTIFICATION_PREFERENCE_BY_EVENT = {
    "bot.runtime.stopped": "critical_alerts",
    "bot.runtime.authorization_required": "critical_alerts",
    "portfolio.kill_switch": "critical_alerts",
    "bot.execution.failed": "execution_failures",
    "bot.copy.updated": "copy_activity",
}
BOT_COMMANDS = [
    {"command": "status", "description": "Get your fleet summary"},
    {"command": "bots", "description": "Review live bot health"},
    {"command": "positions", "description": "See open positions"},
    {"command": "copy", "description": "Check copy trading"},
    {"command": "help", "description": "Show available commands"},
    {"command": "disconnect", "description": "Unlink this chat"},
]


class TelegramRateLimitError(RuntimeError):
    def __init__(self, *, method: str, retry_after_seconds: int | None, description: str | None = None) -> None:
        retry_hint = f" retry_after={retry_after_seconds}s" if retry_after_seconds is not None else ""
        super().__init__(f"Telegram API rate limited for {method}.{retry_hint}".rstrip())
        self.method = method
        self.retry_after_seconds = retry_after_seconds
        self.description = description or "Too Many Requests"


class TelegramService:
    def __init__(
        self,
        *,
        supabase: SupabaseRestClient | None = None,
        bot_builder_service: BotBuilderService | None = None,
        snapshot_service: BotRuntimeSnapshotService | None = None,
        trading_service: TradingService | None = None,
        copy_dashboard_service: BotCopyDashboardService | None = None,
    ) -> None:
        self._supabase = supabase or SupabaseRestClient()
        self._bot_builder_service = bot_builder_service
        self._snapshot_service = snapshot_service
        self._trading_service = trading_service
        self._copy_dashboard_service = copy_dashboard_service

    @property
    def _builder(self) -> BotBuilderService:
        if self._bot_builder_service is None:
            self._bot_builder_service = BotBuilderService()
        return self._bot_builder_service

    @property
    def _snapshots(self) -> BotRuntimeSnapshotService:
        if self._snapshot_service is None:
            self._snapshot_service = BotRuntimeSnapshotService()
        return self._snapshot_service

    @property
    def _trading(self) -> TradingService:
        if self._trading_service is None:
            self._trading_service = TradingService()
        return self._trading_service

    @property
    def _copy_dashboard(self) -> "BotCopyDashboardService":
        if self._copy_dashboard_service is None:
            from src.services.bot_copy_dashboard_service import BotCopyDashboardService

            self._copy_dashboard_service = BotCopyDashboardService()
        return self._copy_dashboard_service

    def get_connection_status(self, *, wallet_address: str) -> dict[str, Any]:
        settings = get_settings()
        user = self._ensure_user(wallet_address)
        prefs = self._resolved_notification_prefs(user.get("telegram_notification_prefs"))
        deeplink_url = None
        link_expires_at = self._parse_datetime(user.get("telegram_link_code_expires_at"))
        link_code = str(user.get("telegram_link_code") or "").strip()
        if link_code and link_expires_at and link_expires_at > datetime.now(tz=UTC):
            deeplink_url = self.build_bot_link(start_param=f"connect_{link_code}", settings=settings)

        return {
            "wallet_address": wallet_address,
            "bot_username": settings.telegram_bot_username or None,
            "bot_link": self.build_bot_link(settings=settings),
            "deeplink_url": deeplink_url,
            "link_expires_at": link_expires_at,
            "connected": bool(user.get("telegram_chat_id")),
            "telegram_username": user.get("telegram_username"),
            "telegram_first_name": user.get("telegram_first_name"),
            "chat_label": self._chat_label(user.get("telegram_chat_id"), user.get("telegram_chat_type")),
            "connected_at": self._parse_datetime(user.get("telegram_connected_at")),
            "last_interaction_at": self._parse_datetime(user.get("telegram_last_interaction_at")),
            "notifications_enabled": bool(user.get("telegram_notifications_enabled", True)),
            "notification_prefs": prefs,
            "token_configured": bool(settings.telegram_bot_token),
            "webhook_url_configured": bool(settings.telegram_webhook_url),
            "webhook_secret_configured": bool(settings.telegram_webhook_secret),
            "webhook_ready": bool(settings.telegram_bot_token and settings.telegram_webhook_url),
            "commands": list(BOT_COMMANDS),
        }

    def issue_link_code(self, *, wallet_address: str) -> dict[str, Any]:
        settings = get_settings()
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not configured on the backend.")
        user = self._ensure_user(wallet_address)
        expires_at = datetime.now(tz=UTC) + timedelta(minutes=settings.telegram_link_code_ttl_minutes)
        link_code = secrets.token_urlsafe(24)
        self._supabase.update(
            "users",
            {
                "telegram_link_code": link_code,
                "telegram_link_code_expires_at": expires_at.isoformat(),
            },
            filters={"id": user["id"]},
            returning="minimal",
        )
        return self.get_connection_status(wallet_address=wallet_address)

    def update_preferences(
        self,
        *,
        wallet_address: str,
        notifications_enabled: bool | None,
        preference_overrides: dict[str, bool],
    ) -> dict[str, Any]:
        user = self._ensure_user(wallet_address)
        next_prefs = self._resolved_notification_prefs(user.get("telegram_notification_prefs"))
        for key, value in preference_overrides.items():
            if key in next_prefs:
                next_prefs[key] = bool(value)
        values: dict[str, Any] = {"telegram_notification_prefs": next_prefs}
        if notifications_enabled is not None:
            values["telegram_notifications_enabled"] = bool(notifications_enabled)
        self._supabase.update("users", values, filters={"id": user["id"]}, returning="minimal")
        return self.get_connection_status(wallet_address=wallet_address)

    async def disconnect_wallet(self, *, wallet_address: str, notify_chat: bool = False) -> dict[str, Any]:
        user = self._ensure_user(wallet_address)
        chat_id = user.get("telegram_chat_id")
        if notify_chat and chat_id:
            await self._send_message(
                chat_id=int(chat_id),
                text="ClashX Telegram delivery is now disconnected for this wallet. Reconnect from the Telegram desk any time.",
            )
        self._clear_connection(user_id=str(user["id"]))
        return self.get_connection_status(wallet_address=wallet_address)

    async def send_test_message(self, *, wallet_address: str) -> dict[str, Any]:
        user = self._ensure_user(wallet_address)
        chat_id = user.get("telegram_chat_id")
        if not chat_id:
            raise ValueError("Telegram is not connected for this wallet yet.")
        summary = self._build_status_message(wallet_address=wallet_address)
        await self._send_message(
            chat_id=int(chat_id),
            text=(
                "ClashX test ping\n\n"
                "Telegram delivery is live for this wallet.\n"
                f"{summary}"
            ),
        )
        return self.get_connection_status(wallet_address=wallet_address)

    async def configure_bot(self, *, settings: Settings | None = None) -> None:
        resolved_settings = settings or get_settings()
        if not resolved_settings.telegram_bot_token:
            return
        try:
            await self._telegram_request("setMyCommands", {"commands": BOT_COMMANDS}, settings=resolved_settings)
            if resolved_settings.telegram_webhook_url:
                webhook_info = await self._telegram_request("getWebhookInfo", {}, settings=resolved_settings)
                configured_url = str(webhook_info.get("url") or "").strip()
                desired_url = str(resolved_settings.telegram_webhook_url).strip()
                if configured_url != desired_url:
                    payload: dict[str, Any] = {
                        "url": desired_url,
                        "allowed_updates": ["message"],
                    }
                    if resolved_settings.telegram_webhook_secret:
                        payload["secret_token"] = resolved_settings.telegram_webhook_secret
                    await self._telegram_request("setWebhook", payload, settings=resolved_settings)
        except TelegramRateLimitError as exc:
            logger.warning(
                "Telegram bot configuration rate limited for %s; retry_after=%s description=%s",
                exc.method,
                exc.retry_after_seconds,
                exc.description,
            )
        except Exception:
            logger.exception("Telegram bot configuration failed")

    async def handle_webhook(self, *, update: dict[str, Any], secret_token: str | None) -> None:
        settings = get_settings()
        expected_secret = settings.telegram_webhook_secret
        if expected_secret and secret_token != expected_secret:
            raise PermissionError("Invalid Telegram webhook secret")

        message = update.get("message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        from_user = message.get("from") if isinstance(message.get("from"), dict) else {}
        chat_id = chat.get("id")
        if chat.get("type") != "private" or not isinstance(chat_id, int):
            return

        text = str(message.get("text") or "").strip()
        if not text:
            await self._send_message(chat_id=chat_id, text="Use /help to see what this bot can do.")
            return

        command, _, argument = text.partition(" ")
        normalized_command = command.split("@", 1)[0].lower()
        linked_user = self._user_by_chat_id(chat_id)
        if linked_user is not None:
            self._touch_linked_chat(chat_id=chat_id, from_user=from_user)

        if normalized_command == "/start":
            await self._handle_start(chat_id=chat_id, from_user=from_user, argument=argument.strip())
            return
        if normalized_command in {"/help", "help"}:
            await self._send_message(chat_id=chat_id, text=self._help_message(linked=linked_user is not None))
            return
        if normalized_command in {"/disconnect", "disconnect"}:
            await self._handle_disconnect(chat_id=chat_id, linked_user=linked_user)
            return
        if linked_user is None:
            await self._send_message(chat_id=chat_id, text=self._unlinked_message())
            return

        wallet_address = str(linked_user.get("wallet_address") or "").strip()
        if normalized_command in {"/status", "status"}:
            await self._send_message(chat_id=chat_id, text=self._build_status_message(wallet_address=wallet_address))
            return
        if normalized_command in {"/bots", "bots"}:
            await self._send_message(chat_id=chat_id, text=self._build_bots_message(wallet_address=wallet_address))
            return
        if normalized_command in {"/positions", "positions"}:
            await self._send_message(chat_id=chat_id, text=await self._build_positions_message(wallet_address=wallet_address))
            return
        if normalized_command in {"/copy", "copy"}:
            await self._send_message(chat_id=chat_id, text=await self._build_copy_message(wallet_address=wallet_address))
            return

        await self._send_message(chat_id=chat_id, text=self._help_message(linked=True))

    async def notify_user(self, *, user_id: str, event: str, payload: dict[str, Any]) -> bool:
        user = self._supabase.maybe_one(
            "users",
            columns=(
                "id,wallet_address,telegram_chat_id,telegram_chat_type,telegram_username,"
                "telegram_notifications_enabled,telegram_notification_prefs"
            ),
            filters={"id": user_id},
            cache_ttl_seconds=5,
        )
        if user is None or not user.get("telegram_chat_id") or not user.get("telegram_notifications_enabled", True):
            return False
        preference_key = NOTIFICATION_PREFERENCE_BY_EVENT.get(event)
        prefs = self._resolved_notification_prefs(user.get("telegram_notification_prefs"))
        if preference_key and not prefs.get(preference_key, False):
            return False
        rendered = self._render_notification_message(event=event, payload=payload)
        if not rendered:
            return False
        await self._send_message(chat_id=int(user["telegram_chat_id"]), text=rendered)
        return True

    def build_bot_link(self, *, start_param: str | None = None, settings: Settings | None = None) -> str:
        resolved_settings = settings or get_settings()
        username = str(resolved_settings.telegram_bot_username or "").strip().lstrip("@")
        base = f"https://t.me/{username}" if username else "https://t.me"
        if start_param:
            return f"{base}?start={start_param}"
        return base

    def _ensure_user(self, wallet_address: str) -> dict[str, Any]:
        normalized_wallet = str(wallet_address or "").strip()
        if not normalized_wallet:
            raise ValueError("Wallet address is required")
        existing = self._supabase.maybe_one("users", filters={"wallet_address": normalized_wallet})
        if existing is not None:
            return existing
        return self._supabase.insert(
            "users",
            {
                "id": str(uuid.uuid4()),
                "wallet_address": normalized_wallet,
                "display_name": normalized_wallet[:8],
                "auth_provider": "privy",
                "created_at": datetime.now(tz=UTC).isoformat(),
            },
            upsert=True,
            on_conflict="wallet_address",
        )[0]

    def _user_by_chat_id(self, chat_id: int) -> dict[str, Any] | None:
        return self._supabase.maybe_one("users", filters={"telegram_chat_id": chat_id}, cache_ttl_seconds=5)

    def _touch_linked_chat(self, *, chat_id: int, from_user: dict[str, Any]) -> None:
        self._supabase.update(
            "users",
            {
                "telegram_username": from_user.get("username"),
                "telegram_first_name": from_user.get("first_name"),
                "telegram_last_interaction_at": datetime.now(tz=UTC).isoformat(),
            },
            filters={"telegram_chat_id": chat_id},
            returning="minimal",
        )

    async def _handle_start(self, *, chat_id: int, from_user: dict[str, Any], argument: str) -> None:
        if argument.startswith("connect_"):
            token = argument.removeprefix("connect_").strip()
            linked_wallet = self._connect_chat_from_token(chat_id=chat_id, from_user=from_user, token=token)
            if linked_wallet is None:
                await self._send_message(
                    chat_id=chat_id,
                    text=(
                        "That link is missing or expired.\n"
                        "Open the Telegram desk in ClashX and generate a fresh secure link."
                    ),
                )
                return
            await self._send_message(
                chat_id=chat_id,
                text=(
                    f"ClashX Telegram is linked to {self._short_wallet(linked_wallet)}.\n\n"
                    f"{self._help_message(linked=True)}"
                ),
            )
            return
        await self._send_message(chat_id=chat_id, text=self._help_message(linked=self._user_by_chat_id(chat_id) is not None))

    async def _handle_disconnect(self, *, chat_id: int, linked_user: dict[str, Any] | None) -> None:
        if linked_user is None:
            await self._send_message(chat_id=chat_id, text="No ClashX wallet is linked to this chat right now.")
            return
        self._clear_connection(user_id=str(linked_user["id"]))
        await self._send_message(
            chat_id=chat_id,
            text="This chat is no longer linked to ClashX. Reconnect from the Telegram desk whenever you want alerts again.",
        )

    def _connect_chat_from_token(self, *, chat_id: int, from_user: dict[str, Any], token: str) -> str | None:
        if not token:
            return None
        users = self._supabase.select(
            "users",
            filters={"telegram_link_code": token},
            limit=1,
        )
        if not users:
            return None
        user = users[0]
        expires_at = self._parse_datetime(user.get("telegram_link_code_expires_at"))
        if expires_at is None or expires_at <= datetime.now(tz=UTC):
            return None

        existing_for_chat = self._user_by_chat_id(chat_id)
        if existing_for_chat is not None and str(existing_for_chat.get("id")) != str(user.get("id")):
            self._clear_connection(user_id=str(existing_for_chat["id"]))

        now = datetime.now(tz=UTC).isoformat()
        self._supabase.update(
            "users",
            {
                "telegram_chat_id": chat_id,
                "telegram_chat_type": "private",
                "telegram_username": from_user.get("username"),
                "telegram_first_name": from_user.get("first_name"),
                "telegram_connected_at": now,
                "telegram_last_interaction_at": now,
                "telegram_link_code": None,
                "telegram_link_code_expires_at": None,
                "telegram_notifications_enabled": True,
            },
            filters={"id": user["id"]},
            returning="minimal",
        )
        return str(user.get("wallet_address") or "").strip()

    def _clear_connection(self, *, user_id: str) -> None:
        self._supabase.update(
            "users",
            {
                "telegram_chat_id": None,
                "telegram_chat_type": None,
                "telegram_username": None,
                "telegram_first_name": None,
                "telegram_connected_at": None,
                "telegram_link_code": None,
                "telegram_link_code_expires_at": None,
            },
            filters={"id": user_id},
            returning="minimal",
        )

    def _build_status_message(self, *, wallet_address: str) -> str:
        definitions = self._builder.list_bots(None, wallet_address=wallet_address)
        snapshots = self._snapshots.list_snapshots_for_wallet(wallet_address)
        active = 0
        paused = 0
        stopped = 0
        draft = 0
        attention = 0
        total_pnl = 0.0
        for bot in definitions:
            snapshot = snapshots.get(str(bot.get("id") or "").strip()) or {}
            status = str(snapshot.get("status") or "draft").strip()
            performance = snapshot.get("performance_json") if isinstance(snapshot.get("performance_json"), dict) else {}
            health = snapshot.get("health_json") if isinstance(snapshot.get("health_json"), dict) else {}
            total_pnl += self._to_float(performance.get("pnl_total"))
            if status == "active":
                active += 1
            elif status == "paused":
                paused += 1
            elif status == "stopped":
                stopped += 1
            else:
                draft += 1
            if health and (
                str(health.get("health") or "") not in {"", "healthy"}
                or int(self._to_float(((snapshot.get("metrics_json") or {}) if isinstance(snapshot.get("metrics_json"), dict) else {}).get("actions_error"))) > 0
            ):
                attention += 1

        lines = [
            "ClashX control tower",
            f"Wallet: {self._short_wallet(wallet_address)}",
            f"Bots: {len(definitions)} total | {active} active | {paused} paused | {stopped} stopped | {draft} draft",
            f"Fleet PnL: {self._format_signed_usd(total_pnl)}",
            f"Needs attention: {attention}",
        ]
        lines.append("Use /bots, /positions, or /copy for detail.")
        return "\n".join(lines)

    def _build_bots_message(self, *, wallet_address: str) -> str:
        definitions = self._builder.list_bots(None, wallet_address=wallet_address)[:8]
        if not definitions:
            return "No bots are saved for this wallet yet."
        snapshots = self._snapshots.list_snapshots_for_wallet(wallet_address)
        lines = ["ClashX bot board"]
        for bot in definitions:
            snapshot = snapshots.get(str(bot.get("id") or "").strip()) or {}
            status = str(snapshot.get("status") or "draft").strip() or "draft"
            health = (
                str(((snapshot.get("health_json") or {}) if isinstance(snapshot.get("health_json"), dict) else {}).get("health") or "")
                or "n/a"
            )
            pnl = self._to_float(
                ((snapshot.get("performance_json") or {}) if isinstance(snapshot.get("performance_json"), dict) else {}).get("pnl_total")
            )
            lines.append(f"- {bot['name']} | {status} | {health} | {self._format_signed_usd(pnl)}")
        return "\n".join(lines)

    async def _build_positions_message(self, *, wallet_address: str) -> str:
        try:
            snapshot = await self._trading.get_account_snapshot(None, wallet_address)
        except Exception:
            return "Live positions are unavailable right now. Check Pacifica authorization and try again."
        positions = snapshot.get("positions") if isinstance(snapshot.get("positions"), list) else []
        if not positions:
            return "No live positions are open right now."
        lines = ["Open positions"]
        sorted_positions = sorted(
            positions,
            key=lambda item: abs(self._to_float(item.get("unrealized_pnl"))),
            reverse=True,
        )[:6]
        for position in sorted_positions:
            symbol = str(position.get("symbol") or "").upper()
            side = str(position.get("side") or "").lower()
            quantity = self._to_float(position.get("quantity") or position.get("amount"))
            pnl = self._to_float(position.get("unrealized_pnl"))
            lines.append(f"- {symbol} {side} | {quantity:.4f} | {self._format_signed_usd(pnl)}")
        return "\n".join(lines)

    async def _build_copy_message(self, *, wallet_address: str) -> str:
        try:
            dashboard = await self._copy_dashboard.get_dashboard(wallet_address=wallet_address)
        except Exception:
            return "Copy trading detail is unavailable right now."
        summary = dashboard.get("summary") if isinstance(dashboard.get("summary"), dict) else {}
        alerts = dashboard.get("alerts") if isinstance(dashboard.get("alerts"), list) else []
        lines = [
            "Copy trading desk",
            f"Active follows: {int(self._to_float(summary.get('active_follows')))}",
            f"Open positions: {int(self._to_float(summary.get('open_positions')))}",
            f"Open notional: ${self._to_float(summary.get('copied_open_notional_usd')):.2f}",
            f"Live PnL: {self._format_signed_usd(self._to_float(summary.get('copied_unrealized_pnl_usd')))}",
        ]
        if alerts:
            top_alert = alerts[0] if isinstance(alerts[0], dict) else {}
            lines.append(f"Top alert: {str(top_alert.get('title') or 'Attention required')}")
        return "\n".join(lines)

    def _help_message(self, *, linked: bool) -> str:
        lines = ["ClashX Telegram desk"]
        if linked:
            lines.append("This chat is linked and ready.")
        else:
            lines.append("Link this chat from the ClashX Telegram desk to unlock account-specific commands.")
        lines.extend(
            [
                "",
                "/status - fleet summary",
                "/bots - runtime board",
                "/positions - open positions",
                "/copy - copy trading snapshot",
                "/help - command list",
                "/disconnect - unlink this chat",
            ]
        )
        return "\n".join(lines)

    def _unlinked_message(self) -> str:
        return (
            "This chat is not linked to a ClashX wallet yet.\n"
            "Open the Telegram page in ClashX, generate a secure link, then tap Start from that link."
        )

    def _render_notification_message(self, *, event: str, payload: dict[str, Any]) -> str | None:
        if event == "bot.runtime.stopped":
            bot_name = self._resolve_runtime_bot_name(str(payload.get("runtime_id") or ""))
            reason = str(payload.get("error_reason") or "Risk policy breach")
            return f"Critical runtime alert\n{bot_name} stopped.\nReason: {reason}"
        if event == "bot.runtime.authorization_required":
            bot_name = self._resolve_bot_name(str(payload.get("bot_id") or ""))
            return f"Critical runtime alert\n{bot_name} is paused because delegated Pacifica authorization is missing."
        if event == "portfolio.kill_switch":
            if not payload.get("engaged", False):
                return None
            reason = str(payload.get("reason") or "Portfolio risk policy breach")
            return f"Critical portfolio alert\nKill switch engaged.\nReason: {reason}"
        if event == "bot.execution.failed":
            request_payload = payload.get("request_payload") if isinstance(payload.get("request_payload"), dict) else {}
            bot_name = self._resolve_runtime_bot_name(str(payload.get("runtime_id") or ""))
            action_type = str(request_payload.get("type") or "action").replace("_", " ")
            symbol = str(request_payload.get("symbol") or "").upper()
            detail = str(payload.get("error_reason") or "Execution failed.")
            subject = f"{bot_name} failed {action_type}".strip()
            if symbol:
                subject = f"{subject} on {symbol}"
            return f"Execution failure\n{subject}\nReason: {detail}"
        if event == "bot.copy.updated":
            status = str(payload.get("status") or "updated")
            scale_bps = int(self._to_float(payload.get("scale_bps")))
            return f"Copy trading update\nRelationship status: {status}\nScale: {scale_bps} bps"
        return None

    def _resolve_runtime_bot_name(self, runtime_id: str) -> str:
        runtime = self._supabase.maybe_one(
            "bot_runtimes",
            columns="id,bot_definition_id",
            filters={"id": runtime_id},
            cache_ttl_seconds=15,
        )
        if runtime is None:
            return "Runtime"
        return self._resolve_bot_name(str(runtime.get("bot_definition_id") or ""))

    def _resolve_bot_name(self, bot_id: str) -> str:
        if not bot_id:
            return "Bot"
        bot = self._supabase.maybe_one(
            "bot_definitions",
            columns="name",
            filters={"id": bot_id},
            cache_ttl_seconds=15,
        )
        return str((bot or {}).get("name") or "Bot")

    async def _send_message(self, *, chat_id: int, text: str) -> None:
        settings = get_settings()
        if not settings.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not configured on the backend.")
        await self._telegram_request(
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": text[:4000],
                "disable_web_page_preview": True,
            },
            settings=settings,
        )

    async def _telegram_request(self, method: str, payload: dict[str, Any], *, settings: Settings) -> dict[str, Any]:
        async with httpx.AsyncClient(base_url=TELEGRAM_API_BASE_URL, timeout=15) as client:
            response = await client.post(
                f"/bot{settings.telegram_bot_token}/{method}",
                json=payload,
            )
        try:
            data = response.json()
        except ValueError:
            data = {}
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if response.status_code == 429:
                parameters = data.get("parameters") if isinstance(data, dict) and isinstance(data.get("parameters"), dict) else {}
                retry_after = parameters.get("retry_after")
                raise TelegramRateLimitError(
                    method=method,
                    retry_after_seconds=int(retry_after) if retry_after not in (None, "") else None,
                    description=(data.get("description") if isinstance(data, dict) else None),
                ) from exc
            raise
        if not isinstance(data, dict) or not data.get("ok"):
            description = (data or {}).get("description") if isinstance(data, dict) else None
            raise RuntimeError(f"Telegram API request failed: {description or 'unknown error'}")
        result = data.get("result")
        return result if isinstance(result, dict) else {"result": result}

    @staticmethod
    def _resolved_notification_prefs(raw_value: Any) -> dict[str, bool]:
        resolved = dict(DEFAULT_NOTIFICATION_PREFS)
        if isinstance(raw_value, dict):
            for key in resolved:
                if key in raw_value:
                    resolved[key] = bool(raw_value[key])
        return resolved

    @staticmethod
    def _parse_datetime(value: Any) -> datetime | None:
        if value in (None, ""):
            return None
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)

    @staticmethod
    def _to_float(value: Any) -> float:
        try:
            if value in (None, ""):
                return 0.0
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _format_signed_usd(value: float) -> str:
        absolute = abs(float(value))
        sign = "+" if value >= 0 else "-"
        return f"{sign}${absolute:.2f}"

    @staticmethod
    def _short_wallet(wallet_address: str) -> str:
        normalized = str(wallet_address or "").strip()
        if len(normalized) <= 10:
            return normalized
        return f"{normalized[:4]}...{normalized[-4:]}"

    @staticmethod
    def _chat_label(chat_id: Any, chat_type: Any) -> str | None:
        if chat_id in (None, ""):
            return None
        return f"{str(chat_type or 'private').title()} chat {str(chat_id)[-5:]}"
