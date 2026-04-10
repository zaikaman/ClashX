from __future__ import annotations

import json
import re
from typing import Any


_JSON_FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


def extract_first_json_object(value: str) -> dict[str, Any]:
    trimmed = value.strip()
    if not trimmed:
        raise RuntimeError("Empty AI response")

    fenced = _JSON_FENCE_PATTERN.search(trimmed)
    candidate = fenced.group(1).strip() if fenced else trimmed
    if not candidate:
        raise RuntimeError("AI response did not contain JSON")

    decoder = json.JSONDecoder()
    for index, char in enumerate(candidate):
        if char != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(candidate, index)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise RuntimeError("AI response did not contain a valid JSON object")
