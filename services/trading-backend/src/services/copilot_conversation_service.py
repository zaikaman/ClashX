from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from src.api.auth import AuthenticatedUser
from src.services.copilot_service import CopilotService
from src.services.supabase_rest import SupabaseRestClient


MAX_CONTEXT_TOKENS = 100_000
TARGET_RECENT_TOKENS = 30_000
MIN_RECENT_MESSAGES = 6
MAX_CONVERSATION_LIST = 48
DEFAULT_CONVERSATION_TITLE = "New conversation"
MAX_PREVIEW_LENGTH = 180
DEFAULT_WALLET_PREVIEW = "ClashX"
CONVERSATION_LIST_CACHE_TTL_SECONDS = 5.0
CONVERSATION_DETAIL_CACHE_TTL_SECONDS = 5.0


def estimate_token_count(text: str) -> int:
    normalized = text.strip()
    if not normalized:
        return 0
    return max(1, (len(normalized) + 3) // 4)


def _as_iso_now() -> str:
    return datetime.now(tz=UTC).isoformat()


class CopilotConversationService:
    def __init__(
        self,
        *,
        copilot: CopilotService | None = None,
        supabase: SupabaseRestClient | None = None,
    ) -> None:
        self._copilot = copilot or CopilotService()
        self._supabase = supabase or SupabaseRestClient()

    def list_conversations(self, *, user: AuthenticatedUser) -> list[dict[str, Any]]:
        wallets = self._wallet_scope(user)
        if not wallets:
            return []
        rows = self._supabase.select(
            "copilot_conversations",
            columns=(
                "id,title,user_id,wallet_address,message_count,last_message_preview,"
                "created_at,updated_at,latest_message_at"
            ),
            filters={"wallet_address": ("in", wallets)},
            order="latest_message_at.desc",
            limit=MAX_CONVERSATION_LIST,
            cache_ttl_seconds=CONVERSATION_LIST_CACHE_TTL_SECONDS,
        )
        return [self._serialize_conversation_summary(row) for row in rows]

    def create_conversation(
        self,
        *,
        user: AuthenticatedUser,
        wallet_address: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        created = self._create_conversation_row(
            user=user,
            wallet_address=wallet_address,
            title=title,
        )
        return self._serialize_conversation_summary(created)

    def _create_conversation_row(
        self,
        *,
        user: AuthenticatedUser,
        wallet_address: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        wallet = self._resolve_wallet(user=user, requested_wallet=wallet_address)
        user_row = self._upsert_user(wallet_address=wallet)
        now = _as_iso_now()
        row = {
            "id": str(uuid.uuid4()),
            "user_id": user_row["id"],
            "wallet_address": wallet,
            "title": self._normalize_title(title),
            "context_summary": "",
            "summary_message_count": 0,
            "summary_token_estimate": 0,
            "message_count": 0,
            "last_message_preview": "",
            "created_at": now,
            "updated_at": now,
            "latest_message_at": now,
        }
        self._supabase.insert(
            "copilot_conversations",
            row,
            returning="minimal",
        )
        return row

    def get_conversation(self, *, user: AuthenticatedUser, conversation_id: str) -> dict[str, Any]:
        conversation = self._require_conversation(user=user, conversation_id=conversation_id)
        messages = self._list_messages(conversation_id=conversation_id)
        return {
            **self._serialize_conversation_summary(conversation),
            "summaryMessageCount": int(conversation.get("summary_message_count") or 0),
            "summaryText": str(conversation.get("context_summary") or ""),
            "messages": [self._serialize_message(row) for row in messages],
        }

    def delete_conversation(self, *, user: AuthenticatedUser, conversation_id: str) -> None:
        conversation = self._require_conversation(user=user, conversation_id=conversation_id)
        self._supabase.delete("copilot_messages", filters={"conversation_id": conversation["id"]})
        self._supabase.delete("copilot_conversations", filters={"id": conversation["id"]})

    async def send_message(
        self,
        *,
        user: AuthenticatedUser,
        content: str,
        conversation_id: str | None = None,
        wallet_address: str | None = None,
    ) -> dict[str, Any]:
        normalized_content = " ".join(content.split()) if "\n" not in content else content.strip()
        if not normalized_content:
            raise ValueError("A chat message is required.")

        conversation = self._get_or_create_conversation(
            user=user,
            conversation_id=conversation_id,
            wallet_address=wallet_address,
        )
        requested_wallet = wallet_address or str(conversation.get("wallet_address") or "").strip() or None
        resolved_wallet = self._resolve_wallet(user=user, requested_wallet=requested_wallet)
        if resolved_wallet != conversation.get("wallet_address"):
            conversation = self._sync_conversation_wallet(conversation=conversation, wallet_address=resolved_wallet)

        now = _as_iso_now()
        user_message = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation["id"],
            "role": "user",
            "content": normalized_content,
            "tool_calls_json": [],
            "follow_ups_json": [],
            "provider": None,
            "token_estimate": estimate_token_count(normalized_content),
            "created_at": now,
        }
        self._supabase.insert(
            "copilot_messages",
            user_message,
            returning="minimal",
        )
        conversation = self._merge_conversation_patch(
            conversation,
            "copilot_conversations",
            self._conversation_patch(
                conversation=conversation,
                title=self._derived_title_for_message(conversation=conversation, content=normalized_content),
                message_count=int(conversation.get("message_count") or 0) + 1,
                last_message_preview=self._preview_text(normalized_content),
                updated_at=now,
                latest_message_at=now,
            ),
        )

        messages = self._list_messages(conversation_id=conversation["id"])
        conversation = await self._compact_context_if_needed(conversation=conversation, messages=messages)
        context_messages = self._build_runtime_messages(conversation=conversation, messages=messages)

        result = await self._copilot.chat(
            messages=context_messages,
            user=user,
            wallet_address=resolved_wallet,
        )

        assistant_now = _as_iso_now()
        assistant_row = {
            "id": str(uuid.uuid4()),
            "conversation_id": conversation["id"],
            "role": "assistant",
            "content": result["reply"],
            "tool_calls_json": result.get("toolCalls") or [],
            "follow_ups_json": result.get("followUps") or [],
            "provider": result.get("provider"),
            "token_estimate": estimate_token_count(result["reply"]),
            "created_at": assistant_now,
        }
        self._supabase.insert(
            "copilot_messages",
            assistant_row,
            returning="minimal",
        )
        conversation = self._merge_conversation_patch(
            conversation,
            "copilot_conversations",
            self._conversation_patch(
                conversation=conversation,
                message_count=int(conversation.get("message_count") or 0) + 1,
                last_message_preview=self._preview_text(result["reply"]),
                updated_at=assistant_now,
                latest_message_at=assistant_now,
            ),
        )

        return {
            "conversationId": conversation["id"],
            "conversation": self._serialize_conversation_summary(conversation),
            "assistantMessage": self._serialize_message(assistant_row),
            **result,
        }

    async def _compact_context_if_needed(
        self,
        *,
        conversation: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        summary_message_count = min(int(conversation.get("summary_message_count") or 0), len(messages))
        unsummarized_messages = messages[summary_message_count:]
        if len(unsummarized_messages) <= MIN_RECENT_MESSAGES:
            return conversation

        total_tokens = int(conversation.get("summary_token_estimate") or 0) + sum(
            self._message_token_estimate(message) for message in unsummarized_messages
        )
        if total_tokens <= MAX_CONTEXT_TOKENS:
            return conversation

        keep_start = max(0, len(unsummarized_messages) - MIN_RECENT_MESSAGES)
        kept_tokens = sum(self._message_token_estimate(message) for message in unsummarized_messages[keep_start:])
        for index in range(keep_start - 1, -1, -1):
            message_tokens = self._message_token_estimate(unsummarized_messages[index])
            if kept_tokens + message_tokens > TARGET_RECENT_TOKENS:
                break
            keep_start = index
            kept_tokens += message_tokens

        if keep_start <= 0:
            keep_start = max(0, len(unsummarized_messages) - MIN_RECENT_MESSAGES)
        messages_to_summarize = unsummarized_messages[:keep_start]
        if not messages_to_summarize:
            return conversation

        updated_summary = await self._copilot.summarize_history(
            existing_summary=str(conversation.get("context_summary") or ""),
            messages=[
                {
                    "role": str(message.get("role") or "assistant"),
                    "content": self._message_to_summary_text(message),
                }
                for message in messages_to_summarize
            ],
        )
        now = _as_iso_now()
        return self._merge_conversation_patch(
            conversation,
            "copilot_conversations",
            {
                "context_summary": updated_summary,
                "summary_message_count": summary_message_count + len(messages_to_summarize),
                "summary_token_estimate": estimate_token_count(updated_summary),
                "updated_at": now,
            },
        )

    def _build_runtime_messages(
        self,
        *,
        conversation: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> list[dict[str, str]]:
        summary_message_count = min(int(conversation.get("summary_message_count") or 0), len(messages))
        runtime_messages: list[dict[str, str]] = []
        summary_text = str(conversation.get("context_summary") or "").strip()
        if summary_text:
            runtime_messages.append(
                {
                    "role": "assistant",
                    "content": f"CONTEXT_SUMMARY\n{summary_text}",
                }
            )
        for message in messages[summary_message_count:]:
            role = str(message.get("role") or "").strip()
            content = str(message.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                runtime_messages.append({"role": role, "content": content})
        return runtime_messages

    def _get_or_create_conversation(
        self,
        *,
        user: AuthenticatedUser,
        conversation_id: str | None,
        wallet_address: str | None,
    ) -> dict[str, Any]:
        if conversation_id:
            return self._require_conversation(user=user, conversation_id=conversation_id)
        return self._create_conversation_row(user=user, wallet_address=wallet_address)

    def _require_conversation(self, *, user: AuthenticatedUser, conversation_id: str) -> dict[str, Any]:
        filters: dict[str, Any] = {"id": conversation_id}
        wallets = self._wallet_scope(user)
        if not wallets:
            raise ValueError("No linked wallet is available for Copilot.")
        filters["wallet_address"] = ("in", wallets)
        conversation = self._supabase.maybe_one(
            "copilot_conversations",
            filters=filters,
            cache_ttl_seconds=CONVERSATION_DETAIL_CACHE_TTL_SECONDS,
        )
        if conversation is None:
            raise ValueError("Conversation not found.")
        return conversation

    def _sync_conversation_wallet(self, *, conversation: dict[str, Any], wallet_address: str) -> dict[str, Any]:
        user_row = self._upsert_user(wallet_address=wallet_address)
        return self._merge_conversation_patch(
            conversation,
            "copilot_conversations",
            {
                "user_id": user_row["id"],
                "wallet_address": wallet_address,
                "updated_at": _as_iso_now(),
            },
        )

    def _list_messages(self, *, conversation_id: str) -> list[dict[str, Any]]:
        return self._supabase.select(
            "copilot_messages",
            columns="id,conversation_id,role,content,tool_calls_json,follow_ups_json,provider,token_estimate,created_at",
            filters={"conversation_id": conversation_id},
            order="created_at.asc",
            cache_ttl_seconds=CONVERSATION_DETAIL_CACHE_TTL_SECONDS,
        )

    def _wallet_scope(self, user: AuthenticatedUser) -> list[str]:
        wallets: list[str] = []
        for wallet in user.wallet_addresses:
            normalized = str(wallet or "").strip()
            if normalized and normalized not in wallets:
                wallets.append(normalized)
        return wallets

    def _resolve_wallet(self, *, user: AuthenticatedUser, requested_wallet: str | None) -> str:
        wallet = str(requested_wallet or "").strip()
        if wallet:
            if wallet not in user.wallet_addresses:
                raise ValueError("Wallet is not linked to the authenticated user.")
            return wallet
        if user.wallet_addresses:
            return str(user.wallet_addresses[0])
        raise ValueError("No linked wallet is available for Copilot.")

    def _upsert_user(self, *, wallet_address: str) -> dict[str, Any]:
        existing = self._supabase.maybe_one("users", filters={"wallet_address": wallet_address}, cache_ttl_seconds=60)
        if existing is not None:
            return existing
        return self._supabase.insert(
            "users",
            {
                "id": str(uuid.uuid4()),
                "wallet_address": wallet_address,
                "display_name": wallet_address[:8] if wallet_address else DEFAULT_WALLET_PREVIEW,
                "auth_provider": "privy",
                "created_at": _as_iso_now(),
            },
            upsert=True,
            on_conflict="wallet_address",
        )[0]

    def _merge_conversation_patch(
        self,
        conversation: dict[str, Any],
        table: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        self._supabase.update(
            table,
            patch,
            filters={"id": conversation["id"]},
            returning="minimal",
        )
        return {**conversation, **patch}

    def _normalize_title(self, value: str | None) -> str:
        cleaned = " ".join(str(value or "").split()).strip()
        if not cleaned:
            return DEFAULT_CONVERSATION_TITLE
        return cleaned[:80]

    def _derived_title_for_message(self, *, conversation: dict[str, Any], content: str) -> str:
        existing_title = str(conversation.get("title") or "").strip()
        if existing_title and existing_title != DEFAULT_CONVERSATION_TITLE:
            return existing_title
        return self._normalize_title(content)

    def _preview_text(self, value: str) -> str:
        compact = " ".join(value.split()).strip()
        if len(compact) <= MAX_PREVIEW_LENGTH:
            return compact
        return f"{compact[: MAX_PREVIEW_LENGTH - 3].rstrip()}..."

    def _message_token_estimate(self, message: dict[str, Any]) -> int:
        stored = message.get("token_estimate")
        try:
            resolved = int(stored)
        except (TypeError, ValueError):
            resolved = estimate_token_count(str(message.get("content") or ""))
        return max(0, resolved)

    def _message_to_summary_text(self, message: dict[str, Any]) -> str:
        content = str(message.get("content") or "").strip()
        tool_calls = message.get("tool_calls_json")
        if isinstance(tool_calls, list) and tool_calls:
            traces: list[str] = []
            for tool_call in tool_calls[:4]:
                if not isinstance(tool_call, dict):
                    continue
                tool = str(tool_call.get("tool") or "").strip()
                preview = str(tool_call.get("resultPreview") or "").strip()
                if tool or preview:
                    traces.append(f"{tool}: {preview}".strip(": "))
            if traces:
                content = f"{content}\nTool traces: {' | '.join(traces)}".strip()
        return content

    def _conversation_patch(
        self,
        *,
        conversation: dict[str, Any],
        title: str | None = None,
        message_count: int | None = None,
        last_message_preview: str | None = None,
        updated_at: str | None = None,
        latest_message_at: str | None = None,
    ) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        if title is not None:
            patch["title"] = title
        if message_count is not None:
            patch["message_count"] = message_count
        if last_message_preview is not None:
            patch["last_message_preview"] = last_message_preview
        patch["updated_at"] = updated_at or _as_iso_now()
        patch["latest_message_at"] = latest_message_at or conversation.get("latest_message_at") or patch["updated_at"]
        return patch

    def _serialize_conversation_summary(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row.get("id") or ""),
            "title": str(row.get("title") or DEFAULT_CONVERSATION_TITLE),
            "walletAddress": str(row.get("wallet_address") or ""),
            "messageCount": int(row.get("message_count") or 0),
            "lastMessagePreview": str(row.get("last_message_preview") or ""),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
            "latestMessageAt": row.get("latest_message_at") or row.get("updated_at") or row.get("created_at"),
        }

    def _serialize_message(self, row: dict[str, Any]) -> dict[str, Any]:
        tool_calls = row.get("tool_calls_json")
        follow_ups = row.get("follow_ups_json")
        return {
            "id": str(row.get("id") or ""),
            "role": str(row.get("role") or "assistant"),
            "content": str(row.get("content") or ""),
            "toolCalls": tool_calls if isinstance(tool_calls, list) else [],
            "followUps": [str(item) for item in follow_ups] if isinstance(follow_ups, list) else [],
            "provider": str(row.get("provider") or "") or None,
            "createdAt": row.get("created_at"),
        }
