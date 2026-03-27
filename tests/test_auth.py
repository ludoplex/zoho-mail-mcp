"""Tests for OAuth token refresh, expiry, and invalidation."""

from __future__ import annotations

import time
from unittest.mock import patch

import httpx
import pytest
import respx

from zoho_auth import TokenCache

ACCOUNTS_URL = "https://accounts.zoho.com"


@pytest.fixture()
def cache() -> TokenCache:
    return TokenCache(
        client_id="cid",
        client_secret="csec",
        refresh_token="rtoken",
        accounts_url=ACCOUNTS_URL,
    )


@pytest.mark.asyncio
async def test_fresh_cache_fetches_token(cache: TokenCache):
    assert cache.is_expired

    with respx.mock:
        respx.post(f"{ACCOUNTS_URL}/oauth/v2/token").respond(
            json={"access_token": "tok1", "expires_in": 3600}
        )
        async with httpx.AsyncClient() as http:
            token = await cache.get_token(http)

    assert token == "tok1"
    assert not cache.is_expired


@pytest.mark.asyncio
async def test_cached_token_no_refetch(cache: TokenCache):
    with respx.mock:
        route = respx.post(f"{ACCOUNTS_URL}/oauth/v2/token").respond(
            json={"access_token": "tok1", "expires_in": 3600}
        )
        async with httpx.AsyncClient() as http:
            t1 = await cache.get_token(http)
            t2 = await cache.get_token(http)

    assert t1 == t2 == "tok1"
    assert route.call_count == 1  # only one refresh call


@pytest.mark.asyncio
async def test_pre_expiry_triggers_refresh(cache: TokenCache):
    with respx.mock:
        respx.post(f"{ACCOUNTS_URL}/oauth/v2/token").respond(
            json={"access_token": "tok_new", "expires_in": 3600}
        )
        async with httpx.AsyncClient() as http:
            await cache.get_token(http)

            # Simulate token about to expire (within PRE_EXPIRY_BUFFER)
            cache._expires_at = time.monotonic() + 10  # 10s left, buffer is 300s
            assert cache.is_expired

            token = await cache.get_token(http)
            assert token == "tok_new"


@pytest.mark.asyncio
async def test_invalidate_forces_refresh(cache: TokenCache):
    call_count = 0

    with respx.mock:
        def side_effect(request):
            nonlocal call_count
            call_count += 1
            return httpx.Response(
                200,
                json={"access_token": f"tok_{call_count}", "expires_in": 3600},
            )

        respx.post(f"{ACCOUNTS_URL}/oauth/v2/token").mock(side_effect=side_effect)

        async with httpx.AsyncClient() as http:
            t1 = await cache.get_token(http)
            assert t1 == "tok_1"

            cache.invalidate()
            assert cache.is_expired

            t2 = await cache.get_token(http)
            assert t2 == "tok_2"


@pytest.mark.asyncio
async def test_auth_headers_format(cache: TokenCache):
    with respx.mock:
        respx.post(f"{ACCOUNTS_URL}/oauth/v2/token").respond(
            json={"access_token": "mytoken", "expires_in": 3600}
        )
        async with httpx.AsyncClient() as http:
            headers = await cache.auth_headers(http)

    assert headers == {"Authorization": "Zoho-oauthtoken mytoken"}


@pytest.mark.asyncio
async def test_refresh_error_raises(cache: TokenCache):
    with respx.mock:
        respx.post(f"{ACCOUNTS_URL}/oauth/v2/token").respond(
            json={"error": "invalid_code"}
        )
        async with httpx.AsyncClient() as http:
            with pytest.raises(RuntimeError, match="invalid_code"):
                await cache.get_token(http)
