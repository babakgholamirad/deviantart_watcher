#!/usr/bin/env python3
"""Local web UI for running the downloader and browsing downloaded images."""

from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from flask import Flask, jsonify, request, send_from_directory

from da_watcher.api import DEFAULT_USER_AGENT, DeviantArtApiError, DeviantArtClient
from da_watcher.config import AppConfig
from da_watcher.database import WatcherDatabase
from da_watcher.env_utils import load_env_file, parse_bool, parse_csv_values
from da_watcher.watcher import process_user_once

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"
load_env_file(ENV_FILE)

DOWNLOADS_DIR = BASE_DIR / os.getenv("OUTPUT_DIR", "downloads")
LEGACY_STATE_FILE = BASE_DIR / (os.getenv("STATE_FILE", "state.json").strip() or "state.json")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}


def resolve_db_path() -> Path:
    explicit = os.getenv("DB_FILE", "").strip()
    if explicit:
        return BASE_DIR / explicit

    legacy = os.getenv("STATE_FILE", "state.json").strip() or "state.json"
    legacy_path = Path(legacy)
    if legacy_path.suffix.lower() == ".json":
        return BASE_DIR / legacy_path.with_suffix(".db")
    if legacy_path.suffix.lower() == ".db":
        return BASE_DIR / legacy_path
    return BASE_DIR / "state.db"


DB_FILE = resolve_db_path()
DATABASE = WatcherDatabase(DB_FILE)

app = Flask(__name__, static_folder=str(BASE_DIR), static_url_path="")
run_lock = threading.Lock()


def bootstrap_database() -> None:
    DATABASE.migrate_from_state_json(LEGACY_STATE_FILE)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE.sync_images_from_filesystem(DOWNLOADS_DIR, IMAGE_EXTENSIONS)


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


def build_runtime_config(
    client_id: str,
    client_secret: str,
    usernames: List[str],
    include_mature: bool,
    allow_preview: bool,
    seed_only: bool,
    verbose: bool,
    page_size: int,
    pages: int,
) -> AppConfig:
    return AppConfig(
        client_id=client_id,
        client_secret=client_secret,
        usernames=usernames,
        output_dir=DOWNLOADS_DIR,
        state_file=DB_FILE,
        pages=pages,
        limit=page_size,
        interval=0,
        include_mature=include_mature,
        allow_preview=allow_preview,
        seed_only=seed_only,
        max_seen=max(100, env_int("MAX_SEEN_IDS", 5000)),
        timeout=max(5, env_int("REQUEST_TIMEOUT_SECONDS", 30)),
        user_agent=os.getenv("USER_AGENT", DEFAULT_USER_AGENT).strip() or DEFAULT_USER_AGENT,
        verbose=verbose,
    )


def scan_images() -> Dict[str, Any]:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE.sync_images_from_filesystem(DOWNLOADS_DIR, IMAGE_EXTENSIONS)
    return DATABASE.get_gallery_data()


def run_download_job(
    config: AppConfig,
    start_page: int,
    end_page: int,
    page_size: int,
) -> Dict[str, Any]:
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
            stats = process_user_once(
                config,
                client,
                DATABASE,
                username,
                start_page=start_page,
                end_page=end_page,
                page_size=page_size,
            )
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

    DATABASE.sync_images_from_filesystem(DOWNLOADS_DIR, IMAGE_EXTENSIONS)
    return {"stats": cycle_stats, "errors": errors}


@app.get("/")
def home() -> Any:
    return send_from_directory(BASE_DIR, "index.html")


@app.get("/api/defaults")
def api_defaults() -> Any:
    default_page_size = max(1, min(24, env_int("PAGE_SIZE", 24)))
    default_end_page = max(1, env_int("PAGES_PER_CHECK", 3))

    return jsonify(
        {
            "client_id": os.getenv("DA_CLIENT_ID", ""),
            "client_secret": os.getenv("DA_CLIENT_SECRET", ""),
            "usernames": os.getenv("DA_USERNAMES", os.getenv("DA_USERNAME", "")),
            "include_mature": env_bool("INCLUDE_MATURE", False),
            "allow_preview": env_bool("ALLOW_PREVIEW", False),
            "seed_only": env_bool("SEED_ONLY", False),
            "verbose": env_bool("VERBOSE", False),
            "start_page": 1,
            "end_page": default_end_page,
            "page_size": default_page_size,
        }
    )


@app.get("/api/gallery")
def api_gallery() -> Any:
    return jsonify(scan_images())


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

    include_mature = payload_bool(payload, "include_mature", env_bool("INCLUDE_MATURE", False))
    allow_preview = payload_bool(payload, "allow_preview", env_bool("ALLOW_PREVIEW", False))
    seed_only = payload_bool(payload, "seed_only", env_bool("SEED_ONLY", False))
    verbose = payload_bool(payload, "verbose", env_bool("VERBOSE", False))

    page_size = payload_int(payload, "page_size", env_int("PAGE_SIZE", 24), minimum=1, maximum=24)
    start_page = payload_int(payload, "start_page", 1, minimum=1)
    end_page = payload_int(payload, "end_page", max(1, env_int("PAGES_PER_CHECK", 3)), minimum=1)

    if end_page < start_page:
        return jsonify({"ok": False, "message": "end_page must be greater than or equal to start_page."}), 400

    pages = end_page - start_page + 1
    if pages > 200:
        return jsonify({"ok": False, "message": "Requested page range is too large (max 200 pages)."}), 400

    if not run_lock.acquire(blocking=False):
        return jsonify({"ok": False, "message": "A download job is already running."}), 409

    try:
        config = build_runtime_config(
            client_id=client_id,
            client_secret=client_secret,
            usernames=usernames,
            include_mature=include_mature,
            allow_preview=allow_preview,
            seed_only=seed_only,
            verbose=verbose,
            page_size=page_size,
            pages=pages,
        )
        result = run_download_job(
            config=config,
            start_page=start_page,
            end_page=end_page,
            page_size=page_size,
        )
        gallery = scan_images()
        response = {
            "ok": len(result["errors"]) == 0,
            "stats": result["stats"],
            "errors": result["errors"],
            "gallery_count": gallery["count"],
            "group_count": gallery["group_count"],
            "pagination": {
                "start_page": start_page,
                "end_page": end_page,
                "page_size": page_size,
                "pages": pages,
            },
        }
        return jsonify(response), 200
    finally:
        run_lock.release()


@app.post("/api/delete/image")
def api_delete_image() -> Any:
    payload = request.get_json(silent=True) or {}
    relative_path = str(payload.get("relative_path", "")).strip()
    if not relative_path:
        return jsonify({"ok": False, "message": "relative_path is required."}), 400

    if not run_lock.acquire(blocking=False):
        return jsonify({"ok": False, "message": "A download job is already running."}), 409

    try:
        result = DATABASE.delete_image(relative_path, DOWNLOADS_DIR)
        gallery = scan_images()
        if not result.get("deleted"):
            return jsonify({"ok": False, "message": "Image not found.", "result": result}), 404

        return jsonify(
            {
                "ok": True,
                "result": result,
                "gallery_count": gallery["count"],
                "group_count": gallery["group_count"],
            }
        )
    finally:
        run_lock.release()


@app.post("/api/delete/artist")
def api_delete_artist() -> Any:
    payload = request.get_json(silent=True) or {}
    artist = str(payload.get("artist", "")).strip()
    if not artist:
        return jsonify({"ok": False, "message": "artist is required."}), 400

    if not run_lock.acquire(blocking=False):
        return jsonify({"ok": False, "message": "A download job is already running."}), 409

    try:
        result = DATABASE.delete_artist_images(artist, DOWNLOADS_DIR)
        gallery = scan_images()
        if not result.get("deleted"):
            return jsonify({"ok": False, "message": "No images found for this artist.", "result": result}), 404

        return jsonify(
            {
                "ok": True,
                "result": result,
                "gallery_count": gallery["count"],
                "group_count": gallery["group_count"],
            }
        )
    finally:
        run_lock.release()


@app.get("/downloads/<path:filename>")
def serve_download(filename: str) -> Any:
    return send_from_directory(DOWNLOADS_DIR, filename)


def main() -> None:
    bootstrap_database()
    app.run(host="127.0.0.1", port=5000, debug=False)


bootstrap_database()

if __name__ == "__main__":
    main()
