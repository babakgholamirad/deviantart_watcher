from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name: str, fallback: str = "deviation") -> str:
    cleaned = INVALID_FILE_CHARS.sub("_", name).strip().strip(".")
    cleaned = re.sub(r"\s+", " ", cleaned)
    if not cleaned:
        cleaned = fallback
    return cleaned[:120]


def extension_from_url(url: str) -> str:
    parsed = urlparse(url)
    suffix = Path(unquote(parsed.path)).suffix.lower()
    return suffix if suffix else ""


def build_output_path(
    output_dir: Path,
    username: str,
    deviation_id: str,
    title: str,
    source_url: str,
    preferred_filename: Optional[str],
) -> Path:
    user_dir = output_dir / sanitize_filename(username, fallback="user")
    user_dir.mkdir(parents=True, exist_ok=True)

    ext = ""
    stem = ""
    if preferred_filename:
        preferred = Path(preferred_filename)
        ext = preferred.suffix.lower()
        stem = preferred.stem

    # Prefer API filename extension, then URL suffix, then a safe fallback.
    if not ext:
        ext = extension_from_url(source_url)
    if not ext:
        ext = ".jpg"

    safe_stem = sanitize_filename(stem or title or deviation_id)
    filename = f"{deviation_id}_{safe_stem}{ext}"
    return user_dir / filename


def load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"users": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logging.warning("State file %s is invalid JSON. Starting with empty state.", path)
        return {"users": {}}
    if not isinstance(data, dict):
        return {"users": {}}
    users = data.get("users")
    if not isinstance(users, dict):
        data["users"] = {}
    return data


def save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(state, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def ensure_user_state(state: Dict[str, Any], username: str) -> Dict[str, Any]:
    users = state.setdefault("users", {})
    if not isinstance(users, dict):
        users = {}
        state["users"] = users

    user_state = users.setdefault(username, {"seen_ids": []})
    if not isinstance(user_state, dict):
        user_state = {"seen_ids": []}
        users[username] = user_state

    seen_ids = user_state.setdefault("seen_ids", [])
    if not isinstance(seen_ids, list):
        user_state["seen_ids"] = []
    return user_state

