"""In-memory job state container for background downloads.

Variables tracked inside `DownloadJobState`:
- `job_id`: monotonically increasing job number.
- `running`: whether a downloader thread is active.
- `started_at` / `finished_at`: UTC timestamps for UI visibility.
- `ok`, `message`, `errors`, `stats`: latest execution result payload.
- `pagination`, `requested_usernames`: job input parameters.
- `gallery_count`, `group_count`: summary snapshot after completion.

How this module works:
- `try_start()` atomically rejects parallel runs and starts new state.
- `finish()` updates the same state only if job IDs match.
- `snapshot()` returns a copy safe for JSON responses.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def default_stats() -> Dict[str, int]:
    return {
        "users_checked": 0,
        "pages_checked": 0,
        "new_items": 0,
        "downloaded": 0,
        "existing": 0,
        "skipped": 0,
    }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class DownloadJobState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._state: Dict[str, Any] = {
            "job_id": 0,
            "running": False,
            "started_at": None,
            "finished_at": None,
            "ok": None,
            "message": "",
            "stats": default_stats(),
            "errors": [],
            "pagination": None,
            "requested_usernames": [],
            "gallery_count": 0,
            "group_count": 0,
        }

    def _snapshot_unlocked(self) -> Dict[str, Any]:
        pagination = self._state.get("pagination")
        return {
            "job_id": int(self._state.get("job_id") or 0),
            "running": bool(self._state.get("running")),
            "started_at": self._state.get("started_at"),
            "finished_at": self._state.get("finished_at"),
            "ok": self._state.get("ok"),
            "message": str(self._state.get("message") or ""),
            "stats": dict(self._state.get("stats") or default_stats()),
            "errors": list(self._state.get("errors") or []),
            "pagination": dict(pagination) if isinstance(pagination, dict) else None,
            "requested_usernames": list(self._state.get("requested_usernames") or []),
            "gallery_count": int(self._state.get("gallery_count") or 0),
            "group_count": int(self._state.get("group_count") or 0),
        }

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return self._snapshot_unlocked()

    def try_start(self, usernames: List[str], pagination: Dict[str, int]) -> Tuple[bool, Dict[str, Any]]:
        with self._lock:
            if bool(self._state.get("running")):
                return False, self._snapshot_unlocked()

            job_id = int(self._state.get("job_id") or 0) + 1
            self._state["job_id"] = job_id
            self._state["running"] = True
            self._state["started_at"] = utc_now_iso()
            self._state["finished_at"] = None
            self._state["ok"] = None
            self._state["message"] = "Download job is running."
            self._state["stats"] = default_stats()
            self._state["errors"] = []
            self._state["pagination"] = dict(pagination)
            self._state["requested_usernames"] = list(usernames)
            return True, self._snapshot_unlocked()

    def finish(
        self,
        job_id: int,
        ok: bool,
        message: str,
        stats: Dict[str, int],
        errors: List[str],
        gallery_count: int,
        group_count: int,
    ) -> None:
        with self._lock:
            if int(self._state.get("job_id") or 0) != int(job_id):
                return

            self._state["running"] = False
            self._state["finished_at"] = utc_now_iso()
            self._state["ok"] = bool(ok)
            self._state["message"] = message
            self._state["stats"] = dict(stats)
            self._state["errors"] = list(errors)
            self._state["gallery_count"] = int(gallery_count)
            self._state["group_count"] = int(group_count)
