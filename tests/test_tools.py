"""Integration tests for all 13 MCP tools against mocked Zoho API."""

from __future__ import annotations

import json

import pytest
import respx

from tests.conftest import FAKE_ACCOUNT_ID, MAIL_BASE


@pytest.mark.asyncio
async def test_get_profile(client, mock_api):
    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}").respond(
        json={"status": {"code": 200}, "data": {"accountId": FAKE_ACCOUNT_ID, "emailAddress": "test@example.com"}}
    )
    result = await client.get_profile()
    assert result["data"]["accountId"] == FAKE_ACCOUNT_ID


@pytest.mark.asyncio
async def test_list_folders(client, mock_api):
    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders").respond(
        json={"status": {"code": 200}, "data": [{"folderId": "1", "folderName": "Inbox"}]}
    )
    result = await client.list_folders()
    assert len(result["data"]) == 1
    assert result["data"][0]["folderName"] == "Inbox"


@pytest.mark.asyncio
async def test_list_labels(client, mock_api):
    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/tags").respond(
        json={"status": {"code": 200}, "data": [{"tagId": "t1", "tagName": "Important"}]}
    )
    result = await client.list_labels()
    assert result["data"][0]["tagName"] == "Important"


@pytest.mark.asyncio
async def test_search_messages(client, mock_api):
    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/messages/search").respond(
        json={"status": {"code": 200}, "data": [{"messageId": "m1", "subject": "Hello"}]}
    )
    result = await client.search_messages(q="Hello")
    assert result["data"][0]["subject"] == "Hello"


@pytest.mark.asyncio
async def test_search_messages_defaults(client, mock_api):
    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/messages/search").respond(
        json={"status": {"code": 200}, "data": []}
    )
    result = await client.search_messages()
    assert result["data"] == []


@pytest.mark.asyncio
async def test_read_message(client, mock_api):
    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders/f1/messages/m1").respond(
        json={"status": {"code": 200}, "data": {"messageId": "m1", "content": "body text"}}
    )
    result = await client.read_message("m1", "f1")
    assert result["data"]["messageId"] == "m1"


@pytest.mark.asyncio
async def test_read_thread(client, mock_api):
    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders/f1/threads/t1").respond(
        json={"status": {"code": 200}, "data": {"threadId": "t1", "messageCount": 3}}
    )
    result = await client.read_thread("t1", "f1")
    assert result["data"]["threadId"] == "t1"


@pytest.mark.asyncio
async def test_list_drafts(client, mock_api):
    # list_drafts first fetches folders to find the Drafts folder
    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders").respond(
        json={"status": {"code": 200}, "data": [
            {"folderId": "100", "folderName": "Inbox"},
            {"folderId": "200", "folderName": "Drafts"},
        ]}
    )
    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders/200/messages").respond(
        json={"status": {"code": 200}, "data": [{"messageId": "d1", "subject": "My draft"}]}
    )
    result = await client.list_drafts()
    assert result["data"][0]["subject"] == "My draft"


@pytest.mark.asyncio
async def test_list_drafts_no_folder(client, mock_api):
    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders").respond(
        json={"status": {"code": 200}, "data": [{"folderId": "100", "folderName": "Inbox"}]}
    )
    result = await client.list_drafts()
    assert result["data"] == []


@pytest.mark.asyncio
async def test_create_draft_minimal(client, mock_api):
    mock_api.post(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/messages").respond(
        json={"status": {"code": 200}, "data": {"messageId": "d1"}}
    )
    result = await client.create_draft("Draft body")
    assert result["data"]["messageId"] == "d1"


@pytest.mark.asyncio
async def test_create_draft_with_thread(client, mock_api):
    mock_api.post(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/messages").respond(
        json={"status": {"code": 200}, "data": {"messageId": "d2"}}
    )
    result = await client.create_draft(
        "Reply draft", to="bob@example.com", thread_id="t1", content_type="text/html"
    )
    assert result["data"]["messageId"] == "d2"


@pytest.mark.asyncio
async def test_send_message(client, mock_api):
    mock_api.post(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/messages").respond(
        json={"status": {"code": 200}, "data": {"messageId": "s1"}}
    )
    result = await client.send_message("to@example.com", "Subject", "Body")
    assert result["data"]["messageId"] == "s1"


@pytest.mark.asyncio
async def test_send_message_html(client, mock_api):
    mock_api.post(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/messages").respond(
        json={"status": {"code": 200}, "data": {"messageId": "s2"}}
    )
    result = await client.send_message(
        "to@example.com", "Subject", "<p>HTML</p>", content_type="text/html"
    )
    assert result["data"]["messageId"] == "s2"


@pytest.mark.asyncio
async def test_reply_to_message(client, mock_api):
    mock_api.post(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders/f1/messages/m1/reply").respond(
        json={"status": {"code": 200}, "data": {"messageId": "r1"}}
    )
    result = await client.reply_to_message("m1", "f1", "Reply body")
    assert result["data"]["messageId"] == "r1"


@pytest.mark.asyncio
async def test_reply_all(client, mock_api):
    mock_api.post(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders/f1/messages/m1/replyall").respond(
        json={"status": {"code": 200}, "data": {"messageId": "ra1"}}
    )
    result = await client.reply_to_message("m1", "f1", "Reply all body", reply_all=True)
    assert result["data"]["messageId"] == "ra1"


@pytest.mark.asyncio
async def test_modify_message_mark_read(client, mock_api):
    mock_api.put(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders/f1/messages/m1").respond(
        json={"status": {"code": 200}, "data": {"messageId": "m1"}}
    )
    result = await client.modify_message("m1", "f1", is_read=True)
    assert result["status"]["code"] == 200


@pytest.mark.asyncio
async def test_delete_message(client, mock_api):
    mock_api.delete(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders/f1/messages/m1").respond(
        json={"status": {"code": 200}}
    )
    result = await client.delete_message("m1", "f1")
    assert result["status"]["code"] == 200


@pytest.mark.asyncio
async def test_get_attachment(client, mock_api):
    mock_api.get(
        f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders/f1/messages/m1/attachments/a1"
    ).respond(
        json={"status": {"code": 200}, "data": {"attachmentId": "a1", "fileName": "doc.pdf"}}
    )
    result = await client.get_attachment("m1", "f1", "a1")
    assert result["data"]["fileName"] == "doc.pdf"


@pytest.mark.asyncio
async def test_401_retry(client, mock_api):
    """On 401, client should invalidate token, re-auth, and retry."""
    call_count = 0

    def handler(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return respx.MockResponse(401)
        return respx.MockResponse(
            200, json={"status": {"code": 200}, "data": [{"folderId": "1"}]}
        )

    mock_api.get(f"{MAIL_BASE}/api/accounts/{FAKE_ACCOUNT_ID}/folders").mock(
        side_effect=handler
    )
    result = await client.list_folders()
    assert call_count == 2
    assert result["data"][0]["folderId"] == "1"
