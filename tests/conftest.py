"""Shared test fixtures with respx mocking for Zoho Mail API."""

from __future__ import annotations

import pytest
import respx
import httpx

from zoho_auth import TokenCache
from zoho_client import ZohoMailClient

FAKE_ACCESS_TOKEN = "fake_access_token_12345"
FAKE_ACCOUNT_ID = "1234567890"
ACCOUNTS_URL = "https://accounts.zoho.com"
MAIL_BASE = "https://mail.zoho.com"


@pytest.fixture()
def mock_api():
    """Activate respx for the test and pre-configure the token refresh endpoint."""
    with respx.mock(assert_all_called=False) as rsps:
        # Token refresh always succeeds
        rsps.post(f"{ACCOUNTS_URL}/oauth/v2/token").respond(
            json={
                "access_token": FAKE_ACCESS_TOKEN,
                "expires_in": 3600,
                "token_type": "Bearer",
            }
        )
        # Account discovery
        rsps.get(f"{MAIL_BASE}/api/accounts").respond(
            json={
                "status": {"code": 200},
                "data": [{"accountId": FAKE_ACCOUNT_ID, "emailAddress": "test@example.com"}],
            }
        )
        yield rsps


@pytest.fixture()
def token_cache() -> TokenCache:
    return TokenCache(
        client_id="test_client_id",
        client_secret="test_client_secret",
        refresh_token="test_refresh_token",
        accounts_url=ACCOUNTS_URL,
    )


@pytest.fixture()
async def client(token_cache, mock_api) -> ZohoMailClient:
    c = ZohoMailClient(
        token_cache=token_cache,
        base_url=MAIL_BASE,
    )
    try:
        yield c
    finally:
        await c.close()
