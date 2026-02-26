#!/usr/bin/env python3
"""Watch a DeviantArt user's gallery and download newly detected images."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, urlparse

import requests

TOKEN_URL = "https://www.deviantart.com/oauth2/token"
API_BASE = "https://www.deviantart.com/api/v1/oauth2"
DEFAULT_USER_AGENT = "auto-image-downloader/1.0"

INVALID_FILE_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class DeviantArtApiError(RuntimeError):
    """Raised for DeviantArt API failures."""

    def __init__(
        self,
        status_code: int,
        message: str,
        payload: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload or {}


@dataclass
class OAuthToken:
    access_token: str
    expires_at: float


def parse_bool(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value!r}")


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


def env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return parse_bool(value)
    except ValueError as exc:
        raise SystemExit(f"Environment variable {name} must be boolean: {exc}") from exc


def env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise SystemExit(f"Environment variable {name} must be an integer.") from exc


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
        pref = Path(preferred_filename)
        ext = pref.suffix.lower()
        stem = pref.stem

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


class DeviantArtClient:
    def __init__(self, client_id: str, client_secret: str, user_agent: str, timeout: int) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/json",
                "Accept-Encoding": "gzip, deflate",
            }
        )
        self.token: Optional[OAuthToken] = None

    def _request_token(self) -> OAuthToken:
        response = self.session.post(
            TOKEN_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=self.timeout,
        )
        payload = self._parse_json(response)
        if response.status_code >= 400 or "access_token" not in payload:
            raise self._as_api_error(response, payload)

        expires_in = int(payload.get("expires_in", 3600))
        return OAuthToken(
            access_token=str(payload["access_token"]),
            expires_at=time.time() + expires_in,
        )

    def _ensure_token(self) -> None:
        if self.token and self.token.expires_at - time.time() > 60:
            return
        self.token = self._request_token()

    def _parse_json(self, response: requests.Response) -> Dict[str, Any]:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return payload
        except ValueError:
            pass
        return {}

    def _as_api_error(
        self,
        response: requests.Response,
        payload: Optional[Dict[str, Any]] = None,
    ) -> DeviantArtApiError:
        payload = payload or self._parse_json(response)
        detail = payload.get("error_description") or payload.get("error") or response.text.strip()
        message = f"HTTP {response.status_code}: {detail}" if detail else f"HTTP {response.status_code}"
        return DeviantArtApiError(response.status_code, message, payload)

    def api_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._ensure_token()
        assert self.token is not None

        response = self.session.get(
            f"{API_BASE}{path}",
            params=params,
            headers={"Authorization": f"Bearer {self.token.access_token}"},
            timeout=self.timeout,
        )
        payload = self._parse_json(response)
        if response.status_code >= 400:
            raise self._as_api_error(response, payload)
        if "error" in payload:
            raise DeviantArtApiError(response.status_code, str(payload.get("error")), payload)
        return payload

    def fetch_gallery_page(
        self,
        username: str,
        offset: int,
        limit: int,
        include_mature: bool,
    ) -> Dict[str, Any]:
        return self.api_get(
            "/gallery/all",
            params={
                "username": username,
                "offset": offset,
                "limit": limit,
                "mature_content": str(include_mature).lower(),
            },
        )

    def fetch_download_info(self, deviation_id: str, include_mature: bool) -> Dict[str, Any]:
        return self.api_get(
            f"/deviation/download/{deviation_id}",
            params={"mature_content": str(include_mature).lower()},
        )

    def download_file(self, url: str, destination: Path) -> bool:
        if destination.exists():
            return False

        tmp_path = destination.with_suffix(destination.suffix + ".part")
        try:
            with self.session.get(url, stream=True, timeout=self.timeout) as response:
                response.raise_for_status()
                with tmp_path.open("wb") as file_handle:
                    for chunk in response.iter_content(chunk_size=65536):
                        if chunk:
                            file_handle.write(chunk)
            tmp_path.replace(destination)
            return True
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise


def process_once(args: argparse.Namespace, client: DeviantArtClient, state: Dict[str, Any]) -> Dict[str, int]:
    user_state = ensure_user_state(state, args.username)
    seen_ids = user_state.get("seen_ids", [])
    seen_set = set(seen_ids)

    offset = 0
    pages_checked = 0
    new_items = 0
    downloaded = 0
    existing = 0
    skipped = 0

    for _ in range(args.pages):
        pages_checked += 1
        page = client.fetch_gallery_page(
            username=args.username,
            offset=offset,
            limit=args.limit,
            include_mature=args.include_mature,
        )
        results = page.get("results") or []
        if not isinstance(results, list):
            break

        for item in results:
            if not isinstance(item, dict):
                continue

            deviation_id = str(item.get("deviationid", "")).strip()
            if not deviation_id:
                continue
            if deviation_id in seen_set:
                continue

            seen_set.add(deviation_id)
            seen_ids.append(deviation_id)
            new_items += 1

            title = str(item.get("title") or deviation_id)
            if args.seed_only:
                logging.info("SEED %s | %s", deviation_id, title)
                continue

            if item.get("is_deleted"):
                skipped += 1
                logging.info("SKIP deleted %s | %s", deviation_id, title)
                continue

            download_url = ""
            preferred_name: Optional[str] = None

            if item.get("is_downloadable"):
                try:
                    info = client.fetch_download_info(deviation_id, args.include_mature)
                    download_url = str(info.get("src") or "")
                    preferred_name = str(info.get("filename") or "") or None
                except DeviantArtApiError as exc:
                    logging.warning("Original download unavailable for %s: %s", deviation_id, exc)

            if not download_url and args.allow_preview:
                content = item.get("content")
                if isinstance(content, dict):
                    download_url = str(content.get("src") or "")

            if not download_url:
                skipped += 1
                logging.info(
                    "SKIP no downloadable image %s | %s (use --allow-preview to save preview/content images)",
                    deviation_id,
                    title,
                )
                continue

            output_path = build_output_path(
                output_dir=args.output_dir,
                username=args.username,
                deviation_id=deviation_id,
                title=title,
                source_url=download_url,
                preferred_filename=preferred_name,
            )

            try:
                created = client.download_file(download_url, output_path)
            except requests.RequestException as exc:
                skipped += 1
                logging.warning("Download failed for %s | %s: %s", deviation_id, title, exc)
                continue

            if created:
                downloaded += 1
                logging.info("DOWNLOADED %s | %s -> %s", deviation_id, title, output_path)
            else:
                existing += 1
                logging.info("EXISTS %s | %s -> %s", deviation_id, title, output_path)

        if not page.get("has_more"):
            break
        next_offset = page.get("next_offset")
        if next_offset is None:
            break
        offset = int(next_offset)

    if len(seen_ids) > args.max_seen:
        user_state["seen_ids"] = seen_ids[-args.max_seen :]

    return {
        "pages_checked": pages_checked,
        "new_items": new_items,
        "downloaded": downloaded,
        "existing": existing,
        "skipped": skipped,
    }


def parse_args() -> argparse.Namespace:
    pre_parser = argparse.ArgumentParser(add_help=False)
    pre_parser.add_argument("--env-file", default=".env")
    pre_args, _ = pre_parser.parse_known_args()
    load_env_file(Path(pre_args.env_file))

    parser = argparse.ArgumentParser(
        description="Download newly uploaded images from a DeviantArt user's gallery."
    )
    parser.add_argument("--env-file", default=pre_args.env_file, help="Path to optional .env file.")
    parser.add_argument("--client-id", default=os.getenv("DA_CLIENT_ID"), help="DeviantArt client_id.")
    parser.add_argument(
        "--client-secret",
        default=os.getenv("DA_CLIENT_SECRET"),
        help="DeviantArt client_secret.",
    )
    parser.add_argument("--username", default=os.getenv("DA_USERNAME"), help="Target DeviantArt username.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(os.getenv("OUTPUT_DIR", "downloads")),
        help="Directory where images are saved.",
    )
    parser.add_argument(
        "--state-file",
        type=Path,
        default=Path(os.getenv("STATE_FILE", "state.json")),
        help="Path to local state file.",
    )
    parser.add_argument(
        "--pages",
        type=int,
        default=env_int("PAGES_PER_CHECK", 3),
        help="How many gallery pages to inspect per check.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=env_int("PAGE_SIZE", 24),
        help="Items per page (API max: 24).",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=env_int("POLL_INTERVAL_SECONDS", 0),
        help="Polling interval in seconds. Use 0 to run once and exit.",
    )
    parser.add_argument(
        "--include-mature",
        action=argparse.BooleanOptionalAction,
        default=env_bool("INCLUDE_MATURE", False),
        help="Include mature content if the account has permission.",
    )
    parser.add_argument(
        "--allow-preview",
        action=argparse.BooleanOptionalAction,
        default=env_bool("ALLOW_PREVIEW", False),
        help="Download preview/content images when original download is unavailable.",
    )
    parser.add_argument(
        "--seed-only",
        action=argparse.BooleanOptionalAction,
        default=env_bool("SEED_ONLY", False),
        help="Record current items as seen without downloading.",
    )
    parser.add_argument(
        "--max-seen",
        type=int,
        default=env_int("MAX_SEEN_IDS", 5000),
        help="Max number of seen IDs to keep in state.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=env_int("REQUEST_TIMEOUT_SECONDS", 30),
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--user-agent",
        default=os.getenv("USER_AGENT", DEFAULT_USER_AGENT),
        help="Custom User-Agent header.",
    )
    parser.add_argument(
        "--verbose",
        action=argparse.BooleanOptionalAction,
        default=env_bool("VERBOSE", False),
        help="Enable debug logs.",
    )

    args = parser.parse_args()

    missing = []
    if not args.client_id:
        missing.append("DA_CLIENT_ID / --client-id")
    if not args.client_secret:
        missing.append("DA_CLIENT_SECRET / --client-secret")
    if not args.username:
        missing.append("DA_USERNAME / --username")
    if missing:
        parser.error(f"Missing required values: {', '.join(missing)}")

    if args.pages < 1:
        parser.error("--pages must be >= 1")
    if args.limit < 1 or args.limit > 24:
        parser.error("--limit must be between 1 and 24")
    if args.interval < 0:
        parser.error("--interval must be >= 0")
    if args.max_seen < 100:
        parser.error("--max-seen should be >= 100")

    return args


def run() -> int:
    args = parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    state = load_state(args.state_file)
    client = DeviantArtClient(
        client_id=args.client_id,
        client_secret=args.client_secret,
        user_agent=args.user_agent,
        timeout=args.timeout,
    )

    while True:
        started_at = time.strftime("%Y-%m-%d %H:%M:%S")
        logging.info("Checking @%s at %s", args.username, started_at)
        try:
            stats = process_once(args, client, state)
            save_state(args.state_file, state)
            logging.info(
                "Finished check | pages=%s new=%s downloaded=%s existing=%s skipped=%s",
                stats["pages_checked"],
                stats["new_items"],
                stats["downloaded"],
                stats["existing"],
                stats["skipped"],
            )
        except DeviantArtApiError as exc:
            logging.error("API error: %s", exc)
            if args.interval == 0:
                return 1
        except requests.RequestException as exc:
            logging.error("Network error: %s", exc)
            if args.interval == 0:
                return 1

        if args.interval == 0:
            return 0

        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(run())
