from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import requests

TOKEN_URL = "https://www.deviantart.com/oauth2/token"
API_BASE = "https://www.deviantart.com/api/v1/oauth2"
DEFAULT_USER_AGENT = "deviantart-watcher/1.0"


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
        # Refresh the token slightly early to avoid edge-expiry during requests.
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

    def fetch_deviation(self, deviation_id: str, include_mature: bool) -> Dict[str, Any]:
        return self.api_get(
            f"/deviation/{deviation_id}",
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
            # Write to temporary file first, then atomically rename.
            tmp_path.replace(destination)
            return True
        except Exception:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
            raise
