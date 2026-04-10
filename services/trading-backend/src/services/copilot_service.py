from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from src.api.auth import AuthenticatedUser
from src.core.settings import get_settings
from src.services.ai_response_json import extract_first_json_object
from src.services.bot_builder_service import BotBuilderService
from src.services.bot_runtime_engine import BotRuntimeEngine
from src.services.creator_marketplace_service import CreatorMarketplaceService
from src.services.pacifica_auth_service import PacificaAuthService
from src.services.pacifica_readiness_service import PacificaReadinessService
from src.services.portfolio_allocator_service import PortfolioAllocatorService
from src.services.runtime_observability_service import RuntimeObservabilityService
from src.services.supabase_rest import SupabaseRestClient
from src.services.trading_service import TradingService


@dataclass(frozen=True)
class _ProviderAttempt:
    name: str
    request_coro: Any


class CopilotService:
    _ALLOWED_QUERY_TABLES = {
        "audit_events",
        "bot_backtest_runs",
        "bot_copy_relationships",
        "bot_definitions",
        "bot_execution_events",
        "bot_invite_access",
        "bot_publish_snapshots",
        "bot_publishing_settings",
        "bot_runtimes",
        "bot_strategy_versions",
        "bot_trade_closures",
        "bot_trade_lots",
        "bot_trade_sync_state",
        "copilot_conversations",
        "copilot_messages",
        "creator_marketplace_profiles",
        "featured_bots",
        "pacifica_authorizations",
        "portfolio_allocation_members",
        "portfolio_baskets",
        "portfolio_rebalance_events",
        "portfolio_risk_policies",
        "users",
    }
    _PUBLIC_QUERY_TABLES = {
        "creator_marketplace_profiles",
        "featured_bots",
    }
    _DIRECT_WALLET_TABLES = {
        "bot_backtest_runs",
        "bot_copy_relationships",
        "bot_definitions",
        "bot_runtimes",
        "copilot_conversations",
        "portfolio_baskets",
    }
    _CONVERSATION_SCOPED_TABLES = {
        "copilot_messages",
    }
    _BOT_SCOPED_TABLES = {
        "bot_invite_access",
        "bot_publish_snapshots",
        "bot_publishing_settings",
        "bot_strategy_versions",
    }
    _RUNTIME_SCOPED_TABLES = {
        "bot_execution_events",
        "bot_trade_closures",
        "bot_trade_lots",
        "bot_trade_sync_state",
    }
    _PORTFOLIO_SCOPED_TABLES = {
        "portfolio_allocation_members",
        "portfolio_rebalance_events",
        "portfolio_risk_policies",
    }
    _TOOL_NAMES = (
        "get_linked_wallets",
        "list_bots",
        "get_bot",
        "get_runtime_overview",
        "get_bot_events",
        "get_trading_account",
        "list_portfolios",
        "get_portfolio",
        "get_pacifica_authorization",
        "get_pacifica_readiness",
        "get_marketplace_overview",
        "list_schema_tables",
        "describe_schema_table",
        "query_database",
    )

    def __init__(self) -> None:
        self.settings = get_settings()
        self._http = httpx.AsyncClient(timeout=60.0)
        self._supabase = SupabaseRestClient()
        self._bot_builder = BotBuilderService()
        self._bot_runtime = BotRuntimeEngine()
        self._runtime_observability = RuntimeObservabilityService()
        self._trading = TradingService()
        self._portfolio_allocator = PortfolioAllocatorService()
        self._pacifica_auth = PacificaAuthService()
        self._pacifica_readiness = PacificaReadinessService()
        self._marketplace = CreatorMarketplaceService()
        self._schema_definitions = self._load_schema_definitions()

    async def chat(
        self,
        *,
        messages: list[dict[str, str]],
        user: AuthenticatedUser,
        wallet_address: str | None,
    ) -> dict[str, Any]:
        attempts = self._build_provider_attempts(messages=messages, user=user, wallet_address=wallet_address)
        if not attempts:
            raise RuntimeError(
                "Missing Gemini and OpenAI configuration. Set GEMINI_API_KEY, GEMINI_BASE_URL, and GEMINI_MODEL "
                "or OPENAI_API_KEY, OPENAI_BASE_URL, and OPENAI_MODEL."
            )

        errors: list[str] = []
        for attempt in attempts:
            try:
                result = await attempt.request_coro()
                return {"provider": attempt.name, **result}
            except RuntimeError as exc:
                errors.append(f"{attempt.name}: {exc}")
        raise RuntimeError("; ".join(errors))

    async def summarize_history(
        self,
        *,
        existing_summary: str,
        messages: list[dict[str, str]],
    ) -> str:
        conversation_lines: list[str] = []
        for message in messages:
            role = str(message.get("role") or "").strip()
            content = str(message.get("content") or "").strip()
            if role not in {"user", "assistant"} or not content:
                continue
            conversation_lines.append(f"{role.upper()}: {content}")
        if not conversation_lines:
            return existing_summary.strip()

        system_prompt = "\n".join(
            [
                "You compress earlier ClashX Copilot chat history for future assistant turns.",
                "Return plain text only. No JSON. No markdown tables.",
                "Keep the summary compact but specific.",
                "Preserve user goals, wallet or bot identifiers, concrete factual findings, unresolved questions, and action items.",
                "Prefer exact names, ids, counts, and timestamps when present.",
                "Do not invent facts that were not present in the conversation.",
                "Write no more than 1200 words.",
            ]
        )
        request_messages = [
            {
                "role": "user",
                "content": "\n".join(
                    [
                        "Existing rolling summary:",
                        existing_summary.strip() or "(none)",
                        "",
                        "Newer conversation turns to merge into the summary:",
                        "\n".join(conversation_lines),
                    ]
                ).strip(),
            }
        ]
        attempts = self._build_text_attempts(messages=request_messages, system_prompt=system_prompt)
        if not attempts:
            raise RuntimeError(
                "Missing Gemini and OpenAI configuration. Set GEMINI_API_KEY, GEMINI_BASE_URL, and GEMINI_MODEL "
                "or OPENAI_API_KEY, OPENAI_BASE_URL, and OPENAI_MODEL."
            )

        errors: list[str] = []
        for attempt in attempts:
            try:
                text = (await attempt.request_coro()).strip()
                if text:
                    return text
                raise RuntimeError("Summary response was empty")
            except RuntimeError as exc:
                errors.append(f"{attempt.name}: {exc}")
        raise RuntimeError("; ".join(errors))

    def _build_provider_attempts(
        self,
        *,
        messages: list[dict[str, str]],
        user: AuthenticatedUser,
        wallet_address: str | None,
    ) -> list[_ProviderAttempt]:
        system_prompt = self._build_system_prompt(user=user, wallet_address=wallet_address)
        attempts: list[_ProviderAttempt] = []
        if self._has_gemini_config():
            attempts.append(
                _ProviderAttempt(
                    name="Gemini",
                    request_coro=lambda: self._run_conversation(
                        messages=messages,
                        user=user,
                        wallet_address=wallet_address,
                        request_model=lambda conversation: self._request_gemini(conversation, system_prompt),
                    ),
                )
            )
        if self._has_openai_config():
            attempts.append(
                _ProviderAttempt(
                    name="OpenAI",
                    request_coro=lambda: self._run_conversation(
                        messages=messages,
                        user=user,
                        wallet_address=wallet_address,
                        request_model=lambda conversation: self._request_openai(conversation, system_prompt),
                    ),
                )
            )
        return attempts

    def _build_text_attempts(
        self,
        *,
        messages: list[dict[str, str]],
        system_prompt: str,
    ) -> list[_ProviderAttempt]:
        attempts: list[_ProviderAttempt] = []
        if self._has_gemini_config():
            attempts.append(
                _ProviderAttempt(
                    name="Gemini",
                    request_coro=lambda: self._request_gemini(messages, system_prompt),
                )
            )
        if self._has_openai_config():
            attempts.append(
                _ProviderAttempt(
                    name="OpenAI",
                    request_coro=lambda: self._request_openai(messages, system_prompt),
                )
            )
        return attempts

    async def _run_conversation(
        self,
        *,
        messages: list[dict[str, str]],
        user: AuthenticatedUser,
        wallet_address: str | None,
        request_model: Any,
    ) -> dict[str, Any]:
        conversation: list[dict[str, str]] = []
        for message in messages:
            sanitized = self._sanitize_message(message)
            if sanitized is not None:
                conversation.append(sanitized)
        if not conversation:
            raise RuntimeError("At least one chat message is required")

        tool_traces: list[dict[str, Any]] = []
        scope_cache: dict[str, Any] = {}
        for _ in range(6):
            raw_text = await request_model(conversation)
            payload = self._normalize_response_payload(self._extract_json(raw_text))

            if payload.get("type") == "final":
                reply = str(payload.get("reply") or "").strip()
                if not reply:
                    raise RuntimeError("AI final response was empty")
                return {
                    "reply": reply,
                    "followUps": self._sanitize_follow_ups(payload.get("followUps") or payload.get("follow_ups")),
                    "toolCalls": tool_traces,
                    "usedWalletAddress": scope_cache.get("default_wallet_address")
                    or wallet_address
                    or (user.wallet_addresses[0] if user.wallet_addresses else None),
                }

            if payload.get("type") != "tool_call":
                raise RuntimeError("AI response must be either a tool_call or final JSON object")

            tool_name = str(payload.get("tool") or "").strip()
            arguments = payload.get("arguments")
            if not tool_name or tool_name not in self._TOOL_NAMES:
                raise RuntimeError(f"Unsupported Copilot tool: {tool_name or 'unknown'}")
            if not isinstance(arguments, dict):
                raise RuntimeError("Copilot tool arguments must be a JSON object")

            result = await self._execute_tool_call(
                tool_name=tool_name,
                arguments=arguments,
                user=user,
                default_wallet_address=wallet_address,
                scope_cache=scope_cache,
            )
            tool_traces.append(
                {
                    "tool": tool_name,
                    "arguments": arguments,
                    "ok": result["ok"],
                    "resultPreview": self._summarize_tool_result(result),
                }
            )
            conversation.append(
                {
                    "role": "assistant",
                    "content": json.dumps({"type": "tool_call", "tool": tool_name, "arguments": arguments}, ensure_ascii=True),
                }
            )
            conversation.append(
                {
                    "role": "user",
                    "content": "TOOL_RESULT " + json.dumps({"tool": tool_name, **result}, ensure_ascii=True, default=str),
                }
            )
        raise RuntimeError("Copilot exceeded the tool-call limit for a single reply")

    async def _execute_tool_call(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        user: AuthenticatedUser,
        default_wallet_address: str | None,
        scope_cache: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            if tool_name == "get_linked_wallets":
                wallet = self._resolve_wallet(user=user, requested_wallet=arguments.get("wallet_address"), required=False)
                scope_cache["default_wallet_address"] = wallet
                return {
                    "ok": True,
                    "data": {
                        "wallet_addresses": user.wallet_addresses,
                        "default_wallet_address": wallet,
                        "user_id": user.user_id,
                    },
                }

            if tool_name == "list_bots":
                wallet = self._resolve_wallet(user=user, requested_wallet=arguments.get("wallet_address") or default_wallet_address)
                scope_cache["default_wallet_address"] = wallet
                definitions = self._bot_builder.list_bots(None, wallet_address=wallet)
                runtimes = self._bot_runtime.list_runtimes_for_wallet(None, wallet_address=wallet, user_id=user.user_id)
                overviews = self._runtime_observability.get_overviews_for_wallet(None, wallet_address=wallet, user_id=user.user_id)
                runtime_by_bot_id = {str(runtime.get("bot_definition_id") or ""): runtime for runtime in runtimes}
                data = [
                    {
                        **definition,
                        "runtime": runtime_by_bot_id.get(definition["id"]),
                        "runtime_overview": overviews.get(definition["id"]),
                    }
                    for definition in definitions
                ]
                return {"ok": True, "data": {"wallet_address": wallet, "bots": data}}

            if tool_name == "get_bot":
                wallet = self._resolve_wallet(user=user, requested_wallet=arguments.get("wallet_address") or default_wallet_address)
                scope_cache["default_wallet_address"] = wallet
                bot_id = str(arguments.get("bot_id") or "").strip()
                if not bot_id:
                    raise RuntimeError("get_bot requires bot_id")
                bot = self._bot_builder.get_bot(None, bot_id=bot_id, wallet_address=wallet)
                runtime = self._bot_runtime.get_runtime(None, bot_id=bot_id, wallet_address=wallet, user_id=user.user_id)
                return {"ok": True, "data": {"wallet_address": wallet, "bot": bot, "runtime": runtime}}

            if tool_name == "get_runtime_overview":
                wallet = self._resolve_wallet(user=user, requested_wallet=arguments.get("wallet_address") or default_wallet_address)
                scope_cache["default_wallet_address"] = wallet
                bot_id = str(arguments.get("bot_id") or "").strip()
                if not bot_id:
                    raise RuntimeError("get_runtime_overview requires bot_id")
                overview = self._runtime_observability.get_overview(None, bot_id=bot_id, wallet_address=wallet, user_id=user.user_id)
                runtime = self._bot_runtime.get_runtime(None, bot_id=bot_id, wallet_address=wallet, user_id=user.user_id)
                return {"ok": True, "data": {"wallet_address": wallet, "bot_id": bot_id, "runtime": runtime, "overview": overview}}

            if tool_name == "get_bot_events":
                wallet = self._resolve_wallet(user=user, requested_wallet=arguments.get("wallet_address") or default_wallet_address)
                scope_cache["default_wallet_address"] = wallet
                bot_id = str(arguments.get("bot_id") or "").strip()
                limit = self._bounded_int(arguments.get("limit"), default=20, minimum=1, maximum=100)
                if not bot_id:
                    raise RuntimeError("get_bot_events requires bot_id")
                events = self._bot_runtime.list_runtime_events(
                    None,
                    bot_id=bot_id,
                    wallet_address=wallet,
                    user_id=user.user_id,
                    limit=limit,
                )
                return {"ok": True, "data": {"wallet_address": wallet, "bot_id": bot_id, "events": events}}

            if tool_name == "get_trading_account":
                wallet = self._resolve_wallet(user=user, requested_wallet=arguments.get("wallet_address") or default_wallet_address)
                scope_cache["default_wallet_address"] = wallet
                snapshot = await self._trading.get_account_snapshot(None, wallet)
                return {"ok": True, "data": snapshot}

            if tool_name == "list_portfolios":
                wallet = self._resolve_wallet(user=user, requested_wallet=arguments.get("wallet_address") or default_wallet_address)
                scope_cache["default_wallet_address"] = wallet
                portfolios = self._portfolio_allocator.list_portfolios(wallet_address=wallet)
                return {"ok": True, "data": {"wallet_address": wallet, "portfolios": portfolios}}

            if tool_name == "get_portfolio":
                wallet = self._resolve_wallet(user=user, requested_wallet=arguments.get("wallet_address") or default_wallet_address)
                scope_cache["default_wallet_address"] = wallet
                portfolio_id = str(arguments.get("portfolio_id") or "").strip()
                if not portfolio_id:
                    raise RuntimeError("get_portfolio requires portfolio_id")
                portfolio = self._portfolio_allocator.get_portfolio(portfolio_id=portfolio_id, wallet_address=wallet)
                return {"ok": True, "data": {"wallet_address": wallet, "portfolio": portfolio}}

            if tool_name == "get_pacifica_authorization":
                wallet = self._resolve_wallet(user=user, requested_wallet=arguments.get("wallet_address") or default_wallet_address)
                scope_cache["default_wallet_address"] = wallet
                authorization = self._pacifica_auth.get_authorization_by_wallet(None, wallet)
                return {"ok": True, "data": {"wallet_address": wallet, "authorization": authorization}}

            if tool_name == "get_pacifica_readiness":
                wallet = self._resolve_wallet(user=user, requested_wallet=arguments.get("wallet_address") or default_wallet_address)
                scope_cache["default_wallet_address"] = wallet
                readiness = await self._pacifica_readiness.get_readiness(None, wallet)
                return {"ok": True, "data": readiness}

            if tool_name == "get_marketplace_overview":
                discover_limit = self._bounded_int(arguments.get("discover_limit"), default=12, minimum=1, maximum=36)
                creator_limit = self._bounded_int(arguments.get("creator_limit"), default=6, minimum=1, maximum=12)
                overview = await self._marketplace.get_marketplace_overview(
                    discover_limit=discover_limit,
                    featured_limit=0,
                    creator_limit=creator_limit,
                )
                return {"ok": True, "data": overview}

            if tool_name == "list_schema_tables":
                return {"ok": True, "data": {"tables": sorted(self._schema_definitions.keys())}}

            if tool_name == "describe_schema_table":
                table = str(arguments.get("table") or "").strip()
                if not table:
                    raise RuntimeError("describe_schema_table requires table")
                definition = self._schema_definitions.get(table)
                if definition is None:
                    raise RuntimeError(f"Unknown schema table: {table}")
                return {"ok": True, "data": definition}

            if tool_name == "query_database":
                table = str(arguments.get("table") or "").strip()
                if not table:
                    raise RuntimeError("query_database requires table")
                rows = self._query_database(
                    table=table,
                    columns=str(arguments.get("columns") or "*").strip() or "*",
                    filters=arguments.get("filters"),
                    order=str(arguments.get("order") or "").strip() or None,
                    limit=self._bounded_int(arguments.get("limit"), default=10, minimum=1, maximum=25),
                    user=user,
                    default_wallet_address=default_wallet_address,
                    requested_wallet_address=arguments.get("wallet_address"),
                    scope_cache=scope_cache,
                )
                return {"ok": True, "data": {"table": table, "rows": rows}}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

        return {"ok": False, "error": f"Unsupported Copilot tool: {tool_name}"}

    def _query_database(
        self,
        *,
        table: str,
        columns: str,
        filters: Any,
        order: str | None,
        limit: int,
        user: AuthenticatedUser,
        default_wallet_address: str | None,
        requested_wallet_address: Any,
        scope_cache: dict[str, Any],
    ) -> list[dict[str, Any]]:
        normalized_table = table.strip()
        if normalized_table not in self._ALLOWED_QUERY_TABLES:
            raise RuntimeError(f"Table is not available to Copilot: {normalized_table}")
        if not self._is_safe_columns(columns):
            raise RuntimeError("query_database columns contains unsupported characters")
        if order and not self._is_safe_order(order):
            raise RuntimeError("query_database order contains unsupported characters")

        requested_filters = self._normalize_filters(filters)
        enforced_filters = self._build_query_scope_filters(
            table=normalized_table,
            user=user,
            default_wallet_address=default_wallet_address,
            requested_wallet_address=requested_wallet_address,
            scope_cache=scope_cache,
        )
        for key in enforced_filters:
            if key in requested_filters and requested_filters[key] != enforced_filters[key]:
                raise RuntimeError(f"query_database cannot override enforced scope filter: {key}")
        merged_filters = {**requested_filters, **enforced_filters}
        return self._supabase.select(
            normalized_table,
            columns=columns,
            filters=merged_filters,
            order=order,
            limit=limit,
        )

    def _build_query_scope_filters(
        self,
        *,
        table: str,
        user: AuthenticatedUser,
        default_wallet_address: str | None,
        requested_wallet_address: Any,
        scope_cache: dict[str, Any],
    ) -> dict[str, Any]:
        if table in self._PUBLIC_QUERY_TABLES:
            return {}
        if table in {"audit_events", "pacifica_authorizations", "users"}:
            if table == "users":
                return {"id": user.user_id}
            return {"user_id": user.user_id}

        wallet = self._resolve_wallet(user=user, requested_wallet=requested_wallet_address or default_wallet_address)
        scope_cache["default_wallet_address"] = wallet
        if table == "bot_copy_relationships":
            return {"follower_wallet_address": wallet}
        if table in self._DIRECT_WALLET_TABLES:
            return {"wallet_address": wallet}
        if table in self._CONVERSATION_SCOPED_TABLES:
            conversation_ids = self._get_owned_conversation_ids(wallet_address=wallet, scope_cache=scope_cache)
            return {"conversation_id": ("in", conversation_ids or ["__none__"])}
        if table in self._BOT_SCOPED_TABLES:
            bot_ids = self._get_owned_bot_ids(wallet_address=wallet, scope_cache=scope_cache)
            return {"bot_definition_id": ("in", bot_ids or ["__none__"])}
        if table in self._RUNTIME_SCOPED_TABLES:
            runtime_ids = self._get_owned_runtime_ids(wallet_address=wallet, scope_cache=scope_cache)
            return {"runtime_id": ("in", runtime_ids or ["__none__"])}
        if table in self._PORTFOLIO_SCOPED_TABLES:
            portfolio_ids = self._get_owned_portfolio_ids(wallet_address=wallet, scope_cache=scope_cache)
            return {"portfolio_basket_id": ("in", portfolio_ids or ["__none__"])}
        raise RuntimeError(f"Missing scope mapping for table: {table}")

    def _get_owned_bot_ids(self, *, wallet_address: str, scope_cache: dict[str, Any]) -> list[str]:
        cache_key = f"bot_ids:{wallet_address}"
        if cache_key not in scope_cache:
            rows = self._supabase.select("bot_definitions", columns="id", filters={"wallet_address": wallet_address}, limit=500)
            scope_cache[cache_key] = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
        return scope_cache[cache_key]

    def _get_owned_runtime_ids(self, *, wallet_address: str, scope_cache: dict[str, Any]) -> list[str]:
        cache_key = f"runtime_ids:{wallet_address}"
        if cache_key not in scope_cache:
            rows = self._supabase.select("bot_runtimes", columns="id", filters={"wallet_address": wallet_address}, limit=500)
            scope_cache[cache_key] = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
        return scope_cache[cache_key]

    def _get_owned_portfolio_ids(self, *, wallet_address: str, scope_cache: dict[str, Any]) -> list[str]:
        cache_key = f"portfolio_ids:{wallet_address}"
        if cache_key not in scope_cache:
            rows = self._supabase.select("portfolio_baskets", columns="id", filters={"wallet_address": wallet_address}, limit=200)
            scope_cache[cache_key] = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
        return scope_cache[cache_key]

    def _get_owned_conversation_ids(self, *, wallet_address: str, scope_cache: dict[str, Any]) -> list[str]:
        cache_key = f"conversation_ids:{wallet_address}"
        if cache_key not in scope_cache:
            rows = self._supabase.select(
                "copilot_conversations",
                columns="id",
                filters={"wallet_address": wallet_address},
                limit=500,
            )
            scope_cache[cache_key] = [str(row.get("id") or "").strip() for row in rows if str(row.get("id") or "").strip()]
        return scope_cache[cache_key]

    def _resolve_wallet(
        self,
        *,
        user: AuthenticatedUser,
        requested_wallet: Any,
        required: bool = True,
    ) -> str | None:
        wallet = str(requested_wallet or "").strip() if requested_wallet else ""
        if wallet:
            if wallet not in user.wallet_addresses:
                raise RuntimeError("Wallet is not linked to the authenticated user")
            return wallet
        if user.wallet_addresses:
            return user.wallet_addresses[0]
        if required:
            raise RuntimeError("No authenticated wallet is available")
        return None

    def _build_system_prompt(self, *, user: AuthenticatedUser, wallet_address: str | None) -> str:
        default_wallet = wallet_address or (user.wallet_addresses[0] if user.wallet_addresses else "")
        return "\n".join(
            [
                "You are ClashX Copilot.",
                "Answer user questions about their trading account, bots, portfolios, Pacifica setup, marketplace context, and schema context.",
                "You must return exactly one JSON object per response. No markdown. No prose outside JSON.",
                "If you need live, user-specific, or database-backed context, call a tool first.",
                "Use plain-text JSON tool calls for every provider.",
                'Tool call shape: {"type":"tool_call","tool":"list_bots","arguments":{"wallet_address":"..."}}',
                'Final answer shape: {"type":"final","reply":"plain text answer","followUps":["optional follow-up 1","optional follow-up 2"]}',
                "When you receive a message starting with TOOL_RESULT, treat it as the output of your previous tool call.",
                "When you receive a message starting with CONTEXT_SUMMARY, treat it as compacted history from older turns in the same conversation.",
                "Never invent balances, bot statuses, event counts, or database rows.",
                "Prefer concise answers that cite concrete numbers, names, ids, or timestamps from tool results when available.",
                "If the user asks about tables or raw data, prefer list_schema_tables, describe_schema_table, or query_database.",
                "Use query_database sparingly, with a small limit and explicit relevant tables only.",
                f"Authenticated user id: {user.user_id}",
                f"Linked wallet addresses: {', '.join(user.wallet_addresses) if user.wallet_addresses else 'none'}",
                f"Default wallet address: {default_wallet or 'none'}",
                "Available tools:",
                self._tool_catalog_text(),
            ]
        )

    def _tool_catalog_text(self) -> str:
        return "\n".join(
            [
                '- `get_linked_wallets` args: `{"wallet_address":"optional linked wallet"}`',
                '- `list_bots` args: `{"wallet_address":"optional linked wallet"}`',
                '- `get_bot` args: `{"bot_id":"required","wallet_address":"optional linked wallet"}`',
                '- `get_runtime_overview` args: `{"bot_id":"required","wallet_address":"optional linked wallet"}`',
                '- `get_bot_events` args: `{"bot_id":"required","wallet_address":"optional linked wallet","limit":20}`',
                '- `get_trading_account` args: `{"wallet_address":"optional linked wallet"}`',
                '- `list_portfolios` args: `{"wallet_address":"optional linked wallet"}`',
                '- `get_portfolio` args: `{"portfolio_id":"required","wallet_address":"optional linked wallet"}`',
                '- `get_pacifica_authorization` args: `{"wallet_address":"optional linked wallet"}`',
                '- `get_pacifica_readiness` args: `{"wallet_address":"optional linked wallet"}`',
                '- `get_marketplace_overview` args: `{"discover_limit":12,"creator_limit":6}`',
                '- `list_schema_tables` args: `{}`',
                '- `describe_schema_table` args: `{"table":"required"}`',
                '- `query_database` args: `{"table":"required","columns":"optional comma-separated columns","filters":{"field":"value or structured filter"},"order":"optional field.asc|field.desc","limit":10,"wallet_address":"optional linked wallet"}`',
            ]
        )

    async def _request_gemini(self, messages: list[dict[str, str]], system_prompt: str) -> str:
        response = await self._http.post(
            self._build_gemini_url(self.settings.gemini_base_url, self.settings.gemini_model),
            headers={
                "Authorization": f"Bearer {self.settings.gemini_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "systemInstruction": {"parts": [{"text": system_prompt}]},
                "contents": self._build_gemini_contents(messages),
                "generationConfig": {
                    "temperature": 0.35,
                    "topP": 0.95,
                    "thinkingConfig": {
                        "includeThoughts": True,
                        "thinkingBudget": 24576,
                    },
                },
            },
        )
        return self._extract_gemini_text(self._parse_response_payload(response))

    async def _request_openai(self, messages: list[dict[str, str]], system_prompt: str) -> str:
        response = await self._http.post(
            self._build_responses_url(self.settings.openai_base_url),
            headers={
                "Authorization": f"Bearer {self.settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.settings.openai_model,
                "input": [
                    {"role": "system", "content": system_prompt},
                    *messages,
                ],
            },
        )
        return self._extract_openai_text(self._parse_response_payload(response))

    def _sanitize_message(self, message: dict[str, str]) -> dict[str, str] | None:
        role = str(message.get("role") or "").strip()
        content = str(message.get("content") or "").strip()
        if role not in {"user", "assistant"} or not content:
            return None
        return {"role": role, "content": content}

    def _sanitize_follow_ups(self, value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        follow_ups: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text:
                follow_ups.append(text)
            if len(follow_ups) >= 3:
                break
        return follow_ups

    def _has_gemini_config(self) -> bool:
        return bool(self.settings.gemini_api_key and self.settings.gemini_base_url and self.settings.gemini_model)

    def _has_openai_config(self) -> bool:
        return bool(self.settings.openai_api_key and self.settings.openai_base_url and self.settings.openai_model)

    def _build_responses_url(self, base_url: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith("/responses"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/responses"
        return f"{normalized}/v1/responses"

    def _build_gemini_url(self, base_url: str, model: str) -> str:
        normalized = base_url.strip().rstrip("/")
        if normalized.endswith(":generateContent"):
            return normalized
        model_path = f"/models/{model}"
        if model_path in normalized:
            return normalized if normalized.endswith(":generateContent") else f"{normalized}:generateContent"
        if normalized.endswith("/models"):
            return f"{normalized}/{model}:generateContent"
        return f"{normalized}/models/{model}:generateContent"

    def _build_gemini_contents(self, messages: list[dict[str, str]]) -> list[dict[str, Any]]:
        contents: list[dict[str, Any]] = []
        for message in messages:
            contents.append(
                {
                    "role": "model" if message.get("role") == "assistant" else "user",
                    "parts": [{"text": message.get("content", "")}],
                }
            )
        return contents

    def _parse_response_payload(self, response: Any) -> Any:
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("AI provider returned a non-JSON response.") from exc
        if getattr(response, "status_code", 500) >= 400:
            error = payload.get("error", {}) if isinstance(payload, dict) else {}
            detail = error.get("message") if isinstance(error, dict) else None
            raise RuntimeError(str(detail or "AI request failed."))
        return payload

    def _extract_openai_text(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        output_text = payload.get("output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        output = payload.get("output")
        if not isinstance(output, list):
            return ""
        chunks: list[str] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        return "\n".join(chunks).strip()

    def _extract_gemini_text(self, payload: Any) -> str:
        if not isinstance(payload, dict):
            return ""
        candidates = payload.get("candidates")
        if not isinstance(candidates, list):
            return ""
        chunks: list[str] = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content")
            if not isinstance(content, dict):
                continue
            parts = content.get("parts")
            if not isinstance(parts, list):
                continue
            for part in parts:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    chunks.append(part["text"])
        return "\n".join(chunks).strip()

    def _extract_json(self, value: str) -> dict[str, Any]:
        return extract_first_json_object(value)

    def _normalize_response_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        nested_function = payload.get("function")
        if isinstance(nested_function, dict) and nested_function.get("name"):
            function_name = str(nested_function["name"]).strip().lower()
            arguments = self._coerce_arguments(nested_function.get("arguments"))
            if function_name in {"final", "final_response", "respond"} and isinstance(arguments.get("reply"), str):
                return {"type": "final", **arguments}
            return {
                "type": "tool_call",
                "tool": nested_function["name"],
                "arguments": arguments,
            }
        if "arguments" in payload and (payload.get("tool") or payload.get("name")):
            normalized_name = str(payload.get("tool") or payload.get("name") or "").strip().lower()
            arguments = self._coerce_arguments(payload.get("arguments"))
            if normalized_name in {"final", "final_response", "respond"} and isinstance(arguments.get("reply"), str):
                return {"type": "final", **arguments}
            return {
                "type": "tool_call",
                "tool": payload.get("tool") or payload.get("name"),
                "arguments": arguments,
            }
        if payload.get("type") == "tool_call":
            return {
                "type": "tool_call",
                "tool": payload.get("tool") or payload.get("name"),
                "arguments": self._coerce_arguments(payload.get("arguments")),
            }
        if payload.get("type") == "final":
            return payload
        if isinstance(payload.get("reply"), str):
            return {"type": "final", **payload}
        raise RuntimeError("AI response JSON did not match a supported Copilot schema")

    def _coerce_arguments(self, value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if isinstance(value, str):
            return self._extract_json(value)
        return {}

    def _summarize_tool_result(self, result: dict[str, Any]) -> str:
        if not result.get("ok"):
            return str(result.get("error") or "Tool call failed")
        serialized = json.dumps(result.get("data"), ensure_ascii=True, default=str)
        return serialized if len(serialized) <= 220 else f"{serialized[:217]}..."

    def _normalize_filters(self, value: Any) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, Any] = {}
        for key, raw in value.items():
            field = str(key or "").strip()
            if not field or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", field):
                raise RuntimeError(f"Invalid filter field: {key}")
            if isinstance(raw, dict):
                operator = str(raw.get("operator") or "eq").strip()
                operand = raw.get("value")
                if operator not in {"eq", "neq", "gt", "gte", "lt", "lte", "like", "ilike", "is", "in"}:
                    raise RuntimeError(f"Unsupported filter operator: {operator}")
                if operator == "in" and not isinstance(operand, list):
                    raise RuntimeError("The `in` filter operator requires a list value")
                normalized[field] = (operator, operand)
                continue
            normalized[field] = raw
        return normalized

    def _bounded_int(self, value: Any, *, default: int, minimum: int, maximum: int) -> int:
        try:
            resolved = int(value)
        except (TypeError, ValueError):
            return default
        return max(minimum, min(maximum, resolved))

    def _is_safe_columns(self, value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_,* ]+", value))

    def _is_safe_order(self, value: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_.]+(\.(asc|desc))?", value))

    def _load_schema_definitions(self) -> dict[str, dict[str, Any]]:
        schema_path = Path(__file__).resolve().parents[2] / "db" / "current_schema.sql"
        try:
            raw_schema = schema_path.read_text(encoding="utf-8")
        except OSError:
            return {}

        definitions: dict[str, dict[str, Any]] = {}
        pattern = re.compile(r"CREATE TABLE public\.([a-zA-Z0-9_]+) \(([\s\S]*?)\n\);", re.MULTILINE)
        for match in pattern.finditer(raw_schema):
            table_name = match.group(1)
            body = match.group(2)
            columns: list[dict[str, str]] = []
            for raw_line in body.splitlines():
                line = raw_line.strip().rstrip(",")
                if not line or line.startswith("CONSTRAINT"):
                    continue
                column_match = re.match(r"([a-zA-Z0-9_]+)\s+(.+)", line)
                if column_match is None:
                    continue
                columns.append(
                    {
                        "name": column_match.group(1),
                        "definition": column_match.group(2),
                    }
                )
            definitions[table_name] = {"table": table_name, "columns": columns}
        return definitions
