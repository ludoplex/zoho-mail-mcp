"""Async Zoho Mail API client with auto-auth and retry on 401."""

from __future__ import annotations

import os
from typing import Any

import httpx

from zoho_auth import TokenCache


class ZohoMailClient:
    """Wraps Zoho Mail REST API v2 with automatic OAuth and account ID discovery."""

    def __init__(
        self,
        token_cache: TokenCache,
        base_url: str = "https://mail.zoho.com",
        account_id: str | None = None,
    ) -> None:
        self._token_cache = token_cache
        self._base_url = base_url.rstrip("/")
        self._account_id = account_id
        self._http = httpx.AsyncClient(timeout=30.0)

    async def close(self) -> None:
        await self._http.aclose()

    async def _ensure_account_id(self) -> str:
        """Discover the primary account ID if not pre-configured."""
        if self._account_id:
            return self._account_id
        data = await self._request("GET", "/api/accounts")
        accounts = data.get("data", [])
        if not accounts:
            raise RuntimeError("No Zoho Mail accounts found for this token")
        self._account_id = str(accounts[0]["accountId"])
        return self._account_id

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        retry_on_401: bool = True,
    ) -> dict[str, Any]:
        """Make an authenticated request to the Zoho Mail API."""
        headers = await self._token_cache.auth_headers(self._http)
        url = f"{self._base_url}{path}"

        resp = await self._http.request(
            method, url, headers=headers, params=params, json=json_body
        )

        if resp.status_code == 401 and retry_on_401:
            self._token_cache.invalidate()
            headers = await self._token_cache.auth_headers(self._http)
            resp = await self._http.request(
                method, url, headers=headers, params=params, json=json_body
            )

        resp.raise_for_status()
        return resp.json()

    # ── Account ────────────────────────────────────────────────────

    async def get_profile(self) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        return await self._request("GET", f"/api/accounts/{account_id}")

    # ── Folders & Labels ───────────────────────────────────────────

    async def list_folders(self) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        return await self._request("GET", f"/api/accounts/{account_id}/folders")

    async def list_labels(self) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        return await self._request("GET", f"/api/accounts/{account_id}/tags")

    # ── Messages ───────────────────────────────────────────────────

    async def search_messages(
        self,
        query: str,
        folder_id: str | None = None,
        limit: int = 10,
        start: int = 0,
    ) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        params: dict[str, Any] = {
            "searchKey": query,
            "limit": limit,
            "start": start,
        }
        if folder_id:
            params["folderId"] = folder_id
        return await self._request(
            "GET", f"/api/accounts/{account_id}/messages/search", params=params
        )

    async def read_message(self, message_id: str, folder_id: str) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        return await self._request(
            "GET",
            f"/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}",
        )

    async def read_thread(self, thread_id: str, folder_id: str) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        return await self._request(
            "GET",
            f"/api/accounts/{account_id}/folders/{folder_id}/threads/{thread_id}",
        )

    async def modify_message(
        self,
        message_id: str,
        folder_id: str,
        *,
        is_read: bool | None = None,
        is_starred: bool | None = None,
        move_to_folder_id: str | None = None,
    ) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        body: dict[str, Any] = {"mode": "markAs"}

        if is_read is not None:
            body["isRead"] = str(is_read).lower()
        if is_starred is not None:
            body["isFlagged"] = str(is_starred).lower()
        if move_to_folder_id:
            body["mode"] = "moveMessage"
            body["destfolderId"] = move_to_folder_id

        return await self._request(
            "PUT",
            f"/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}",
            json_body=body,
        )

    async def delete_message(self, message_id: str, folder_id: str) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        return await self._request(
            "DELETE",
            f"/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}",
        )

    # ── Compose & Send ─────────────────────────────────────────────

    async def create_draft(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        cc: str = "",
        bcc: str = "",
        is_html: bool = True,
    ) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        payload: dict[str, Any] = {
            "toAddress": to,
            "subject": subject,
            "content": body,
            "mailFormat": "html" if is_html else "plaintext",
        }
        if cc:
            payload["ccAddress"] = cc
        if bcc:
            payload["bccAddress"] = bcc
        return await self._request(
            "POST", f"/api/accounts/{account_id}/messages", json_body=payload
        )

    async def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        cc: str = "",
        bcc: str = "",
        is_html: bool = True,
    ) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        payload: dict[str, Any] = {
            "toAddress": to,
            "subject": subject,
            "content": body,
            "mailFormat": "html" if is_html else "plaintext",
        }
        if cc:
            payload["ccAddress"] = cc
        if bcc:
            payload["bccAddress"] = bcc
        return await self._request(
            "POST", f"/api/accounts/{account_id}/messages", json_body=payload
        )

    async def reply_to_message(
        self,
        message_id: str,
        folder_id: str,
        body: str,
        *,
        to: str = "",
        cc: str = "",
        bcc: str = "",
        is_html: bool = True,
        reply_all: bool = False,
    ) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        payload: dict[str, Any] = {
            "content": body,
            "mailFormat": "html" if is_html else "plaintext",
        }
        if to:
            payload["toAddress"] = to
        if cc:
            payload["ccAddress"] = cc
        if bcc:
            payload["bccAddress"] = bcc

        action = "replyall" if reply_all else "reply"
        return await self._request(
            "POST",
            f"/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}/{action}",
            json_body=payload,
        )

    # ── Attachments ────────────────────────────────────────────────

    async def get_attachment(
        self, message_id: str, folder_id: str, attachment_id: str
    ) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        return await self._request(
            "GET",
            f"/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}/attachments/{attachment_id}",
        )


def create_client_from_env() -> ZohoMailClient:
    """Factory: build a ZohoMailClient from environment variables."""
    token_cache = TokenCache(
        client_id=os.environ["ZOHO_CLIENT_ID"],
        client_secret=os.environ["ZOHO_CLIENT_SECRET"],
        refresh_token=os.environ["ZOHO_REFRESH_TOKEN"],
        accounts_url=os.environ.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.com"),
    )
    return ZohoMailClient(
        token_cache=token_cache,
        base_url=os.environ.get("ZOHO_MAIL_BASE_URL", "https://mail.zoho.com"),
        account_id=os.environ.get("ZOHO_ACCOUNT_ID"),
    )
