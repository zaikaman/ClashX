from __future__ import annotations

import json
from typing import Any


def sort_json_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: sort_json_keys(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        return [sort_json_keys(item) for item in value]
    return value


def prepare_message(header: dict[str, Any], payload: dict[str, Any]) -> str:
    if "type" not in header or "timestamp" not in header or "expiry_window" not in header:
        raise ValueError("Header must have type, timestamp, and expiry_window")
    return json.dumps(sort_json_keys({**header, "data": payload}), separators=(",", ":"))
