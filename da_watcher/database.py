from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Set

from .storage import sanitize_filename


class WatcherDatabase:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS artists (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS seen_deviations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist_id INTEGER NOT NULL,
                    deviation_id TEXT NOT NULL,
                    seeded INTEGER NOT NULL DEFAULT 0 CHECK (seeded IN (0, 1)),
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(artist_id, deviation_id),
                    FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_seen_deviations_artist_id
                ON seen_deviations(artist_id);

                CREATE TABLE IF NOT EXISTS images (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    artist_id INTEGER NOT NULL,
                    deviation_id TEXT NOT NULL,
                    relative_path TEXT NOT NULL UNIQUE,
                    file_size INTEGER NOT NULL DEFAULT 0,
                    mtime INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (artist_id) REFERENCES artists(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_images_artist_id
                ON images(artist_id);
                """
            )

    def _get_artist_id(self, connection: sqlite3.Connection, username: str) -> int | None:
        row = connection.execute(
            "SELECT id FROM artists WHERE username = ?",
            (username,),
        ).fetchone()
        return int(row["id"]) if row else None

    def _get_or_create_artist_id(self, connection: sqlite3.Connection, username: str) -> int:
        artist_id = self._get_artist_id(connection, username)
        if artist_id is not None:
            return artist_id

        cursor = connection.execute(
            "INSERT INTO artists (username) VALUES (?)",
            (username,),
        )
        return int(cursor.lastrowid)

    def migrate_from_state_json(self, state_json_path: Path) -> Dict[str, int]:
        if not state_json_path.exists() or state_json_path.suffix.lower() != ".json":
            return {"users": 0, "seen_rows": 0}

        try:
            data = json.loads(state_json_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"users": 0, "seen_rows": 0}

        if not isinstance(data, dict):
            return {"users": 0, "seen_rows": 0}

        users = data.get("users")
        if not isinstance(users, dict):
            return {"users": 0, "seen_rows": 0}

        migrated_users = 0
        migrated_rows = 0

        with self._connect() as connection:
            for username, user_state in users.items():
                if not isinstance(username, str) or not username.strip():
                    continue
                if not isinstance(user_state, dict):
                    continue

                seen_ids = user_state.get("seen_ids", [])
                if not isinstance(seen_ids, list):
                    continue
                seeded_ids_raw = user_state.get("seeded_ids", [])
                seeded_ids = set(seeded_ids_raw) if isinstance(seeded_ids_raw, list) else set()

                artist_id = self._get_or_create_artist_id(connection, username)
                migrated_users += 1

                for deviation_id in seen_ids:
                    deviation_id_str = str(deviation_id).strip()
                    if not deviation_id_str:
                        continue
                    seeded = 1 if deviation_id_str in seeded_ids else 0
                    connection.execute(
                        """
                        INSERT INTO seen_deviations (artist_id, deviation_id, seeded)
                        VALUES (?, ?, ?)
                        ON CONFLICT(artist_id, deviation_id)
                        DO UPDATE SET seeded = excluded.seeded
                        """,
                        (artist_id, deviation_id_str, seeded),
                    )
                    migrated_rows += 1

        return {"users": migrated_users, "seen_rows": migrated_rows}

    def get_seen_ids(self, username: str) -> Set[str]:
        with self._connect() as connection:
            artist_id = self._get_artist_id(connection, username)
            if artist_id is None:
                return set()

            rows = connection.execute(
                "SELECT deviation_id FROM seen_deviations WHERE artist_id = ?",
                (artist_id,),
            ).fetchall()
            return {str(row["deviation_id"]) for row in rows}

    def get_seeded_ids(self, username: str) -> Set[str]:
        with self._connect() as connection:
            artist_id = self._get_artist_id(connection, username)
            if artist_id is None:
                return set()

            rows = connection.execute(
                "SELECT deviation_id FROM seen_deviations WHERE artist_id = ? AND seeded = 1",
                (artist_id,),
            ).fetchall()
            return {str(row["deviation_id"]) for row in rows}

    def upsert_seen(self, username: str, deviation_id: str, seeded: bool) -> None:
        with self._connect() as connection:
            artist_id = self._get_or_create_artist_id(connection, username)
            connection.execute(
                """
                INSERT INTO seen_deviations (artist_id, deviation_id, seeded)
                VALUES (?, ?, ?)
                ON CONFLICT(artist_id, deviation_id)
                DO UPDATE SET seeded = excluded.seeded
                """,
                (artist_id, deviation_id, 1 if seeded else 0),
            )

    def remove_seen_ids(self, username: str, deviation_ids: Iterable[str]) -> None:
        ids = [str(item).strip() for item in deviation_ids if str(item).strip()]
        if not ids:
            return

        with self._connect() as connection:
            artist_id = self._get_artist_id(connection, username)
            if artist_id is None:
                return

            placeholders = ",".join("?" for _ in ids)
            connection.execute(
                f"DELETE FROM seen_deviations WHERE artist_id = ? AND deviation_id IN ({placeholders})",
                (artist_id, *ids),
            )

    def trim_seen(self, username: str, max_seen: int) -> None:
        if max_seen < 1:
            return

        with self._connect() as connection:
            artist_id = self._get_artist_id(connection, username)
            if artist_id is None:
                return

            connection.execute(
                """
                DELETE FROM seen_deviations
                WHERE artist_id = ?
                  AND id NOT IN (
                      SELECT id
                      FROM seen_deviations
                      WHERE artist_id = ?
                      ORDER BY id DESC
                      LIMIT ?
                  )
                """,
                (artist_id, artist_id, max_seen),
            )

    def upsert_image(self, username: str, deviation_id: str, file_path: Path, output_dir: Path) -> None:
        if not file_path.exists() or not file_path.is_file():
            return

        relative_path = file_path.relative_to(output_dir).as_posix()
        stats = file_path.stat()

        with self._connect() as connection:
            artist_id = self._get_or_create_artist_id(connection, username)
            connection.execute(
                """
                INSERT INTO images (artist_id, deviation_id, relative_path, file_size, mtime)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(relative_path)
                DO UPDATE SET
                    artist_id = excluded.artist_id,
                    deviation_id = excluded.deviation_id,
                    file_size = excluded.file_size,
                    mtime = excluded.mtime,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (artist_id, deviation_id, relative_path, int(stats.st_size), int(stats.st_mtime)),
            )

    def sync_images_from_filesystem(self, output_dir: Path, image_extensions: Set[str]) -> Dict[str, int]:
        output_dir.mkdir(parents=True, exist_ok=True)

        discovered: Dict[str, Dict[str, Any]] = {}
        for path in output_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in image_extensions:
                continue

            relative_path = path.relative_to(output_dir).as_posix()
            parts = relative_path.split("/")
            artist = parts[0] if len(parts) > 1 else "ungrouped"
            separator_index = path.name.find("_")
            deviation_id = path.name[:separator_index] if separator_index > 0 else path.stem
            stats = path.stat()

            discovered[relative_path] = {
                "artist": artist,
                "deviation_id": deviation_id,
                "size": int(stats.st_size),
                "mtime": int(stats.st_mtime),
            }

        with self._connect() as connection:
            existing_rows = connection.execute("SELECT relative_path FROM images").fetchall()
            existing_paths = {str(row["relative_path"]) for row in existing_rows}
            discovered_paths = set(discovered.keys())

            missing_paths = list(existing_paths - discovered_paths)
            if missing_paths:
                placeholders = ",".join("?" for _ in missing_paths)
                connection.execute(
                    f"DELETE FROM images WHERE relative_path IN ({placeholders})",
                    tuple(missing_paths),
                )

            for relative_path, payload in discovered.items():
                artist_id = self._get_or_create_artist_id(connection, payload["artist"])
                connection.execute(
                    """
                    INSERT INTO images (artist_id, deviation_id, relative_path, file_size, mtime)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(relative_path)
                    DO UPDATE SET
                        artist_id = excluded.artist_id,
                        deviation_id = excluded.deviation_id,
                        file_size = excluded.file_size,
                        mtime = excluded.mtime,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        artist_id,
                        payload["deviation_id"],
                        relative_path,
                        payload["size"],
                        payload["mtime"],
                    ),
                )

        return {
            "discovered": len(discovered),
            "deleted_stale": len(existing_paths - set(discovered.keys())),
        }

    def get_gallery_data(self) -> Dict[str, Any]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT
                    artists.username AS artist,
                    images.deviation_id AS deviation_id,
                    images.relative_path AS relative_path,
                    images.file_size AS file_size,
                    images.mtime AS mtime
                FROM images
                INNER JOIN artists ON artists.id = images.artist_id
                ORDER BY images.mtime DESC, images.id DESC
                """
            ).fetchall()

        images: List[Dict[str, Any]] = []
        groups_map: Dict[str, List[Dict[str, Any]]] = {}

        for row in rows:
            artist = str(row["artist"])
            relative_path = str(row["relative_path"])
            image = {
                "artist": artist,
                "deviation_id": str(row["deviation_id"]),
                "name": Path(relative_path).name,
                "relative_path": relative_path,
                "url": f"/downloads/{relative_path}",
                "mtime": int(row["mtime"]),
                "size_bytes": int(row["file_size"]),
            }
            images.append(image)
            groups_map.setdefault(artist, []).append(image)

        groups: List[Dict[str, Any]] = []
        for artist in sorted(groups_map.keys(), key=str.lower):
            group_images = groups_map[artist]
            groups.append({"artist": artist, "count": len(group_images), "images": group_images})

        return {"images": images, "groups": groups, "count": len(images), "group_count": len(groups)}

    def delete_image(self, relative_path: str, output_dir: Path) -> Dict[str, Any]:
        cleaned_relative_path = str(Path(relative_path).as_posix()).lstrip("/")
        if not cleaned_relative_path:
            return {"deleted": False, "message": "relative_path is required."}

        target_path = (output_dir / cleaned_relative_path).resolve()
        base_path = output_dir.resolve()
        if base_path not in target_path.parents and target_path != base_path:
            return {"deleted": False, "message": "Invalid relative_path."}

        file_deleted = False
        if target_path.exists() and target_path.is_file():
            target_path.unlink()
            file_deleted = True

        artist = ""
        deviation_id = ""
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT artists.username AS artist, images.deviation_id AS deviation_id
                FROM images
                INNER JOIN artists ON artists.id = images.artist_id
                WHERE images.relative_path = ?
                """,
                (cleaned_relative_path,),
            ).fetchone()

            if row:
                artist = str(row["artist"])
                deviation_id = str(row["deviation_id"])

            connection.execute(
                "DELETE FROM images WHERE relative_path = ?",
                (cleaned_relative_path,),
            )

            if artist and deviation_id:
                artist_id = self._get_artist_id(connection, artist)
                if artist_id is not None:
                    connection.execute(
                        "DELETE FROM seen_deviations WHERE artist_id = ? AND deviation_id = ?",
                        (artist_id, deviation_id),
                    )

        return {
            "deleted": file_deleted or bool(artist),
            "artist": artist,
            "deviation_id": deviation_id,
            "relative_path": cleaned_relative_path,
        }

    def delete_artist_images(self, username: str, output_dir: Path) -> Dict[str, Any]:
        username_clean = username.strip()
        if not username_clean:
            return {"deleted": False, "message": "artist is required.", "deleted_files": 0}

        user_dir = output_dir / sanitize_filename(username_clean, fallback="user")
        deleted_files = 0

        with self._connect() as connection:
            artist_id = self._get_artist_id(connection, username_clean)
            if artist_id is None:
                # Fallback: remove folder if present even when DB has no artist row.
                if user_dir.exists() and user_dir.is_dir():
                    for file_path in user_dir.rglob("*"):
                        if file_path.is_file():
                            file_path.unlink()
                            deleted_files += 1
                    for child in sorted(user_dir.rglob("*"), reverse=True):
                        if child.is_dir():
                            child.rmdir()
                    user_dir.rmdir()
                return {"deleted": deleted_files > 0, "artist": username_clean, "deleted_files": deleted_files}

            rows = connection.execute(
                "SELECT relative_path FROM images WHERE artist_id = ?",
                (artist_id,),
            ).fetchall()
            relative_paths = [str(row["relative_path"]) for row in rows]

            for relative_path in relative_paths:
                file_path = output_dir / relative_path
                if file_path.exists() and file_path.is_file():
                    file_path.unlink()
                    deleted_files += 1

            connection.execute("DELETE FROM images WHERE artist_id = ?", (artist_id,))
            connection.execute("DELETE FROM seen_deviations WHERE artist_id = ?", (artist_id,))

        if user_dir.exists() and user_dir.is_dir():
            for child in sorted(user_dir.rglob("*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
            user_dir.rmdir()

        return {"deleted": deleted_files > 0, "artist": username_clean, "deleted_files": deleted_files}
