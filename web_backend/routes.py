"""Flask route registration for API endpoints and static download serving.

Variables and behavior:
- Routes read env/defaults, parse payloads, and call service layer functions.
- A single module-local `download_thread` reference tracks the latest worker thread.
- All endpoints return JSON payloads expected by the current frontend.

How this module works:
1. `register_routes(app, job_state)` wires all endpoint handlers.
2. `POST /api/run` starts a background thread and returns immediately.
3. `GET /api/job/status` exposes running/completed state across page refreshes.
"""

from __future__ import annotations

import os
import threading
from typing import Any, Optional

from flask import Flask, jsonify, request, send_from_directory

from da_watcher.env_utils import parse_bool
from web_backend.environment import BASE_DIR, DATABASE, DOWNLOADS_DIR
from web_backend.job_state import DownloadJobState
from web_backend.parsing import env_bool, env_int, parse_usernames, payload_bool, payload_int
from web_backend.services import build_runtime_config, run_download_job_worker, scan_images


def register_routes(app: Flask, job_state: DownloadJobState) -> None:
    download_thread: Optional[threading.Thread] = None

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
        query = str(request.args.get("q", "")).strip()
        favorites_raw = str(request.args.get("favorites_only", "")).strip()
        favorites_only = False
        if favorites_raw:
            try:
                favorites_only = parse_bool(favorites_raw)
            except ValueError:
                favorites_only = favorites_raw in {"1", "true", "yes", "on"}
        return jsonify(scan_images(query, favorites_only=favorites_only))

    @app.get("/api/job/status")
    def api_job_status() -> Any:
        return jsonify(job_state.snapshot())

    @app.post("/api/run")
    def api_run() -> Any:
        nonlocal download_thread

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

        pagination = {
            "start_page": start_page,
            "end_page": end_page,
            "page_size": page_size,
            "pages": pages,
        }

        started, snapshot = job_state.try_start(usernames=usernames, pagination=pagination)
        if not started:
            return (
                jsonify(
                    {
                        "ok": False,
                        "message": "A download job is already running.",
                        "job": snapshot,
                    }
                ),
                409,
            )

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

        download_thread = threading.Thread(
            target=run_download_job_worker,
            args=(job_state, int(snapshot["job_id"]), config, start_page, end_page, page_size),
            daemon=True,
        )
        download_thread.start()

        return (
            jsonify(
                {
                    "ok": True,
                    "message": "Download job started.",
                    "job": job_state.snapshot(),
                }
            ),
            202,
        )

    @app.post("/api/delete/image")
    def api_delete_image() -> Any:
        payload = request.get_json(silent=True) or {}
        relative_path = str(payload.get("relative_path", "")).strip()
        if not relative_path:
            return jsonify({"ok": False, "message": "relative_path is required."}), 400

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

    @app.post("/api/delete/artist")
    def api_delete_artist() -> Any:
        payload = request.get_json(silent=True) or {}
        artist = str(payload.get("artist", "")).strip()
        if not artist:
            return jsonify({"ok": False, "message": "artist is required."}), 400

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

    @app.route("/api/favorite/image", methods=["POST", "PUT", "PATCH"], strict_slashes=False)
    def api_favorite_image() -> Any:
        payload = request.get_json(silent=True) or {}
        relative_path = str(payload.get("relative_path", "")).strip()
        if not relative_path:
            return jsonify({"ok": False, "message": "relative_path is required."}), 400

        is_favorite = payload_bool(payload, "is_favorite", False)
        result = DATABASE.set_image_favorite(relative_path, is_favorite)
        if not result.get("updated"):
            return jsonify(
                {
                    "ok": False,
                    "message": result.get("message", "Image not found."),
                    "result": result,
                }
            ), 404

        return jsonify({"ok": True, "result": result})

    @app.get("/downloads/<path:filename>")
    def serve_download(filename: str) -> Any:
        return send_from_directory(DOWNLOADS_DIR, filename)
