from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

from .api import DeviantArtApiError, DeviantArtClient
from .config import AppConfig, parse_config
from .storage import build_output_path, ensure_user_state, load_state, save_state


def process_user_once(
    config: AppConfig,
    client: DeviantArtClient,
    state: Dict[str, Any],
    username: str,
) -> Dict[str, int]:
    user_state = ensure_user_state(state, username)
    seen_ids = user_state.get("seen_ids", [])

    # Use a set for fast membership checks while keeping list order for persisted state.
    seen_set = set(seen_ids)

    offset = 0
    pages_checked = 0
    new_items = 0
    downloaded = 0
    existing = 0
    skipped = 0

    for _ in range(config.pages):
        pages_checked += 1
        page = client.fetch_gallery_page(
            username=username,
            offset=offset,
            limit=config.limit,
            include_mature=config.include_mature,
        )
        results = page.get("results") or []
        if not isinstance(results, list):
            break

        for item in results:
            if not isinstance(item, dict):
                continue

            deviation_id = str(item.get("deviationid", "")).strip()
            if not deviation_id or deviation_id in seen_set:
                continue

            seen_set.add(deviation_id)
            seen_ids.append(deviation_id)
            new_items += 1

            title = str(item.get("title") or deviation_id)
            if config.seed_only:
                logging.info("SEED @%s %s | %s", username, deviation_id, title)
                continue

            if item.get("is_deleted"):
                skipped += 1
                logging.info("SKIP deleted @%s %s | %s", username, deviation_id, title)
                continue

            download_url = ""
            preferred_name: Optional[str] = None

            if item.get("is_downloadable"):
                try:
                    info = client.fetch_download_info(deviation_id, config.include_mature)
                    download_url = str(info.get("src") or "")
                    preferred_name = str(info.get("filename") or "") or None
                except DeviantArtApiError as exc:
                    logging.warning(
                        "Original download unavailable for @%s %s: %s",
                        username,
                        deviation_id,
                        exc,
                    )

            # Fallback for posts where original download is disabled by the artist.
            if not download_url and config.allow_preview:
                content = item.get("content")
                if isinstance(content, dict):
                    download_url = str(content.get("src") or "")

            if not download_url:
                skipped += 1
                logging.info(
                    "SKIP no downloadable image @%s %s | %s (use --allow-preview to save preview/content images)",
                    username,
                    deviation_id,
                    title,
                )
                continue

            output_path = build_output_path(
                output_dir=config.output_dir,
                username=username,
                deviation_id=deviation_id,
                title=title,
                source_url=download_url,
                preferred_filename=preferred_name,
            )

            try:
                created = client.download_file(download_url, output_path)
            except requests.RequestException as exc:
                skipped += 1
                logging.warning("Download failed for @%s %s | %s: %s", username, deviation_id, title, exc)
                continue

            if created:
                downloaded += 1
                logging.info("DOWNLOADED @%s %s | %s -> %s", username, deviation_id, title, output_path)
            else:
                existing += 1
                logging.info("EXISTS @%s %s | %s -> %s", username, deviation_id, title, output_path)

        if not page.get("has_more"):
            break
        next_offset = page.get("next_offset")
        if next_offset is None:
            break
        offset = int(next_offset)

    if len(seen_ids) > config.max_seen:
        # Trim old IDs to keep state file bounded over long-running usage.
        user_state["seen_ids"] = seen_ids[-config.max_seen :]

    return {
        "pages_checked": pages_checked,
        "new_items": new_items,
        "downloaded": downloaded,
        "existing": existing,
        "skipped": skipped,
    }


def run() -> int:
    config = parse_config()
    logging.basicConfig(
        level=logging.DEBUG if config.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    state = load_state(config.state_file)
    client = DeviantArtClient(
        client_id=config.client_id,
        client_secret=config.client_secret,
        user_agent=config.user_agent,
        timeout=config.timeout,
    )

    while True:
        started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        targets = ", ".join(f"@{username}" for username in config.usernames)
        logging.info("Checking %s at %s", targets, started_at)

        cycle_stats = {
            "users_checked": 0,
            "pages_checked": 0,
            "new_items": 0,
            "downloaded": 0,
            "existing": 0,
            "skipped": 0,
        }
        had_errors = False

        for username in config.usernames:
            logging.info("Checking @%s", username)
            try:
                stats = process_user_once(config, client, state, username)
                cycle_stats["users_checked"] += 1
                cycle_stats["pages_checked"] += stats["pages_checked"]
                cycle_stats["new_items"] += stats["new_items"]
                cycle_stats["downloaded"] += stats["downloaded"]
                cycle_stats["existing"] += stats["existing"]
                cycle_stats["skipped"] += stats["skipped"]
                logging.info(
                    "Finished @%s | pages=%s new=%s downloaded=%s existing=%s skipped=%s",
                    username,
                    stats["pages_checked"],
                    stats["new_items"],
                    stats["downloaded"],
                    stats["existing"],
                    stats["skipped"],
                )
            except DeviantArtApiError as exc:
                had_errors = True
                logging.error("API error for @%s: %s", username, exc)
            except requests.RequestException as exc:
                had_errors = True
                logging.error("Network error for @%s: %s", username, exc)

        save_state(config.state_file, state)
        logging.info(
            "Finished cycle | users=%s pages=%s new=%s downloaded=%s existing=%s skipped=%s",
            cycle_stats["users_checked"],
            cycle_stats["pages_checked"],
            cycle_stats["new_items"],
            cycle_stats["downloaded"],
            cycle_stats["existing"],
            cycle_stats["skipped"],
        )

        if config.interval == 0:
            return 1 if had_errors else 0
        time.sleep(config.interval)

