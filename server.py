"""Zoho Mail MCP Server — 15 tools via FastMCP.

Safety policy: this server cannot permanently destroy mail. "Delete" moves a
message to Trash (reversible), Trashed mail can be restored, and the transport
layer refuses permanent-delete / empty-folder operations outright.
"""

from __future__ import annotations

import json
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

# Make imports work regardless of CWD (Claude may launch us from anywhere).
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from zoho_client import (
    UnrecoverableOperationError,
    ZohoMailClient,
    create_client_from_env,
)

# Load .env from the server's own directory — not from the caller's CWD.
load_dotenv(_HERE / ".env")

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


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
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


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
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


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
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


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
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


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
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


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
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


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
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


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
async def zoho_create_draft(
    body: str,
    to: str = "",
    subject: str = "",
    cc: str = "",
    bcc: str = "",
    contentType: Literal["text/plain", "text/html"] = "text/plain",
    threadId: str = "",
    folderId: str = "",
    attachments: list[str] | None = None,
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

    ATTACHMENTS:
    - Pass local file paths in the attachments list; each file is uploaded to
      Zoho's attachment store first, then referenced by the draft

    Args:
        body: Email body content (plain text or HTML based on contentType)
        to: Primary recipient email address(es). Can be omitted to save a draft without a recipient yet
        subject: Email subject line. Required when threadId is not provided. When threadId is provided and subject is omitted, it is automatically derived from the thread
        cc: Carbon copy recipients (comma-separated)
        bcc: Blind carbon copy recipients (comma-separated)
        contentType: Content type of the email body — "text/plain" (default) or "text/html"
        threadId: Thread ID to reply to. When provided, the draft is created as a reply within that thread
        folderId: Optional folder ID to save the draft in
        attachments: Optional list of local file paths to attach to the draft
    """
    assert _client is not None
    attachment_meta: list[dict[str, Any]] = []
    for file_path in attachments or []:
        attachment_meta.extend(await _client.upload_attachment(file_path))
    result = await _client.create_draft(
        body,
        to=to,
        subject=subject,
        cc=cc,
        bcc=bcc,
        content_type=contentType,
        thread_id=threadId,
        folder_id=folderId,
        attachments=attachment_meta or None,
    )
    return _fmt(result)


# ── 9. Send Draft ─────────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True))
async def zoho_send_draft(draftMessageId: str) -> str:
    """Sends an existing draft email immediately.

    Use this after zoho_create_draft to send a previously saved draft. The draft
    must exist and have at least a recipient (to) address to be sent successfully.

    Zoho has no native send-draft call, so the server rebuilds the draft as a
    fresh outgoing message (headers, body, and attachments re-uploaded) and then
    moves the draft to Trash (reversible) so it cannot be sent twice.

    The response includes:
    - The sent message details on success, plus draftMessageId and
      draftMovedToTrash
    - An error if the draft was not found or has no recipient

    Args:
        draftMessageId: The message ID of the draft to send (obtained from zoho_create_draft or zoho_list_drafts)
    """
    assert _client is not None
    result = await _client.send_draft(draftMessageId)
    return _fmt(result)



# ── 10. Send Message ─────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True))
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


# ── 11. Reply to Message ──────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=True))
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


# ── 12. Modify Message ────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True))
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


# ── 13. Delete Message (move to Trash — reversible) ───────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True))
async def zoho_delete_message(messageId: str, folderId: str) -> str:
    """Deletes a message by moving it to Trash. The delete is ALWAYS reversible.

    This server cannot permanently delete mail. "Deleting" moves the message to
    the Trash folder, from which it can be recovered with zoho_restore_message.

    REFUSED CASES (returns a "refused" result, takes no action):
    - The message is already in Trash. Re-deleting from Trash is how mail is
      permanently destroyed, which is disabled. Restore it or let it expire.

    Args:
        messageId: The ID of the message to delete (move to Trash)
        folderId: The folder ID currently containing the message
    """
    assert _client is not None
    try:
        result = await _client.delete_message(messageId, folderId)
    except UnrecoverableOperationError as exc:
        return _fmt({"refused": True, "reason": str(exc)})
    return _fmt(result)


# ── 14. Restore Message (move out of Trash) ───────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def zoho_restore_message(
    messageId: str, folderId: str, toFolderId: str = ""
) -> str:
    """Restores a message out of Trash (or any folder) back to the Inbox.

    Use this to undo a delete or recover anything sitting in Trash. By default the
    message is moved back to the Inbox; pass toFolderId to restore it elsewhere.

    Args:
        messageId: The ID of the message to restore
        folderId: The folder ID currently containing the message (e.g. Trash)
        toFolderId: Optional destination folder ID. Defaults to the Inbox when empty
    """
    assert _client is not None
    try:
        result = await _client.restore_message(
            messageId, folderId, dest_folder_id=toFolderId or None
        )
    except UnrecoverableOperationError as exc:
        return _fmt({"refused": True, "reason": str(exc)})
    return _fmt(result)


# ── 15. Get Attachment ─────────────────────────────────────────────


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
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
