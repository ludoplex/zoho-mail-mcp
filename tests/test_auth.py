"""Tests for OAuth token refresh, expiry, and invalidation."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import traceback
from urllib.parse import parse_qs

import httpx
import pytest
import respx

from zoho_auth import TokenCache, ZohoTokenError

ACCOUNTS_URL = "https://accounts.zoho.com"
TOKEN_URL = f"{ACCOUNTS_URL}/oauth/v2/token"

# Distinctive fake credentials, so a leak is a plain substring match.
LEAK_ID = "1000.LEAKCHECKCLIENTID0000000000000000"
LEAK_SECRET = "leakchecksecret00000000000000000000000000"
LEAK_REFRESH = "1000.leakcheckrefresh0000000000000000.leakcheckrefresh00000000000000"
THROTTLED = {
    "error_description": "You have made too many requests continuously. "
    "Please try again after some time.",
    "error": "Access Denied",
    "status": "failure",
}


def _leaky_cache() -> TokenCache:
    return TokenCache(
        client_id=LEAK_ID,
        client_secret=LEAK_SECRET,
        refresh_token=LEAK_REFRESH,
        accounts_url=ACCOUNTS_URL,
    )


def _assert_no_credentials(text: str) -> None:
    for secret in (LEAK_ID, LEAK_SECRET, LEAK_REFRESH):
        assert secret not in text


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


# ── Credentials stay out of URLs and error text ─────────────────────


@pytest.mark.asyncio
async def test_refresh_sends_credentials_in_form_body():
    with respx.mock:
        route = respx.post(TOKEN_URL).respond(
            json={"access_token": "tok", "expires_in": 3600}
        )
        async with httpx.AsyncClient() as http:
            await _leaky_cache().get_token(http)

    request = route.calls.last.request
    assert request.url.query == b""
    _assert_no_credentials(str(request.url))
    assert request.headers["content-type"] == "application/x-www-form-urlencoded"
    form = parse_qs(request.content.decode())
    assert form == {
        "refresh_token": [LEAK_REFRESH],
        "client_id": [LEAK_ID],
        "client_secret": [LEAK_SECRET],
        "grant_type": ["refresh_token"],
    }


@pytest.mark.asyncio
async def test_http_400_error_has_status_and_zoho_fields_only():
    with respx.mock:
        respx.post(TOKEN_URL).respond(400, json=THROTTLED)
        async with httpx.AsyncClient() as http:
            with pytest.raises(ZohoTokenError) as excinfo:
                await _leaky_cache().get_token(http)

    err = excinfo.value
    assert isinstance(err, RuntimeError)
    assert (err.status_code, err.error) == (400, "Access Denied")
    assert "too many requests continuously" in err.error_description
    message = str(err)
    assert "HTTP 400" in message
    assert "Access Denied" in message
    assert "too many requests continuously" in message
    assert "accounts.zoho.com" not in message
    _assert_no_credentials(message)
    _assert_no_credentials(repr(err))
    # A chained httpx.HTTPStatusError would print the URL in the traceback.
    assert err.__cause__ is None and err.__context__ is None
    _assert_no_credentials("".join(traceback.format_exception(err)))


@pytest.mark.asyncio
async def test_non_json_error_body_is_not_echoed():
    with respx.mock:
        respx.post(TOKEN_URL).respond(502, text=f"<html>bad gateway {LEAK_REFRESH}</html>")
        async with httpx.AsyncClient() as http:
            with pytest.raises(ZohoTokenError) as excinfo:
                await _leaky_cache().get_token(http)

    assert str(excinfo.value) == "Zoho token refresh failed: HTTP 502"
    assert excinfo.value.__context__ is None


@pytest.mark.asyncio
async def test_error_fields_that_echo_a_credential_are_redacted():
    body = {"error": f"bad {LEAK_ID}", "error_description": f"token {LEAK_REFRESH} {LEAK_SECRET}"}
    with respx.mock:
        respx.post(TOKEN_URL).respond(400, json=body)
        async with httpx.AsyncClient() as http:
            with pytest.raises(ZohoTokenError) as excinfo:
                await _leaky_cache().get_token(http)

    _assert_no_credentials(str(excinfo.value))
    assert "<redacted>" in str(excinfo.value)


@pytest.mark.asyncio
async def test_long_error_field_is_truncated():
    with respx.mock:
        respx.post(TOKEN_URL).respond(400, json={"error": "x" * 5000})
        async with httpx.AsyncClient() as http:
            with pytest.raises(ZohoTokenError) as excinfo:
                await _leaky_cache().get_token(http)

    assert len(str(excinfo.value)) < 500


@pytest.mark.asyncio
async def test_success_status_without_access_token_raises():
    with respx.mock:
        respx.post(TOKEN_URL).respond(json={"expires_in": 3600})
        async with httpx.AsyncClient() as http:
            with pytest.raises(ZohoTokenError, match="HTTP 200"):
                await _leaky_cache().get_token(http)


def test_repr_hides_credentials():
    _assert_no_credentials(repr(_leaky_cache()))


# ── Shared on-disk token cache ──────────────────────────────────────


@pytest.mark.asyncio
async def test_second_process_reuses_disk_token():
    with respx.mock:
        route = respx.post(TOKEN_URL).respond(
            json={"access_token": "shared", "expires_in": 3600}
        )
        async with httpx.AsyncClient() as http:
            first = await _leaky_cache().get_token(http)
            second = await _leaky_cache().get_token(http)  # fresh instance = other process

    assert first == second == "shared"
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_disk_cache_holds_no_credentials(token_cache_dir):
    with respx.mock:
        respx.post(TOKEN_URL).respond(json={"access_token": "tok", "expires_in": 3600})
        async with httpx.AsyncClient() as http:
            await _leaky_cache().get_token(http)

    files = [p for p in token_cache_dir.iterdir() if p.suffix == ".json"]
    assert len(files) == 1
    _assert_no_credentials(files[0].name)
    raw = files[0].read_text(encoding="utf-8")
    _assert_no_credentials(raw)
    assert set(json.loads(raw)) == {"access_token", "expires_at_epoch"}
    assert not [p for p in token_cache_dir.iterdir() if p.suffix in {".lock", ".tmp"}]


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX permission bits")
@pytest.mark.asyncio
async def test_disk_cache_file_is_owner_only(token_cache_dir):
    with respx.mock:
        respx.post(TOKEN_URL).respond(json={"access_token": "tok", "expires_in": 3600})
        async with httpx.AsyncClient() as http:
            await _leaky_cache().get_token(http)

    (cache_file,) = token_cache_dir.glob("*.json")
    assert cache_file.stat().st_mode & 0o777 == 0o600
    assert token_cache_dir.stat().st_mode & 0o777 == 0o700


@pytest.mark.asyncio
async def test_parallel_instances_refresh_once():
    async def slow_grant(request):
        await asyncio.sleep(0.3)
        return httpx.Response(200, json={"access_token": "one", "expires_in": 3600})

    with respx.mock:
        route = respx.post(TOKEN_URL).mock(side_effect=slow_grant)
        async with httpx.AsyncClient() as http:
            tokens = await asyncio.gather(*(_leaky_cache().get_token(http) for _ in range(6)))

    assert tokens == ["one"] * 6
    assert route.call_count == 1


@pytest.mark.asyncio
async def test_stale_lock_is_broken(token_cache_dir):
    cache = _leaky_cache()
    lock = cache._disk_path().with_suffix(".lock")
    lock.parent.mkdir(parents=True)
    lock.write_text("")
    old = time.time() - cache.LOCK_STALE - 5
    os.utime(lock, (old, old))

    with respx.mock:
        route = respx.post(TOKEN_URL).respond(json={"access_token": "tok", "expires_in": 3600})
        async with httpx.AsyncClient() as http:
            assert await cache.get_token(http) == "tok"

    assert route.call_count == 1
    assert not lock.exists()


@pytest.mark.asyncio
async def test_lock_wait_timeout_refreshes_alone(token_cache_dir, monkeypatch):
    cache = _leaky_cache()
    monkeypatch.setattr(TokenCache, "LOCK_WAIT", 0.3)
    lock = cache._disk_path().with_suffix(".lock")
    lock.parent.mkdir(parents=True)
    lock.write_text("")  # fresh lock held by a hung process

    with respx.mock:
        respx.post(TOKEN_URL).respond(json={"access_token": "tok", "expires_in": 3600})
        async with httpx.AsyncClient() as http:
            assert await cache.get_token(http) == "tok"

    assert lock.exists()  # never remove a lock this process does not own


@pytest.mark.asyncio
async def test_expired_disk_token_is_ignored():
    cache = _leaky_cache()
    path = cache._disk_path()
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"access_token": "old", "expires_at_epoch": time.time() + 10}))

    with respx.mock:
        respx.post(TOKEN_URL).respond(json={"access_token": "new", "expires_in": 3600})
        async with httpx.AsyncClient() as http:
            assert await cache.get_token(http) == "new"


@pytest.mark.parametrize("content", ["not json", "[]", '{"access_token": 5, "expires_at_epoch": 1e12}'])
@pytest.mark.asyncio
async def test_corrupt_disk_cache_is_ignored(content):
    cache = _leaky_cache()
    path = cache._disk_path()
    path.parent.mkdir(parents=True)
    path.write_text(content)

    with respx.mock:
        respx.post(TOKEN_URL).respond(json={"access_token": "new", "expires_in": 3600})
        async with httpx.AsyncClient() as http:
            assert await cache.get_token(http) == "new"


@pytest.mark.asyncio
async def test_invalidate_drops_rejected_disk_token():
    grants = iter(["first", "second"])
    with respx.mock:
        route = respx.post(TOKEN_URL).mock(
            side_effect=lambda request: httpx.Response(
                200, json={"access_token": next(grants), "expires_in": 3600}
            )
        )
        async with httpx.AsyncClient() as http:
            cache = _leaky_cache()
            assert await cache.get_token(http) == "first"
            cache.invalidate()  # API answered 401 for "first"
            assert not cache._disk_path().exists()
            assert await _leaky_cache().get_token(http) == "second"

    assert route.call_count == 2


@pytest.mark.asyncio
async def test_invalidate_keeps_newer_disk_token():
    cache = _leaky_cache()
    other = _leaky_cache()
    with respx.mock:
        route = respx.post(TOKEN_URL).mock(
            side_effect=[
                httpx.Response(200, json={"access_token": "old", "expires_in": 3600}),
                httpx.Response(200, json={"access_token": "newer", "expires_in": 3600}),
            ]
        )
        async with httpx.AsyncClient() as http:
            assert await cache.get_token(http) == "old"
            assert await other.get_token(http) == "old"  # adopted from disk
            other.invalidate()  # the other process saw the 401 first
            assert await other.get_token(http) == "newer"
            cache.invalidate()  # now this process sees its 401 for "old"
            assert cache._disk_path().exists()  # "newer" is kept
            assert await cache.get_token(http) == "newer"

    assert route.call_count == 2


@pytest.mark.asyncio
async def test_disk_cache_can_be_disabled(token_cache_dir, monkeypatch):
    monkeypatch.setenv("ZOHO_TOKEN_CACHE", "0")
    with respx.mock:
        route = respx.post(TOKEN_URL).respond(json={"access_token": "tok", "expires_in": 3600})
        async with httpx.AsyncClient() as http:
            await _leaky_cache().get_token(http)
            await _leaky_cache().get_token(http)

    assert route.call_count == 2
    assert not token_cache_dir.exists()


@pytest.mark.asyncio
async def test_unwritable_cache_dir_still_refreshes(tmp_path, monkeypatch):
    blocker = tmp_path / "file-not-dir"
    blocker.write_text("")
    monkeypatch.setenv("ZOHO_TOKEN_CACHE_DIR", str(blocker / "sub"))
    with respx.mock:
        respx.post(TOKEN_URL).respond(json={"access_token": "tok", "expires_in": 3600})
        async with httpx.AsyncClient() as http:
            assert await _leaky_cache().get_token(http) == "tok"
