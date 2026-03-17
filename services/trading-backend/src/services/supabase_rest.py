from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

import httpx

from src.core.settings import get_settings


class SupabaseRestError(RuntimeError):
    def __init__(self, message: str, *, status_code: int, response_json: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_json = response_json


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

    def select(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: Mapping[str, Any] | None = None,
        order: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        params: dict[str, str] = {"select": columns}
        params.update(self._build_filters(filters))
        if order:
            params["order"] = order
        if limit is not None:
            params["limit"] = str(limit)
        response = self._request("GET", f"/{table}", params=params)
        data = response.json()
        return data if isinstance(data, list) else []

    def maybe_one(
        self,
        table: str,
        *,
        columns: str = "*",
        filters: Mapping[str, Any] | None = None,
        order: str | None = None,
    ) -> dict[str, Any] | None:
        rows = self.select(table, columns=columns, filters=filters, order=order, limit=1)
        return rows[0] if rows else None

    def insert(
        self,
        table: str,
        payload: dict[str, Any] | list[dict[str, Any]],
        *,
        upsert: bool = False,
        on_conflict: str | None = None,
    ) -> list[dict[str, Any]]:
        headers = {"Prefer": "resolution=merge-duplicates,return=representation" if upsert else "return=representation"}
        params = {"on_conflict": on_conflict} if on_conflict else None
        response = self._request("POST", f"/{table}", json=payload, headers=headers, params=params)
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
    ) -> list[dict[str, Any]]:
        headers = {"Prefer": "return=representation"}
        response = self._request("PATCH", f"/{table}", json=values, headers=headers, params=self._build_filters(filters))
        data = response.json()
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return [data]
        return []

    def delete(self, table: str, *, filters: Mapping[str, Any]) -> None:
        self._request("DELETE", f"/{table}", params=self._build_filters(filters), headers={"Prefer": "return=minimal"})

    def close(self) -> None:
        self._client.close()

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

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, str] | None = None,
        json: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        response = self._client.request(method, path, params=params, json=json, headers=headers)
        if response.is_error:
            try:
                payload = response.json()
            except ValueError:
                payload = response.text
            message = payload.get("message") if isinstance(payload, dict) else response.text
            raise SupabaseRestError(
                message or f"Supabase request failed with status {response.status_code}",
                status_code=response.status_code,
                response_json=payload,
            )
        return response
