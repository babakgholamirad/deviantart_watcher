from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return parse_bool(value)
    except ValueError as exc:
        raise SystemExit(f"Environment variable {name} must be boolean: {exc}") from exc


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"Environment variable {name} must be an integer.") from exc


def parse_csv_values(raw_value: str) -> List[str]:
    return [part.strip() for part in raw_value.split(",") if part.strip()]


def resolve_usernames(
    cli_usernames: Optional[List[str]],
    cli_usernames_csv: Optional[str],
    env_usernames_csv: str,
    env_username_single: str,
) -> List[str]:
    values: List[str] = []

    # CLI values are highest priority, then fallback to environment variables.
    if cli_usernames:
        for item in cli_usernames:
            values.extend(parse_csv_values(item))
    if cli_usernames_csv:
        values.extend(parse_csv_values(cli_usernames_csv))

    if not values:
        if env_usernames_csv.strip():
            values.extend(parse_csv_values(env_usernames_csv))
        elif env_username_single.strip():
            values.extend(parse_csv_values(env_username_single))

    # Keep first occurrence order while deduplicating case-insensitively.
    deduped: List[str] = []
    seen = set()
    for username in values:
        key = username.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(username)
    return deduped

