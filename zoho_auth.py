"""Zoho Mail OAuth 2.0 token management with automatic refresh.

The refresh grant goes to the token endpoint as an
``application/x-www-form-urlencoded`` POST body, so no credential is ever part
of a URL: not of an httpx error message, not of a log line, not of a proxy or
server access log. A failed grant raises :class:`ZohoTokenError`, whose text is
only the HTTP status and Zoho's ``error`` / ``error_description`` fields.

Access tokens are shared between processes through a small per-user disk cache
(one owner-only JSON file per credential set, holding only the access token and
its expiry). Zoho throttles refresh grants and answers HTTP 400 "You have made
too many requests continuously" after a burst, so parallel MCP servers and CLI
runs reuse one token instead of each spending a grant. A lock file serializes
the grant itself.

Environment:
    ZOHO_TOKEN_CACHE=0       disable the disk cache (memory cache only)
    ZOHO_TOKEN_CACHE_DIR=D   cache directory (default: %LOCALAPPDATA%,
                             $XDG_CACHE_HOME or ~/.cache, + /zoho-mail-tokens)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

import httpx

log = logging.getLogger(__name__)

_FIELD_LIMIT = 200  # max characters kept from each Zoho error field
_REDACTED = "<redacted>"


class ZohoTokenError(RuntimeError):
    """The refresh grant failed.

    The message holds only the HTTP status and Zoho's ``error`` and
    ``error_description`` fields, never the request URL or a credential.
    """

    def __init__(
        self,
        status_code: int,
        error: str | None = None,
        error_description: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.error = error
        self.error_description = error_description
        parts = [f"Zoho token refresh failed: HTTP {status_code}"]
        if error:
            parts.append(f"error={error!r}")
        if error_description:
            parts.append(f"error_description={error_description!r}")
        super().__init__(" ".join(parts))


def _cache_dir() -> Path | None:
    """Directory of the shared token cache, or None when it is disabled."""
    if os.environ.get("ZOHO_TOKEN_CACHE", "1").strip().lower() in {"0", "off", "false", "no"}:
        return None
    override = os.environ.get("ZOHO_TOKEN_CACHE_DIR")
    if override:
        return Path(override)
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME")
    return Path(base or Path.home() / ".cache") / "zoho-mail-tokens"


def _json_body(resp: httpx.Response) -> dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:
        log.debug("zoho token cache: cannot remove %s (%s)", path.name, type(exc).__name__)


@dataclass
class TokenCache:
    """Caches an OAuth access token and refreshes 300s before expiry."""

    client_id: str = field(repr=False)
    client_secret: str = field(repr=False)
    refresh_token: str = field(repr=False)
    accounts_url: str = "https://accounts.zoho.com"

    _access_token: str | None = field(default=None, init=False, repr=False)
    _expires_at: float = field(default=0.0, init=False, repr=False)
    _rejected: str | None = field(default=None, init=False, repr=False)

    PRE_EXPIRY_BUFFER: int = 300  # seconds before expiry to trigger refresh

    LOCK_WAIT: ClassVar[float] = 30.0  # max seconds to wait for another grant
    LOCK_STALE: ClassVar[float] = 60.0  # a lock older than this is abandoned
    LOCK_POLL: ClassVar[float] = 0.2

    @property
    def is_expired(self) -> bool:
        return (
            self._access_token is None
            or time.monotonic() >= self._expires_at - self.PRE_EXPIRY_BUFFER
        )

    async def get_token(self, http: httpx.AsyncClient) -> str:
        """Return a valid access token, refreshing if needed."""
        if self.is_expired and not self._load_disk():
            return await self._refresh_shared(http)
        return self._current()

    def invalidate(self) -> None:
        """Force re-fetch on next call (e.g. after a 401)."""
        rejected = self._access_token
        self._access_token = None
        self._expires_at = 0.0
        if rejected is None:
            return
        self._rejected = rejected
        path = self._disk_path()
        if path is not None and self._read_disk(path).get("access_token") == rejected:
            _unlink_quietly(path)  # keep a newer token another process wrote

    async def auth_headers(self, http: httpx.AsyncClient) -> dict[str, str]:
        """Return the Zoho-oauthtoken authorization header."""
        token = await self.get_token(http)
        return {"Authorization": f"Zoho-oauthtoken {token}"}

    # ── Refresh grant ───────────────────────────────────────────────

    async def _refresh(self, http: httpx.AsyncClient) -> str:
        """Exchange the refresh token for a new access token."""
        form = {
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }
        resp = await http.post(f"{self.accounts_url}/oauth/v2/token", data=form)
        data = _json_body(resp)
        token = data.get("access_token")
        if not resp.is_success or "error" in data or not isinstance(token, str):
            raise self._token_error(resp.status_code, data)

        expires_in = int(data.get("expires_in", 3600))
        self._store(token, expires_in)
        self._rejected = None
        self._save_disk(expires_in)
        return token

    def _token_error(self, status_code: int, data: dict[str, Any]) -> ZohoTokenError:
        return ZohoTokenError(
            status_code,
            self._clean_field(data.get("error")),
            self._clean_field(data.get("error_description")),
        )

    def _clean_field(self, value: Any) -> str | None:
        """Bound a Zoho error field and strip any credential it echoes."""
        if value is None:
            return None
        text = str(value)
        for secret in (self.refresh_token, self.client_secret, self.client_id):
            if secret:
                text = text.replace(secret, _REDACTED)
        return text[:_FIELD_LIMIT]

    async def _refresh_shared(self, http: httpx.AsyncClient) -> str:
        """Refresh under the cross-process lock; adopt a peer's token if one lands."""
        path = self._disk_path()
        if path is None:
            return await self._refresh(http)
        lock = path.with_suffix(".lock")
        deadline = time.monotonic() + self.LOCK_WAIT
        owned = self._try_lock(lock)
        while owned is False:
            if self._load_disk():
                return self._current()
            if time.monotonic() >= deadline:
                log.debug("zoho token cache: lock wait timed out, refreshing alone")
                break
            self._break_stale_lock(lock)
            await asyncio.sleep(self.LOCK_POLL)
            owned = self._try_lock(lock)
        try:
            if self._load_disk():
                return self._current()
            return await self._refresh(http)
        finally:
            if owned:
                _unlink_quietly(lock)

    # ── In-memory state ─────────────────────────────────────────────

    def _store(self, token: str, expires_in: float) -> None:
        self._access_token = token
        self._expires_at = time.monotonic() + expires_in

    def _current(self) -> str:
        assert self._access_token is not None
        return self._access_token

    # ── Disk cache (best-effort: any OSError falls back to a refresh) ─

    def _disk_path(self) -> Path | None:
        directory = _cache_dir()
        if directory is None:
            return None
        material = f"{self.accounts_url}\n{self.client_id}\n{self.refresh_token}"
        return directory / f"{hashlib.sha256(material.encode()).hexdigest()[:16]}.json"

    @staticmethod
    def _read_disk(path: Path) -> dict[str, Any]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _load_disk(self) -> bool:
        """Adopt a still-valid token persisted by another process."""
        path = self._disk_path()
        if path is None:
            return False
        data = self._read_disk(path)
        token, expires_at = data.get("access_token"), data.get("expires_at_epoch")
        if not isinstance(token, str) or not isinstance(expires_at, (int, float)):
            return False
        remaining = expires_at - time.time()
        if token == self._rejected or remaining <= self.PRE_EXPIRY_BUFFER:
            return False
        self._store(token, remaining)
        return True

    def _save_disk(self, expires_in: float) -> None:
        path = self._disk_path()
        if path is None or self._access_token is None:
            return
        payload = json.dumps(
            {"access_token": self._access_token, "expires_at_epoch": time.time() + expires_in}
        )
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        try:
            self._ensure_dir(path.parent)
            _unlink_quietly(tmp)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp, path)
        except OSError as exc:
            log.debug("zoho token cache: write skipped (%s)", type(exc).__name__)
            _unlink_quietly(tmp)

    @staticmethod
    def _ensure_dir(directory: Path) -> None:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name == "posix":
            os.chmod(directory, 0o700)

    def _try_lock(self, lock: Path) -> bool | None:
        """True: lock taken. False: another process holds it. None: no lock possible."""
        try:
            self._ensure_dir(lock.parent)
        except OSError as exc:  # mkdir raises FileExistsError when a parent is a file
            log.debug("zoho token cache: no cache dir (%s)", type(exc).__name__)
            return None
        try:
            os.close(os.open(lock, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        except FileExistsError:
            return False
        except OSError as exc:
            log.debug("zoho token cache: no lock (%s)", type(exc).__name__)
            return None
        return True

    def _break_stale_lock(self, lock: Path) -> None:
        try:
            age = time.time() - lock.stat().st_mtime
        except OSError:
            return
        if age > self.LOCK_STALE:
            _unlink_quietly(lock)
