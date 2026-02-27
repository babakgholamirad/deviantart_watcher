from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any, Iterable, List, Optional, Set

import requests

from .api import DeviantArtApiError, DeviantArtClient
from .config import AppConfig, parse_config
from .database import WatcherDatabase
from .storage import build_output_path, sanitize_filename

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".avif"}


def collect_local_deviation_ids(output_dir: Path, username: str) -> Set[str]:
    user_dir = output_dir / sanitize_filename(username, fallback="user")
    if not user_dir.exists() or not user_dir.is_dir():
        return set()

    ids: Set[str] = set()
    for path in user_dir.iterdir():
        if not path.is_file():
            continue
        separator_index = path.name.find("_")
        if separator_index <= 0:
            continue
        ids.add(path.name[:separator_index])
    return ids


def normalize_tags(values: Iterable[str]) -> List[str]:
    normalized: List[str] = []
    seen: Set[str] = set()
    for value in values:
        tag = str(value).strip()
        if not tag:
            continue
        key = tag.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(tag)
    return normalized


def extract_tags(raw_value: Any) -> List[str]:
    if not isinstance(raw_value, list):
        return []

    extracted: List[str] = []
    for item in raw_value:
        if isinstance(item, str):
            extracted.append(item)
            continue
        if not isinstance(item, dict):
            continue

        for key in ("tag_name", "tag", "name", "title"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                extracted.append(value)
                break

    return normalize_tags(extracted)


def extract_item_tags(item: Any) -> List[str]:
    if not isinstance(item, dict):
        return []

    direct_tags = extract_tags(item.get("tags"))
    if direct_tags:
        return direct_tags

    metadata = item.get("metadata")
    if isinstance(metadata, dict):
        metadata_tags = extract_tags(metadata.get("tags"))
        if metadata_tags:
            return metadata_tags

    return []


def process_user_once(
    config: AppConfig,
    client: DeviantArtClient,
    db: WatcherDatabase,
    username: str,
    start_page: int = 1,
    end_page: Optional[int] = None,
    page_size: Optional[int] = None,
) -> dict[str, int]:
    seen_set = db.get_seen_ids(username)
    seeded_set = db.get_seeded_ids(username)
    processed_this_run = set()
    local_ids = collect_local_deviation_ids(config.output_dir, username)

    effective_limit = page_size if page_size is not None else config.limit
    effective_limit = max(1, min(24, int(effective_limit)))

    normalized_start_page = max(1, int(start_page))
    if end_page is None:
        normalized_end_page = normalized_start_page + max(1, config.pages) - 1
    else:
        normalized_end_page = max(normalized_start_page, int(end_page))

    max_pages = normalized_end_page - normalized_start_page + 1

    def unmark_seen(deviation_id: str) -> None:
        db.remove_seen_ids(username, [deviation_id])
        seen_set.discard(deviation_id)
        seeded_set.discard(deviation_id)

    def mark_seen(deviation_id: str, seeded: bool) -> None:
        db.upsert_seen(username, deviation_id, seeded=seeded)
        seen_set.add(deviation_id)
        if seeded:
            seeded_set.add(deviation_id)
        else:
            seeded_set.discard(deviation_id)

    if not config.seed_only:
        stale_ids = [
            deviation_id
            for deviation_id in seen_set
            if deviation_id not in seeded_set and deviation_id not in local_ids
        ]
        if stale_ids:
            db.remove_seen_ids(username, stale_ids)
            for deviation_id in stale_ids:
                seen_set.discard(deviation_id)
                seeded_set.discard(deviation_id)
            logging.info(
                "Recovered %s stale seen IDs for @%s (missing local files).",
                len(stale_ids),
                username,
            )

    offset = (normalized_start_page - 1) * effective_limit
    pages_checked = 0
    new_items = 0
    downloaded = 0
    existing = 0
    skipped = 0

    for _ in range(max_pages):
        pages_checked += 1
        page = client.fetch_gallery_page(
            username=username,
            offset=offset,
            limit=effective_limit,
            include_mature=config.include_mature,
        )
        results = page.get("results") or []
        if not isinstance(results, list):
            break

        for item in results:
            if not isinstance(item, dict):
                continue

            deviation_id = str(item.get("deviationid", "")).strip()
            if not deviation_id or deviation_id in processed_this_run:
                continue

            if deviation_id in seen_set:
                if deviation_id in seeded_set or deviation_id in local_ids:
                    continue
                unmark_seen(deviation_id)

            processed_this_run.add(deviation_id)
            new_items += 1

            title = str(item.get("title") or deviation_id).strip() or deviation_id
            if config.seed_only:
                mark_seen(deviation_id, seeded=True)
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

            tags = extract_item_tags(item)
            if not tags:
                try:
                    deviation_data = client.fetch_deviation(deviation_id, config.include_mature)
                    tags = extract_item_tags(deviation_data)
                except DeviantArtApiError as exc:
                    logging.debug("Could not fetch tags for @%s %s: %s", username, deviation_id, exc)

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

            mark_seen(deviation_id, seeded=False)
            local_ids.add(deviation_id)
            db.upsert_image(
                username,
                deviation_id,
                output_path,
                config.output_dir,
                image_title=title,
                tags=tags,
            )
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

    db.trim_seen(username, config.max_seen)

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

    db = WatcherDatabase(config.state_file)

    legacy_state = Path(os.getenv("STATE_FILE", "state.json").strip() or "state.json")
    if legacy_state.suffix.lower() == ".json":
        migration_stats = db.migrate_from_state_json(legacy_state)
        if migration_stats["seen_rows"]:
            logging.info(
                "Migrated %s seen rows from %s into %s",
                migration_stats["seen_rows"],
                legacy_state,
                config.state_file,
            )

    db.sync_images_from_filesystem(config.output_dir, IMAGE_EXTENSIONS)

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
                stats = process_user_once(config, client, db, username)
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

        db.sync_images_from_filesystem(config.output_dir, IMAGE_EXTENSIONS)
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


