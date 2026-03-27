"""Zoho Mail MCP Server — 13 tools via FastMCP."""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, Literal

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
    """Retrieves your Zoho Mail profile information, including email address and account details.

    This tool fetches basic profile data for the currently authenticated Zoho Mail account.

    Args:
        None
    """
    assert _client is not None
    result = await _client.get_profile()
    return _fmt(result)


# ── 2. Search Messages ────────────────────────────────────────────


@mcp.tool()
async def zoho_search_messages(
    q: str = "",
    maxResults: int = 20,
    start: int = 0,
    folderId: str = "",
    includeSpamTrash: bool = False,
) -> str:
    """Searches Zoho Mail messages using query syntax with support for filtering by sender, recipient, subject, folders, dates, and more.

    This tool provides access to Zoho Mail's search capabilities.

    ZOHO SEARCH SYNTAX:
    - from:sender@example.com — Messages from specific sender
    - to:recipient@example.com — Messages to specific recipient
    - subject:meeting — Messages with "meeting" in subject
    - has:attachment — Messages with attachments
    - after:2024/1/1 before:2024/12/31 — Date range
    - "exact phrase" — Exact phrase match
    - Combine multiple: from:boss@company.com has:attachment

    PAGINATION: Results are limited per request. Use start offset for pagination:
    1. First call returns messages up to maxResults
    2. Call again with start=maxResults to get next batch
    3. Continue until fewer results are returned than requested

    Args:
        q: Search query string. If omitted, returns most recent messages
        maxResults: Maximum messages to return per request (default: 20)
        start: Offset for pagination (default: 0)
        folderId: Optional folder ID to restrict search to a specific folder
        includeSpamTrash: Include messages from Spam and Trash folders (default: false)
    """
    assert _client is not None
    result = await _client.search_messages(
        q=q,
        max_results=maxResults,
        start=start,
        folder_id=folderId or None,
        include_spam_trash=includeSpamTrash,
    )
    return _fmt(result)


# ── 3. Read Message ───────────────────────────────────────────────


@mcp.tool()
async def zoho_read_message(messageId: str, folderId: str) -> str:
    """Retrieves the complete content and metadata of a specific Zoho Mail message including headers, body, and attachment information.

    This tool fetches full details of a single email message using its unique ID.

    Args:
        messageId: The unique ID of the message to retrieve (obtained from zoho_search_messages)
        folderId: The folder ID containing the message (obtained from zoho_search_messages or zoho_list_folders)
    """
    assert _client is not None
    result = await _client.read_message(messageId, folderId)
    return _fmt(result)


# ── 4. Read Thread ────────────────────────────────────────────────


@mcp.tool()
async def zoho_read_thread(threadId: str, folderId: str) -> str:
    """Retrieves a complete email conversation thread including all messages in chronological order.

    This tool fetches an entire email thread (conversation) with all its messages.

    Args:
        threadId: The unique ID of the thread to retrieve (obtained from zoho_search_messages)
        folderId: The folder ID containing the thread (obtained from zoho_search_messages or zoho_list_folders)
    """
    assert _client is not None
    result = await _client.read_thread(threadId, folderId)
    return _fmt(result)


# ── 5. List Folders ───────────────────────────────────────────────


@mcp.tool()
async def zoho_list_folders() -> str:
    """Lists all mail folders in your Zoho Mail account.

    Returns system folders (Inbox, Sent, Drafts, Spam, Trash) and user-created folders.
    Use the returned folder IDs with zoho_read_message, zoho_read_thread, zoho_modify_message, and other tools that require a folderId.

    Args:
        None
    """
    assert _client is not None
    result = await _client.list_folders()
    return _fmt(result)


# ── 6. List Labels ────────────────────────────────────────────────


@mcp.tool()
async def zoho_list_labels() -> str:
    """Lists all labels/tags in your Zoho Mail account.

    Returns all user-created labels. Use the returned IDs with zoho_modify_message.

    Args:
        None
    """
    assert _client is not None
    result = await _client.list_labels()
    return _fmt(result)


# ── 7. List Drafts ────────────────────────────────────────────────


@mcp.tool()
async def zoho_list_drafts(
    maxResults: int = 20,
    start: int = 0,
) -> str:
    """Lists all saved email drafts in your Zoho Mail account with their content and metadata.

    This tool retrieves all unsent email drafts.

    PAGINATION: When you have many drafts, results are paginated:
    1. First call returns drafts up to maxResults
    2. Call again with start=maxResults to get additional drafts
    3. Continue until fewer results are returned than requested

    Args:
        maxResults: Maximum number of drafts to return per request (default: 20)
        start: Offset for pagination (default: 0)
    """
    assert _client is not None
    result = await _client.list_drafts(max_results=maxResults, start=start)
    return _fmt(result)


# ── 8. Create Draft ───────────────────────────────────────────────


@mcp.tool()
async def zoho_create_draft(
    body: str,
    to: str = "",
    subject: str = "",
    cc: str = "",
    bcc: str = "",
    contentType: Literal["text/plain", "text/html"] = "text/plain",
    threadId: str = "",
    folderId: str = "",
) -> str:
    """Creates a new email draft that can be edited and sent later.

    This tool creates a draft email with specified recipients, subject, and body content.
    It can also create a draft reply to an existing thread by providing the threadId parameter.

    CONTENT TYPES:
    - text/plain: Simple text emails (default)
    - text/html: Rich HTML emails with formatting, links, images, etc.

    RECIPIENT FORMATS:
    - Single: "user@example.com"
    - Multiple: "user1@example.com, user2@example.com"
    - With names: "John Doe <john@example.com>, Jane Smith <jane@example.com>"

    DRAFT REPLIES:
    - Provide threadId to create a draft reply within an existing thread
    - The subject is automatically derived from the thread when not provided

    Args:
        body: Email body content (plain text or HTML based on contentType)
        to: Primary recipient email address(es). Can be omitted to save a draft without a recipient yet
        subject: Email subject line. Required when threadId is not provided. When threadId is provided and subject is omitted, it is automatically derived from the thread
        cc: Carbon copy recipients (comma-separated)
        bcc: Blind carbon copy recipients (comma-separated)
        contentType: Content type of the email body — "text/plain" (default) or "text/html"
        threadId: Thread ID to reply to. When provided, the draft is created as a reply within that thread
        folderId: Optional folder ID to save the draft in
    """
    assert _client is not None
    result = await _client.create_draft(
        body,
        to=to,
        subject=subject,
        cc=cc,
        bcc=bcc,
        content_type=contentType,
        thread_id=threadId,
        folder_id=folderId,
    )
    return _fmt(result)


# ── 9. Send Message ───────────────────────────────────────────────


@mcp.tool()
async def zoho_send_message(
    to: str,
    subject: str,
    body: str,
    cc: str = "",
    bcc: str = "",
    contentType: Literal["text/plain", "text/html"] = "text/plain",
) -> str:
    """Composes and sends an email immediately.

    CONTENT TYPES:
    - text/plain: Simple text emails (default)
    - text/html: Rich HTML emails with formatting, links, images, etc.

    RECIPIENT FORMATS:
    - Single: "user@example.com"
    - Multiple: "user1@example.com, user2@example.com"
    - With names: "John Doe <john@example.com>, Jane Smith <jane@example.com>"

    Args:
        to: Primary recipient email address(es), comma-separated for multiple
        subject: Email subject line
        body: Email body content (plain text or HTML based on contentType)
        cc: Carbon copy recipients (comma-separated)
        bcc: Blind carbon copy recipients (comma-separated)
        contentType: Content type of the email body — "text/plain" (default) or "text/html"
    """
    assert _client is not None
    result = await _client.send_message(
        to, subject, body, cc=cc, bcc=bcc, content_type=contentType
    )
    return _fmt(result)


# ── 10. Reply to Message ──────────────────────────────────────────


@mcp.tool()
async def zoho_reply_to_message(
    messageId: str,
    folderId: str,
    body: str,
    to: str = "",
    cc: str = "",
    bcc: str = "",
    contentType: Literal["text/plain", "text/html"] = "text/plain",
    replyAll: bool = False,
) -> str:
    """Replies to an existing email message. Set replyAll=true for reply-all.

    Args:
        messageId: The ID of the message to reply to
        folderId: The folder ID containing the message
        body: Reply body content (plain text or HTML based on contentType)
        to: Override recipient address(es) (optional, defaults to original sender)
        cc: Carbon copy recipients (comma-separated)
        bcc: Blind carbon copy recipients (comma-separated)
        contentType: Content type — "text/plain" (default) or "text/html"
        replyAll: Set to true to reply to all recipients (default: false)
    """
    assert _client is not None
    result = await _client.reply_to_message(
        messageId, folderId, body,
        to=to, cc=cc, bcc=bcc, content_type=contentType, reply_all=replyAll,
    )
    return _fmt(result)


# ── 11. Modify Message ────────────────────────────────────────────


@mcp.tool()
async def zoho_modify_message(
    messageId: str,
    folderId: str,
    isRead: bool | None = None,
    isStarred: bool | None = None,
    moveToFolderId: str = "",
) -> str:
    """Modifies a message: mark read/unread, star/unstar, or move to another folder.

    Args:
        messageId: The ID of the message to modify
        folderId: The current folder ID of the message
        isRead: Set to true to mark as read, false for unread (optional)
        isStarred: Set to true to star, false to unstar (optional)
        moveToFolderId: Destination folder ID to move the message to (optional)
    """
    assert _client is not None
    result = await _client.modify_message(
        messageId,
        folderId,
        is_read=isRead,
        is_starred=isStarred,
        move_to_folder_id=moveToFolderId or None,
    )
    return _fmt(result)


# ── 12. Delete Message ────────────────────────────────────────────


@mcp.tool()
async def zoho_delete_message(messageId: str, folderId: str) -> str:
    """Deletes (trashes) an email message.

    Args:
        messageId: The ID of the message to delete
        folderId: The folder ID containing the message
    """
    assert _client is not None
    result = await _client.delete_message(messageId, folderId)
    return _fmt(result)


# ── 13. Get Attachment ─────────────────────────────────────────────


@mcp.tool()
async def zoho_get_attachment(
    messageId: str, folderId: str, attachmentId: str
) -> str:
    """Retrieves metadata for a specific email attachment.

    Args:
        messageId: The ID of the message containing the attachment
        folderId: The folder ID containing the message
        attachmentId: The ID of the attachment to retrieve
    """
    assert _client is not None
    result = await _client.get_attachment(messageId, folderId, attachmentId)
    return _fmt(result)


if __name__ == "__main__":
    mcp.run()
