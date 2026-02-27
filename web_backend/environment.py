"""Shared environment and filesystem objects for the Flask web app.

Variables in this module:
- `BASE_DIR`: project root path used to resolve relative files.
- `ENV_FILE`: `.env` file path loaded once at import time.
- `DOWNLOADS_DIR`: root folder that stores downloaded images.
- `LEGACY_STATE_FILE`: old state file path used for migration.
- `IMAGE_EXTENSIONS`: allowed image file suffixes for gallery sync.
- `DB_FILE`: resolved SQLite database file path.
- `DATABASE`: shared `WatcherDatabase` instance used by routes/services.

How this module works:
1. Loads `.env` once, then resolves all runtime paths.
2. Creates one reusable DB object.
3. Exposes `bootstrap_database()` to run migration and filesystem sync.
"""

from __future__ import annotations

import os
from pathlib import Path

from da_watcher.database import WatcherDatabase
from da_watcher.env_utils import load_env_file

BASE_DIR = Path(__file__).resolve().parent.parent
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


def bootstrap_database() -> None:
    DATABASE.migrate_from_state_json(LEGACY_STATE_FILE)
    DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
    DATABASE.sync_images_from_filesystem(DOWNLOADS_DIR, IMAGE_EXTENSIONS)
