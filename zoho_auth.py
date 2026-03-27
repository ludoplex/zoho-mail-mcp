"""Zoho Mail OAuth 2.0 token management with automatic refresh."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import httpx


@dataclass
class TokenCache:
    """Caches an OAuth access token and refreshes 300s before expiry."""

    client_id: str
    client_secret: str
    refresh_token: str
    accounts_url: str = "https://accounts.zoho.com"

    _access_token: str | None = field(default=None, init=False, repr=False)
    _expires_at: float = field(default=0.0, init=False, repr=False)

    PRE_EXPIRY_BUFFER: int = 300  # seconds before expiry to trigger refresh

    @property
    def is_expired(self) -> bool:
        return (
            self._access_token is None
            or time.monotonic() >= self._expires_at - self.PRE_EXPIRY_BUFFER
        )

    async def get_token(self, http: httpx.AsyncClient) -> str:
        """Return a valid access token, refreshing if needed."""
        if not self.is_expired:
            assert self._access_token is not None
            return self._access_token
        return await self._refresh(http)

    async def _refresh(self, http: httpx.AsyncClient) -> str:
        """Exchange the refresh token for a new access token."""
        url = f"{self.accounts_url}/oauth/v2/token"
        params = {
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "refresh_token",
        }
        resp = await http.post(url, params=params)
        resp.raise_for_status()
        data = resp.json()

        if "error" in data:
            raise RuntimeError(f"Zoho token refresh failed: {data['error']}")

        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 3600))
        self._expires_at = time.monotonic() + expires_in
        return self._access_token

    def invalidate(self) -> None:
        """Force re-fetch on next call (e.g. after a 401)."""
        self._access_token = None
        self._expires_at = 0.0

    async def auth_headers(self, http: httpx.AsyncClient) -> dict[str, str]:
        """Return the Zoho-oauthtoken authorization header."""
        token = await self.get_token(http)
        return {"Authorization": f"Zoho-oauthtoken {token}"}
