"""Environment/request parsing helpers for route handlers.

Variables are not stored globally here; all helpers are pure functions.

How this module works:
- `env_int` and `env_bool` read optional values from process env safely.
- `payload_int` and `payload_bool` parse API request JSON values safely.
- `parse_usernames` normalizes comma/newline separated usernames.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from da_watcher.env_utils import parse_bool, parse_csv_values


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return parse_bool(raw)
    except ValueError:
        return default


def payload_bool(payload: Dict[str, Any], key: str, default: bool) -> bool:
    value = payload.get(key, default)
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        try:
            return parse_bool(value)
        except ValueError:
            return default
    return default


def payload_int(
    payload: Dict[str, Any],
    key: str,
    default: int,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    value = payload.get(key, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default

    if minimum is not None:
        parsed = max(minimum, parsed)
    if maximum is not None:
        parsed = min(maximum, parsed)
    return parsed


def parse_usernames(raw: str) -> List[str]:
    normalized = raw.replace("\n", ",").replace("\r", ",")
    return parse_csv_values(normalized)
