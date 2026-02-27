"""Download execution helpers used by Flask routes.

Variables and behavior:
- Reads runtime env defaults (`MAX_SEEN_IDS`, `REQUEST_TIMEOUT_SECONDS`, `USER_AGENT`).
- Uses shared `DATABASE`, `DOWNLOADS_DIR`, and `IMAGE_EXTENSIONS` from `environment`.
- Builds `AppConfig`, runs each artist fetch, and updates job state on completion.

How this module works:
1. `build_runtime_config` composes one execution config from request + env defaults.
2. `run_download_job` processes all usernames and aggregates counters/errors.
3. `run_download_job_worker` wraps execution and writes final job status.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List

import requests

from da_watcher.api import DEFAULT_USER_AGENT, DeviantArtApiError, DeviantArtClient
from da_watcher.config import AppConfig
from da_watcher.watcher import process_user_once
from web_backend.environment import DATABASE, DB_FILE, DOWNLOADS_DIR, IMAGE_EXTENSIONS
from web_backend.job_state import DownloadJobState, default_stats
from web_backend.parsing import env_int


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


def scan_images(search_query: str = "", favorites_only: bool = False) -> Dict[str, Any]:
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE.sync_images_from_filesystem(DOWNLOADS_DIR, IMAGE_EXTENSIONS)
    return DATABASE.get_gallery_data(search_query=search_query, favorites_only=favorites_only)


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

    cycle_stats = default_stats()
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


def run_download_job_worker(
    job_state: DownloadJobState,
    job_id: int,
    config: AppConfig,
    start_page: int,
    end_page: int,
    page_size: int,
) -> None:
    try:
        result = run_download_job(
            config=config,
            start_page=start_page,
            end_page=end_page,
            page_size=page_size,
        )
        gallery = scan_images()
        errors = list(result.get("errors") or [])
        stats = dict(result.get("stats") or default_stats())
        ok = len(errors) == 0
        message = "Download job completed." if ok else "Download job completed with errors."

        job_state.finish(
            job_id=job_id,
            ok=ok,
            message=message,
            stats=stats,
            errors=errors,
            gallery_count=int(gallery.get("count") or 0),
            group_count=int(gallery.get("group_count") or 0),
        )
    except Exception as exc:
        job_state.finish(
            job_id=job_id,
            ok=False,
            message="Download job failed unexpectedly.",
            stats=default_stats(),
            errors=[str(exc)],
            gallery_count=0,
            group_count=0,
        )
