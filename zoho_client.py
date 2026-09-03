"""Async Zoho Mail API client with auto-auth and retry on 401."""

from __future__ import annotations

import html
import os
from email.utils import getaddresses
from pathlib import Path
from typing import Any

import httpx

from zoho_auth import TokenCache

# System folder names used for safe-delete (move-to-Trash) and restore.
TRASH_FOLDER_NAME = "Trash"
INBOX_FOLDER_NAME = "Inbox"


class UnrecoverableOperationError(RuntimeError):
    """Raised when a caller attempts an action that would permanently destroy mail.

    This server intentionally forbids: permanent deletion (Zoho ``expunge=true``),
    emptying or deleting a folder (``mode=emptyFolder`` / ``deleteFolder``), and the
    raw HTTP ``DELETE`` verb. All "delete" intents are routed to a reversible
    move-to-Trash instead, and Trashed mail can be restored.
    """

# Gmail-style → Zoho-style field prefix translation.
# Lets the MCP tool accept queries written in either dialect.
_GMAIL_TO_ZOHO = {
    "from:": "sender:",
    "to:": "receiver:",
    "body:": "content:",
}
# Zoho search fields we recognize as already-prefixed (pass through).
_ZOHO_FIELDS = ("entire:", "sender:", "receiver:", "subject:", "content:",
                "folder:", "label:", "flag:", "priority:", "attachment:",
                "newer_than:", "older_than:")


def _normalize_search_key(q: str) -> str:
    """Make a raw user query into a Zoho-valid searchKey.

    - Translates Gmail-style prefixes (``from:`` → ``sender:``).
    - Auto-prefixes bare keywords with ``entire:`` to avoid Zoho's 500.
    - Leaves fully-qualified Zoho queries untouched.
    """
    stripped = q.strip()
    if not stripped:
        return stripped
    for gmail, zoho in _GMAIL_TO_ZOHO.items():
        if stripped.lower().startswith(gmail):
            stripped = zoho + stripped[len(gmail):]
            break
    lower = stripped.lower()
    if any(lower.startswith(f) for f in _ZOHO_FIELDS):
        return stripped
    # Bare keyword → search everywhere
    return f"entire:{stripped}"


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
        content: bytes | None = None,
        retry_on_401: bool = True,
    ) -> dict[str, Any]:
        """Make an authenticated request to the Zoho Mail API.

        ``content`` sends a raw byte payload (attachment uploads) instead of a
        JSON body; the two are mutually exclusive.
        """
        self._assert_recoverable(method, params, json_body)
        headers = await self._token_cache.auth_headers(self._http)
        if content is not None:
            headers["Content-Type"] = "application/octet-stream"
        url = f"{self._base_url}{path}"

        resp = await self._http.request(
            method, url, headers=headers, params=params, json=json_body,
            content=content,
        )

        if resp.status_code == 401 and retry_on_401:
            self._token_cache.invalidate()
            headers = await self._token_cache.auth_headers(self._http)
            resp = await self._http.request(
                method, url, headers=headers, params=params, json=json_body,
                content=content,
            )

        resp.raise_for_status()
        return resp.json()

    async def _request_bytes(self, path: str) -> bytes:
        """Authenticated GET returning the raw response body (attachment downloads)."""
        self._assert_recoverable("GET", None, None)
        headers = await self._token_cache.auth_headers(self._http)
        url = f"{self._base_url}{path}"
        resp = await self._http.get(url, headers=headers)
        if resp.status_code == 401:
            self._token_cache.invalidate()
            headers = await self._token_cache.auth_headers(self._http)
            resp = await self._http.get(url, headers=headers)
        resp.raise_for_status()
        return resp.content

    @staticmethod
    def _assert_recoverable(
        method: str,
        params: dict[str, Any] | None,
        json_body: dict[str, Any] | None,
    ) -> None:
        """Refuse any request that could destroy mail irrecoverably (defense-in-depth).

        Blocks, regardless of which method assembled the call:
          - HTTP ``DELETE`` (the verb Zoho uses for permanent/expunge deletion)
          - ``expunge=true`` in query params or body (permanent delete)
          - ``mode=emptyFolder`` / ``mode=deleteFolder`` (empties or drops a folder)

        Recoverable operations — move-to-Trash and restore — go through
        ``mode=moveMessage`` PUTs, which this guard allows.
        """
        if method.upper() == "DELETE":
            raise UnrecoverableOperationError(
                "Direct DELETE is disabled. Use delete_message (move-to-Trash) "
                "instead; permanent deletion is not permitted by this server."
            )
        lowered_params = {
            str(k).lower(): str(v).lower() for k, v in (params or {}).items()
        }
        if lowered_params.get("expunge") == "true":
            raise UnrecoverableOperationError(
                "Permanent deletion (expunge=true) is disabled by this server."
            )
        body = json_body or {}
        if str(body.get("expunge", "")).lower() == "true":
            raise UnrecoverableOperationError(
                "Permanent deletion (expunge=true) is disabled by this server."
            )
        if str(body.get("mode", "")).lower() in {"emptyfolder", "deletefolder"}:
            raise UnrecoverableOperationError(
                "Emptying or deleting a folder (incl. Trash) is disabled by this server."
            )

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

    async def _resolve_folder_id(self, name: str) -> str | None:
        """Find a folder's ID by its name or type (case-insensitive).

        Matches Zoho's ``folderName`` or ``folderType`` (e.g. "Trash", "Inbox"),
        tolerating localized display names where ``folderType`` is still canonical.
        """
        account_id = await self._ensure_account_id()
        resp = await self._request(
            "GET", f"/api/accounts/{account_id}/folders"
        )
        target = name.strip().lower()
        for folder in resp.get("data", []):
            candidates = {
                str(folder.get("folderName", "")).strip().lower(),
                str(folder.get("folderType", "")).strip().lower(),
            }
            if target in candidates:
                return str(folder["folderId"])
        return None

    # ── Messages ───────────────────────────────────────────────────

    async def search_messages(
        self,
        *,
        q: str = "",
        max_results: int = 20,
        start: int = 0,
        folder_id: str | None = None,
        include_spam_trash: bool = False,
    ) -> dict[str, Any]:
        """Search messages.

        Zoho's search endpoint requires a FIELD-PREFIXED query. Bare keywords
        return HTTP 500. Accepted prefixes include:

          entire:keyword        — search all fields (body, headers, subject…)
          sender:addr-or-name   — filter by sender
          subject:keyword       — filter by subject
          content:keyword       — search body only
          receiver:addr-or-name — filter by To/Cc

        If the caller passes a bare query (no colon), we auto-prefix with
        ``entire:`` so "pearson" becomes "entire:pearson".

        Gmail-style syntax (``from:`` / ``to:`` / ``body:``) is translated to
        Zoho syntax to keep the tool forgiving for models trained on Gmail.

        When ``q`` is empty, we fall back to ``/messages/view`` to list the
        folder (``/messages/search`` 500s without a searchKey).
        """
        account_id = await self._ensure_account_id()
        params: dict[str, Any] = {"limit": max_results, "start": start}
        if folder_id:
            params["folderId"] = folder_id
        if include_spam_trash:
            params["includeJunk"] = "true"

        # Empty query → plain folder listing via /messages/view
        if not q:
            return await self._request(
                "GET", f"/api/accounts/{account_id}/messages/view", params=params
            )

        params["searchKey"] = _normalize_search_key(q)
        return await self._request(
            "GET", f"/api/accounts/{account_id}/messages/search", params=params
        )

    async def read_message(self, message_id: str, folder_id: str) -> dict[str, Any]:
        """Fetch a message's full body (HTML/plaintext content).

        Zoho requires the ``/content`` suffix — without it the endpoint 404s.
        """
        account_id = await self._ensure_account_id()
        return await self._request(
            "GET",
            f"/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}/content",
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
        """Mark read/unread, star/unstar, or move a message.

        Uses the bulk ``/updatemessage`` endpoint — the per-message
        ``folders/{fid}/messages/{mid}`` PUT 404s on this tenant. Each
        requested change is its own call (the endpoint takes one mode per
        request). ``folder_id`` is kept for interface compatibility but the
        bulk endpoint addresses messages by ID alone.
        """
        account_id = await self._ensure_account_id()
        url = f"/api/accounts/{account_id}/updatemessage"
        ids = [str(message_id)]
        result: dict[str, Any] = {
            "status": {"code": 200, "description": "no changes requested"}
        }

        if is_read is not None:
            result = await self._request(
                "PUT", url,
                json_body={
                    "mode": "markAsRead" if is_read else "markAsUnread",
                    "messageId": ids,
                },
            )
        if is_starred is not None:
            result = await self._request(
                "PUT", url,
                json_body={
                    "mode": "setFlag",
                    "flagid": "important" if is_starred else "flag_not_set",
                    "messageId": ids,
                },
            )
        if move_to_folder_id:
            result = await self._request(
                "PUT", url,
                json_body={
                    "mode": "moveMessage",
                    "destfolderId": str(move_to_folder_id),
                    "messageId": ids,
                },
            )
        return result

    async def delete_message(self, message_id: str, folder_id: str) -> dict[str, Any]:
        """Reversibly "delete" a message by MOVING it to Trash.

        This never calls Zoho's DELETE verb and never expunges, so the message
        stays recoverable (restore it with :meth:`restore_message`).

        If the message is already in Trash, the request is REFUSED — re-deleting
        from Trash is how Zoho permanently destroys mail, which this server forbids.
        """
        trash_id = await self._resolve_folder_id(TRASH_FOLDER_NAME)
        if trash_id is None:
            raise UnrecoverableOperationError(
                "Could not resolve the Trash folder; refusing to delete."
            )
        if str(folder_id) == trash_id:
            raise UnrecoverableOperationError(
                "Message is already in Trash. Permanent deletion / emptying Trash "
                "is disabled by this server. Use restore_message to move it back to "
                "the Inbox, or leave it in Trash to expire under Zoho's retention."
            )
        return await self.modify_message(
            message_id, folder_id, move_to_folder_id=trash_id
        )

    async def restore_message(
        self,
        message_id: str,
        folder_id: str,
        dest_folder_id: str | None = None,
    ) -> dict[str, Any]:
        """Restore a message out of Trash (or any folder) back to the Inbox.

        Provide ``dest_folder_id`` to restore into a specific folder; otherwise
        the message is moved back to the Inbox.
        """
        if not dest_folder_id:
            dest_folder_id = await self._resolve_folder_id(INBOX_FOLDER_NAME)
            if dest_folder_id is None:
                raise RuntimeError(
                    "Could not resolve the Inbox folder; "
                    "pass dest_folder_id explicitly to restore."
                )
        return await self.modify_message(
            message_id, folder_id, move_to_folder_id=dest_folder_id
        )

    # ── Drafts ─────────────────────────────────────────────────────

    async def list_drafts(
        self,
        *,
        max_results: int = 20,
        start: int = 0,
    ) -> dict[str, Any]:
        """List messages in the Drafts folder.

        Zoho 404s on ``/folders/{id}/messages`` folder listings; the working
        listing endpoint is ``/messages/view?folderId=`` (same one
        ``search_messages`` uses for empty queries).
        """
        account_id = await self._ensure_account_id()
        drafts_folder_id = await self._resolve_folder_id("Drafts")
        if not drafts_folder_id:
            return {"status": {"code": 200}, "data": []}

        return await self._request(
            "GET",
            f"/api/accounts/{account_id}/messages/view",
            params={
                "folderId": drafts_folder_id,
                "limit": max_results,
                "start": start,
            },
        )

    async def _ensure_from_address(self) -> str:
        """Cache + return the primary email for this account (required by Zoho)."""
        if getattr(self, "_from_address", None):
            return self._from_address  # type: ignore[attr-defined]
        account_id = await self._ensure_account_id()
        resp = await self._request("GET", f"/api/accounts/{account_id}")
        data = resp.get("data", {})
        # Prefer primary from the emailAddress array; fall back to incomingUserName
        emails = data.get("emailAddress") or []
        primary = next((e.get("mailId") for e in emails if e.get("isPrimary")), None)
        self._from_address = primary or data.get("incomingUserName", "")
        return self._from_address  # type: ignore[return-value]

    async def create_draft(
        self,
        body: str,
        *,
        to: str = "",
        subject: str = "",
        cc: str = "",
        bcc: str = "",
        content_type: str = "text/plain",
        thread_id: str = "",
        folder_id: str = "",
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Create a draft. Zoho requires ``fromAddress`` and ``mode='draft'``.

        ``attachments`` takes the descriptors returned by
        :meth:`upload_attachment` (``storeName`` / ``attachmentPath`` /
        ``attachmentName``) — upload first, then reference them here.
        """
        account_id = await self._ensure_account_id()
        from_addr = await self._ensure_from_address()
        is_html = content_type == "text/html"
        payload: dict[str, Any] = {
            "fromAddress": from_addr,
            "mode": "draft",
            "content": body,
            "mailFormat": "html" if is_html else "plaintext",
        }
        if to:
            payload["toAddress"] = to
        if subject:
            payload["subject"] = subject
        if cc:
            payload["ccAddress"] = cc
        if bcc:
            payload["bccAddress"] = bcc
        if thread_id:
            payload["threadId"] = thread_id
        if folder_id:
            payload["folderId"] = folder_id
        if attachments:
            payload["attachments"] = attachments
        return await self._request(
            "POST", f"/api/accounts/{account_id}/messages", json_body=payload
        )

    async def send_draft(
        self, draft_message_id: str, *, delete_after_send: bool = True
    ) -> dict[str, Any]:
        """Send a saved draft.

        Zoho Mail's REST API has no "send this draft" operation — ``POST
        /messages/{id}`` is *reply*, and ``mode=send`` returns HTTP 400 (verified
        2026-09-02 against six real drafts). The only way to send a draft's
        content is to rebuild it as a fresh message:

          1. read the draft's headers (``/details``) and body (``/content``)
          2. download each stored attachment and re-upload it to the attachment
             store, because ``storeName``/``attachmentPath`` descriptors are not
             retrievable from a saved draft
          3. ``POST /messages`` (no ``mode``) — the documented send call
          4. move the draft to Trash (reversible) so it cannot be sent twice;
             pass ``delete_after_send=False`` to keep it

        Returns the send response plus ``draftMessageId`` and
        ``draftMovedToTrash``.
        """
        account_id = await self._ensure_account_id()
        drafts_folder_id = await self._resolve_folder_id("Drafts")
        if not drafts_folder_id:
            raise RuntimeError("Could not resolve the Drafts folder")
        base = (
            f"/api/accounts/{account_id}/folders/{drafts_folder_id}"
            f"/messages/{draft_message_id}"
        )
        details = (await self._request("GET", f"{base}/details")).get("data", {})
        content = (await self._request("GET", f"{base}/content")).get("data", {})

        def _addr(field: str) -> str:
            raw = str(details.get(field, "") or "").strip()
            if not raw or raw == "Not Provided":
                return ""
            return html.unescape(raw)

        to_addr = _addr("toAddress")
        if not to_addr:
            raise ValueError(
                f"Draft {draft_message_id} has no recipient (toAddress); add one before sending."
            )

        payload: dict[str, Any] = {
            "fromAddress": _addr("fromAddress") or await self._ensure_from_address(),
            "toAddress": to_addr,
            "subject": html.unescape(str(details.get("subject", "") or "")),
            "content": str(content.get("content", "") or ""),
            "mailFormat": "html",  # /content always returns the stored HTML rendering
        }
        for field in ("ccAddress", "bccAddress"):
            value = _addr(field)
            if value:
                payload[field] = value

        info = (await self._request("GET", f"{base}/attachmentinfo")).get("data", {})
        descriptors: list[dict[str, Any]] = []
        for att in info.get("attachments", []) or []:
            att_id = str(att.get("attachmentId", ""))
            name = str(att.get("attachmentName", "") or f"attachment-{att_id}")
            data = await self._request_bytes(f"{base}/attachments/{att_id}")
            uploaded = await self._request(
                "POST",
                f"/api/accounts/{account_id}/messages/attachments",
                params={"fileName": name},
                content=data,
            )
            got = uploaded.get("data", [])
            descriptors.extend(got if isinstance(got, list) else [got])
        if descriptors:
            payload["attachments"] = descriptors

        result = await self._request(
            "POST", f"/api/accounts/{account_id}/messages", json_body=payload
        )
        moved = False
        if delete_after_send:
            await self.delete_message(draft_message_id, drafts_folder_id)
            moved = True
        return {**result, "draftMessageId": draft_message_id, "draftMovedToTrash": moved}

    # ── Send & Reply ───────────────────────────────────────────────

    async def send_message(
        self,
        to: str,
        subject: str,
        body: str,
        *,
        cc: str = "",
        bcc: str = "",
        content_type: str = "text/plain",
    ) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        is_html = content_type == "text/html"
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
        content_type: str = "text/plain",
        reply_all: bool = False,
    ) -> dict[str, Any]:
        """Reply to a message.

        Zoho's documented call is ``POST /messages/{id}`` with ``action=reply`` (the
        old ``/folders/{fid}/messages/{mid}/reply[all]`` routes 404 — verified
        2026-09-02). There is no reply-all action, so recipients are derived from the
        original's ``/details``: To = the original sender (or ``to`` override);
        with ``reply_all`` every original To/Cc address except our own and the sender
        is added to Cc, plus any ``cc`` given.
        """
        account_id = await self._ensure_account_id()
        from_addr = await self._ensure_from_address()
        details = (await self._request(
            "GET", f"/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}/details"
        )).get("data", {})

        def _addrs(field: str) -> list[str]:
            raw = str(details.get(field, "") or "")
            if not raw or raw == "Not Provided":
                return []
            return [a for _, a in getaddresses([html.unescape(raw)]) if a]

        sender = _addrs("fromAddress")
        to_addr = to or (sender[0] if sender else "")
        if not to_addr:
            raise ValueError(f"Cannot determine a recipient for reply to message {message_id}")

        cc_list: list[str] = []
        if reply_all:
            skip = {from_addr.lower(), to_addr.lower()}
            for a in _addrs("toAddress") + _addrs("ccAddress"):
                if a.lower() not in skip and a.lower() not in {c.lower() for c in cc_list}:
                    cc_list.append(a)
        for a in [c.strip() for c in cc.split(",") if c.strip()]:
            if a.lower() not in {c.lower() for c in cc_list} and a.lower() != to_addr.lower():
                cc_list.append(a)

        subject = html.unescape(str(details.get("subject", "") or ""))
        if not subject.lower().startswith("re:"):
            subject = f"Re: {subject}".strip()

        is_html = content_type == "text/html"
        payload: dict[str, Any] = {
            "fromAddress": from_addr,
            "toAddress": to_addr,
            "subject": subject,
            "content": body,
            "mailFormat": "html" if is_html else "plaintext",
            "action": "reply",
        }
        if cc_list:
            payload["ccAddress"] = ", ".join(cc_list)
        if bcc:
            payload["bccAddress"] = bcc
        return await self._request(
            "POST", f"/api/accounts/{account_id}/messages/{message_id}", json_body=payload
        )

    # ── Attachments ────────────────────────────────────────────────

    async def upload_attachment(self, file_path: str) -> list[dict[str, Any]]:
        """Upload a local file to Zoho's attachment store.

        POSTs the raw bytes to ``/messages/attachments?fileName=`` and returns
        the descriptor list (``storeName`` / ``attachmentPath`` /
        ``attachmentName``) that a draft or send payload references in its
        ``attachments`` array.
        """
        account_id = await self._ensure_account_id()
        path = Path(file_path).expanduser()
        file_bytes = path.read_bytes()
        resp = await self._request(
            "POST",
            f"/api/accounts/{account_id}/messages/attachments",
            params={"fileName": path.name},
            content=file_bytes,
        )
        descriptor = resp.get("data", [])
        return descriptor if isinstance(descriptor, list) else [descriptor]

    async def get_attachment(
        self, message_id: str, folder_id: str, attachment_id: str
    ) -> dict[str, Any]:
        account_id = await self._ensure_account_id()
        return await self._request(
            "GET",
            f"/api/accounts/{account_id}/folders/{folder_id}/messages/{message_id}/attachments/{attachment_id}",
        )


def _load_credential(key: str, profile: str | None) -> str:
    """Resolve a credential, preferring env vars, falling back to macOS Keychain.

    Resolution order:
      1. Environment variable (e.g. ``ZOHO_CLIENT_ID``) — set by caller or .env
      2. macOS Keychain service ``zoho-mail-<profile>`` with account ``key``

    Raises ``KeyError`` if neither source has a value.
    """
    env_val = os.environ.get(f"ZOHO_{key}")
    if env_val:
        return env_val

    if profile:
        try:
            import keyring

            val = keyring.get_password(f"zoho-mail-{profile}", key)
            if val:
                return val
        except ImportError:
            pass  # keyring not installed — fall through to error

    raise KeyError(
        f"ZOHO_{key} not found. Set env var ZOHO_{key} or store in Keychain "
        f"under service 'zoho-mail-{profile or '<profile>'}' account '{key}'."
    )


def create_client_from_env() -> ZohoMailClient:
    """Factory: build a ZohoMailClient from env vars, with Keychain fallback.

    If ``ZOHO_PROFILE`` is set (e.g. ``rachel`` or ``vincent``), missing env
    vars are looked up in the macOS Keychain under service
    ``zoho-mail-<profile>``. This lets us register multiple MCP instances
    pointing at the same ``server.py`` but different profiles, with zero
    plaintext secrets in the MCP config or .env files.
    """
    profile = os.environ.get("ZOHO_PROFILE")
    token_cache = TokenCache(
        client_id=_load_credential("CLIENT_ID", profile),
        client_secret=_load_credential("CLIENT_SECRET", profile),
        refresh_token=_load_credential("REFRESH_TOKEN", profile),
        accounts_url=os.environ.get("ZOHO_ACCOUNTS_URL", "https://accounts.zoho.com"),
    )
    return ZohoMailClient(
        token_cache=token_cache,
        base_url=os.environ.get("ZOHO_MAIL_BASE_URL", "https://mail.zoho.com"),
        account_id=os.environ.get("ZOHO_ACCOUNT_ID"),
    )
