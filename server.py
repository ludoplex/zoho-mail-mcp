"""Zoho Mail MCP Server — 12 tools via FastMCP."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from zoho_client import ZohoMailClient, create_client_from_env

load_dotenv()

_client: ZohoMailClient | None = None


@asynccontextmanager
async def lifespan(server: FastMCP):
    global _client
    _client = create_client_from_env()
    try:
        yield
    finally:
        await _client.close()
        _client = None


mcp = FastMCP("zoho-mail", lifespan=lifespan)


def _fmt(data: dict[str, Any]) -> str:
    return json.dumps(data, indent=2, default=str)


# ── 1. Profile ────────────────────────────────────────────────────


@mcp.tool()
async def zoho_get_profile() -> str:
    """Get the authenticated Zoho Mail account profile."""
    assert _client is not None
    result = await _client.get_profile()
    return _fmt(result)


# ── 2. Search Messages ────────────────────────────────────────────


@mcp.tool()
async def zoho_search_messages(
    query: str,
    folder_id: str = "",
    limit: int = 10,
    start: int = 0,
) -> str:
    """Search emails by query string. Optionally filter by folder_id."""
    assert _client is not None
    result = await _client.search_messages(
        query, folder_id=folder_id or None, limit=limit, start=start
    )
    return _fmt(result)


# ── 3. Read Message ───────────────────────────────────────────────


@mcp.tool()
async def zoho_read_message(message_id: str, folder_id: str) -> str:
    """Read a specific email message by its ID and folder ID."""
    assert _client is not None
    result = await _client.read_message(message_id, folder_id)
    return _fmt(result)


# ── 4. Read Thread ────────────────────────────────────────────────


@mcp.tool()
async def zoho_read_thread(thread_id: str, folder_id: str) -> str:
    """Read an entire email thread/conversation."""
    assert _client is not None
    result = await _client.read_thread(thread_id, folder_id)
    return _fmt(result)


# ── 5. Create Draft ───────────────────────────────────────────────


@mcp.tool()
async def zoho_create_draft(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    is_html: bool = True,
) -> str:
    """Create an email draft (not sent)."""
    assert _client is not None
    result = await _client.create_draft(
        to, subject, body, cc=cc, bcc=bcc, is_html=is_html
    )
    return _fmt(result)


# ── 6. Send Message ───────────────────────────────────────────────


@mcp.tool()
async def zoho_send_message(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    is_html: bool = True,
) -> str:
    """Compose and send an email immediately."""
    assert _client is not None
    result = await _client.send_message(
        to, subject, body, cc=cc, bcc=bcc, is_html=is_html
    )
    return _fmt(result)


# ── 7. Reply to Message ───────────────────────────────────────────


@mcp.tool()
async def zoho_reply_to_message(
    message_id: str,
    folder_id: str,
    body: str,
    to: str = "",
    cc: str = "",
    bcc: str = "",
    is_html: bool = True,
    reply_all: bool = False,
) -> str:
    """Reply to an existing email message. Set reply_all=True for reply-all."""
    assert _client is not None
    result = await _client.reply_to_message(
        message_id, folder_id, body, to=to, cc=cc, bcc=bcc, is_html=is_html, reply_all=reply_all
    )
    return _fmt(result)


# ── 8. List Folders ───────────────────────────────────────────────


@mcp.tool()
async def zoho_list_folders() -> str:
    """List all mail folders (Inbox, Sent, Drafts, custom folders, etc.)."""
    assert _client is not None
    result = await _client.list_folders()
    return _fmt(result)


# ── 9. List Labels ────────────────────────────────────────────────


@mcp.tool()
async def zoho_list_labels() -> str:
    """List all mail labels/tags."""
    assert _client is not None
    result = await _client.list_labels()
    return _fmt(result)


# ── 10. Modify Message ────────────────────────────────────────────


@mcp.tool()
async def zoho_modify_message(
    message_id: str,
    folder_id: str,
    is_read: bool | None = None,
    is_starred: bool | None = None,
    move_to_folder_id: str = "",
) -> str:
    """Modify a message: mark read/unread, star/unstar, or move to another folder."""
    assert _client is not None
    result = await _client.modify_message(
        message_id,
        folder_id,
        is_read=is_read,
        is_starred=is_starred,
        move_to_folder_id=move_to_folder_id or None,
    )
    return _fmt(result)


# ── 11. Delete Message ────────────────────────────────────────────


@mcp.tool()
async def zoho_delete_message(message_id: str, folder_id: str) -> str:
    """Delete (trash) an email message."""
    assert _client is not None
    result = await _client.delete_message(message_id, folder_id)
    return _fmt(result)


# ── 12. Get Attachment ─────────────────────────────────────────────


@mcp.tool()
async def zoho_get_attachment(
    message_id: str, folder_id: str, attachment_id: str
) -> str:
    """Download/retrieve metadata for a specific email attachment."""
    assert _client is not None
    result = await _client.get_attachment(message_id, folder_id, attachment_id)
    return _fmt(result)


if __name__ == "__main__":
    mcp.run()
