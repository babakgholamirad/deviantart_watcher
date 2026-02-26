#!/usr/bin/env python3
"""Local web UI for running the downloader and browsing downloaded images."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, List

import requests
from flask import Flask, jsonify, request, send_from_directory

from da_watcher.api import DEFAULT_USER_AGENT, DeviantArtApiError, DeviantArtClient
from da_watcher.config import AppConfig
from da_watcher.env_utils import load_env_file, parse_bool, parse_csv_values
from da_watcher.storage import load_state, save_state
from da_watcher.watcher import process_user_once

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_env_file(ENV_FILE)

DOWNLOADS_DIR = BASE_DIR / os.getenv("OUTPUT_DIR", "downloads")
STATE_FILE = BASE_DIR / os.getenv("STATE_FILE", "state.json")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
run_lock = threading.Lock()


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


def parse_usernames(raw: str) -> List[str]:
    normalized = raw.replace("\n", ",").replace("\r", ",")
    return parse_csv_values(normalized)


def build_runtime_config(client_id: str, client_secret: str, usernames: List[str]) -> AppConfig:
    return AppConfig(
        client_id=client_id,
        client_secret=client_secret,
        usernames=usernames,
        output_dir=DOWNLOADS_DIR,
        state_file=STATE_FILE,
        pages=max(1, min(10, env_int("PAGES_PER_CHECK", 3))),
        limit=max(1, min(24, env_int("PAGE_SIZE", 24))),
        interval=0,
        include_mature=env_bool("INCLUDE_MATURE", False),
        allow_preview=env_bool("ALLOW_PREVIEW", False),
        seed_only=False,
        max_seen=max(100, env_int("MAX_SEEN_IDS", 5000)),
        timeout=max(5, env_int("REQUEST_TIMEOUT_SECONDS", 30)),
        user_agent=os.getenv("USER_AGENT", DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT,
        verbose=env_bool("VERBOSE", False),
    )


def scan_images() -> List[Dict[str, Any]]:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    images: List[Dict[str, Any]] = []

    for path in DOWNLOADS_DIR.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in IMAGE_EXTENSIONS:
            continue
        rel_path = path.relative_to(DOWNLOADS_DIR).as_posix()
        stats = path.stat()
        images.append(
            {
                "name": path.name,
                "relative_path": rel_path,
                "url": f"/downloads/{rel_path}",
                "mtime": int(stats.st_mtime),
                "size_bytes": stats.st_size,
            }
        )

    images.sort(key=lambda item: item["mtime"], reverse=True)
    return images


def run_download_job(config: AppConfig) -> Dict[str, Any]:
    state = load_state(config.state_file)
    client = DeviantArtClient(
        client_id=config.client_id,
        client_secret=config.client_secret,
        user_agent=config.user_agent,
        timeout=config.timeout,
    )

    cycle_stats = {
        "users_checked": 0,
        "pages_checked": 0,
        "new_items": 0,
        "downloaded": 0,
        "existing": 0,
        "skipped": 0,
    }
    errors: List[str] = []

    for username in config.usernames:
        try:
            stats = process_user_once(config, client, state, username)
            cycle_stats["users_checked"] += 1
            cycle_stats["pages_checked"] += stats["pages_checked"]
            cycle_stats["new_items"] += stats["new_items"]
            cycle_stats["downloaded"] += stats["downloaded"]
            cycle_stats["existing"] += stats["existing"]
            cycle_stats["skipped"] += stats["skipped"]
        except DeviantArtApiError as exc:
            errors.append(f"API error for @{username}: {exc}")
        except requests.RequestException as exc:
            errors.append(f"Network error for @{username}: {exc}")
        except Exception as exc:
            errors.append(f"Unexpected error for @{username}: {exc}")

    save_state(config.state_file, state)
    return {"stats": cycle_stats, "errors": errors}


@app.get("/")
def home() -> Any:
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/api/defaults")
def api_defaults() -> Any:
    return jsonify(
        {
            "client_id": os.getenv("DA_CLIENT_ID", ""),
            "client_secret": os.getenv("DA_CLIENT_SECRET", ""),
            "usernames": os.getenv("DA_USERNAMES", os.getenv("DA_USERNAME", "")),
        }
    )


@app.get("/api/gallery")
def api_gallery() -> Any:
    images = scan_images()
    return jsonify({"images": images, "count": len(images)})


@app.post("/api/run")
def api_run() -> Any:
    payload = request.get_json(silent=True) or {}
    client_id = str(payload.get("client_id", "")).strip()
    client_secret = str(payload.get("client_secret", "")).strip()
    usernames_raw = str(payload.get("usernames", "")).strip()
    usernames = parse_usernames(usernames_raw)

    if not client_id or not client_secret or not usernames:
        return (
            jsonify(
                {
                    "ok": False,
                    "message": "client_id, client_secret, and usernames are required.",
                }
            ),
            400,
        )

    if not run_lock.acquire(blocking=False):
        return jsonify({"ok": False, "message": "A download job is already running."}), 409

    try:
        config = build_runtime_config(client_id, client_secret, usernames)
        result = run_download_job(config)
        response = {
            "ok": len(result["errors"]) == 0,
            "stats": result["stats"],
            "errors": result["errors"],
            "gallery_count": len(scan_images()),
        }
        return jsonify(response), 200
    finally:
        run_lock.release()


@app.get("/downloads/<path:filename>")
def serve_download(filename: str) -> Any:
    return send_from_directory(DOWNLOADS_DIR, filename)


def main() -> None:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
