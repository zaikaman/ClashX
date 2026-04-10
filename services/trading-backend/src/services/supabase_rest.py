from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import unescape
import re
from time import monotonic
from typing import Any

import httpx

from src.core.settings import get_settings


class SupabaseRestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int, response_json: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_json = response_json

    @property
    def is_retryable(self) -> bool:
        return self.status_code >= 500


_HTML_TITLE_RE = re.compile(r"<title>\s*(.*?)\s*</title>", re.IGNORECASE | re.DOTALL)
_WHITESPACE_RE = re.compile(r"\s+")
_MAX_ERROR_MESSAGE_LENGTH = 240
_DEFAULT_CACHE_TTL_SECONDS = 15.0


class SupabaseRestClient:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise RuntimeError("Supabase API mode requires SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY")
        self._base_url = f"{settings.supabase_url.rstrip('/')}/rest/v1"
        self._headers = {
            "apikey": settings.supabase_service_role_key,
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
            "Content-Type": "application/json",
        }
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=self._headers,
            timeout=20,
        )
        self._read_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: Mapping[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> list[dict[str, Any]]:
        cache_key = self._build_read_cache_key(
            table,
            columns=columns,
            filters=filters,
            order=order,
            limit=limit,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        effective_cache_ttl = min(max(0.0, float(cache_ttl_seconds or 0.0)), _DEFAULT_CACHE_TTL_SECONDS)
        if cache_key is not None:
            cached = self._read_cache.get(cache_key)
            if cached is not None and (monotonic() - cached[0]) < effective_cache_ttl:
                return [dict(row) for row in cached[1]]
        params: dict[str, str] = {"select": columns}
        params.update(self._build_filters(filters))
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        response = self._request("GET", f"/{table}", params=params)
        data = response.json()
        rows = data if isinstance(data, list) else []
        if cache_key is not None:
            self._read_cache[cache_key] = (monotonic(), [dict(row) for row in rows if isinstance(row, dict)])
        return rows

    def maybe_one(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: Mapping[str, Any] | None = None,
        order: str | None = None,
        cache_ttl_seconds: float | None = None,
    ) -> dict[str, Any] | None:
        rows = self.select(
            table,
            columns=columns,
            filters=filters,
            order=order,
            limit=1,
            cache_ttl_seconds=cache_ttl_seconds,
        )
        return rows[0] if rows else None

    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
        returning: str = "representation",
    ) -> list[dict[str, Any]]:
        prefer_parts = ["return=minimal" if returning == "minimal" else "return=representation"]
        if upsert:
            prefer_parts.insert(0, "resolution=merge-duplicates")
        headers = {"Prefer": ",".join(prefer_parts)}
        params = {"on_conflict": on_conflict} if on_conflict else None
        response = self._request("POST", f"/{table}", json=payload, headers=headers, params=params)
        self._invalidate_table_cache(table)
        if returning == "minimal":
            return []
        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def update(
        self,
        table: str,
        values: dict[str, Any],
        *,
        filters: Mapping[str, Any],
        returning: str = "representation",
    ) -> list[dict[str, Any]]:
        headers = {"Prefer": "return=minimal" if returning == "minimal" else "return=representation"}
        response = self._request("PATCH", f"/{table}", json=values, headers=headers, params=self._build_filters(filters))
        self._invalidate_table_cache(table)
        if returning == "minimal":
            return []
        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def delete(self, table: str, *, filters: Mapping[str, Any]) -> None:
        self._request("DELETE", f"/{table}", params=self._build_filters(filters), headers={"Prefer": "return=minimal"})
        self._invalidate_table_cache(table)

    def close(self) -> None:
        self._client.close()
        self._read_cache.clear()

    def _build_filters(self, filters: Mapping[str, Any] | None) -> dict[str, str]:
        params: dict[str, str] = {}
        if not filters:
            return params
        for key, value in filters.items():
            if isinstance(value, tuple):
                operator, operand = value
            else:
                operator, operand = "eq", value
            params[key] = self._format_filter(operator, operand)
        return params

    def _format_filter(self, operator: str, operand: Any) -> str:
        if operator == "in":
            assert isinstance(operand, Sequence)
            joined = ",".join(self._quote(item) for item in operand)
            return f"in.({joined})"
        if operator == "is":
            return f"is.{str(operand).lower()}"
        return f"{operator}.{self._quote(operand)}"

    def _quote(self, value: Any) -> str:
        if isinstance(value, bool):
            return str(value).lower()
        if value is None:
            return "null"
        return str(value)

    def _build_read_cache_key(
        self,
        table: str,
        *,
        columns: str,
        filters: Mapping[str, Any] | None,
        order: str | None,
        limit: int | None,
        cache_ttl_seconds: float | None,
    ) -> str | None:
        if cache_ttl_seconds is None:
            return None
        if cache_ttl_seconds <= 0:
            return None
        normalized_filters = self._normalize_cacheable_filters(filters)
        if normalized_filters is None:
            return None
        ttl = min(float(cache_ttl_seconds), _DEFAULT_CACHE_TTL_SECONDS)
        return f"{table}|{columns}|{order or ''}|{limit or ''}|{normalized_filters}|{ttl}"

    def _normalize_cacheable_filters(self, filters: Mapping[str, Any] | None) -> tuple[tuple[str, Any], ...] | None:
        if not filters:
            return tuple()
        normalized: list[tuple[str, Any]] = []
        for key in sorted(filters):
            value = filters[key]
            if isinstance(value, tuple):
                operator, operand = value
                if operator != "eq":
                    return None
                value = operand
            elif isinstance(value, (list, dict, set)):
                return None
            normalized.append((str(key), value))
        return tuple(normalized)

    def _invalidate_table_cache(self, table: str) -> None:
        prefix = f"{table}|"
        for key in [cache_key for cache_key in self._read_cache if cache_key.startswith(prefix)]:
            self._read_cache.pop(key, None)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        try:
            response = self._client.request(method, path, params=params, json=json, headers=headers)
        except httpx.RequestError as exc:
            raise SupabaseRestError(
                f"Supabase request failed before a response was received: {exc.__class__.__name__}",
                status_code=503,
                response_json={"detail": str(exc)},
            ) from exc
        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            raise SupabaseRestError(
                self._build_error_message(response=response, payload=payload),
                status_code=response.status_code,
                response_json=payload,
            )
        return response

    @classmethod
    def _build_error_message(cls, *, response: httpx.Response, payload: Any) -> str:
        prefix = f"Supabase request failed with status {response.status_code}"
        if isinstance(payload, dict):
            detail = cls._extract_json_error_detail(payload)
            return f"{prefix}: {detail}" if detail else prefix

        text = cls._normalize_error_text(payload)
        if cls._looks_like_html_response(response=response, text=text):
            title = cls._extract_html_title(text)
            if title:
                return f"{prefix}: upstream returned an HTML error page ({title})"
            return f"{prefix}: upstream returned an HTML error page"
        return f"{prefix}: {text}" if text else prefix

    @staticmethod
    def _extract_json_error_detail(payload: Mapping[str, Any]) -> str | None:
        for key in ("message", "error", "details", "hint", "code"):
            value = payload.get(key)
            if isinstance(value, str):
                detail = SupabaseRestClient._normalize_error_text(value)
                if detail:
                    return detail
        return None

    @staticmethod
    def _looks_like_html_response(*, response: httpx.Response, text: str) -> bool:
        content_type = str(response.headers.get("content-type") or "").lower()
        if "text/html" in content_type:
            return True
        return text.startswith("<!doctype html") or text.startswith("<html")

    @staticmethod
    def _extract_html_title(text: str) -> str | None:
        match = _HTML_TITLE_RE.search(text)
        if match is None:
            return None
        title = _WHITESPACE_RE.sub(" ", unescape(match.group(1))).strip(" |")
        return title or None

    @staticmethod
    def _normalize_error_text(value: Any) -> str:
        text = _WHITESPACE_RE.sub(" ", str(value or "")).strip()
        if len(text) <= _MAX_ERROR_MESSAGE_LENGTH:
            return text
        return f"{text[:_MAX_ERROR_MESSAGE_LENGTH - 3].rstrip()}..."
