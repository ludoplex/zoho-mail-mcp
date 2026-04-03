# Zoho Mail MCP Server

MCP server for Zoho Mail — gives Claude (and any MCP client) full access to your Zoho Mail account via 14 tools.

## Tools

| Tool | Description | Safety |
|---|---|---|
| `zoho_get_profile` | Get account profile | Read-only |
| `zoho_search_messages` | Search emails by query | Read-only |
| `zoho_read_message` | Read a specific email | Read-only |
| `zoho_read_thread` | Read an email thread | Read-only |
| `zoho_list_folders` | List mail folders | Read-only |
| `zoho_list_labels` | List labels/tags | Read-only |
| `zoho_list_drafts` | List saved drafts | Read-only |
| `zoho_get_attachment` | Get attachment metadata | Read-only |
| `zoho_create_draft` | Create a draft | Write (non-destructive) |
| `zoho_send_draft` | Send an existing draft | Write (destructive) |
| `zoho_send_message` | Send an email | Write (destructive) |
| `zoho_reply_to_message` | Reply / reply-all | Write (destructive) |
| `zoho_modify_message` | Mark read/star/move | Write (destructive, idempotent) |
| `zoho_delete_message` | Delete (trash) an email | Write (destructive, idempotent) |

All tools carry MCP ToolAnnotations with `readOnlyHint`, `destructiveHint`, `idempotentHint`, and `openWorldHint` set appropriately.

## Usage Examples

### Example 1: Search and read recent emails

Prompt: "Show me my most recent emails"

The assistant calls `zoho_search_messages` with default parameters to retrieve the latest 20 messages, then summarizes senders, subjects, and dates.

### Example 2: Send an email

Prompt: "Send an email to alice@example.com with the subject 'Project Update' and let her know the deadline moved to Friday"

The assistant calls `zoho_send_message` with:
- `to`: "alice@example.com"
- `subject`: "Project Update"
- `body`: "Hi Alice, just a heads-up — the project deadline has moved to Friday. Let me know if you have questions."

### Example 3: Find and reply to a thread

Prompt: "Find the email thread from Bob about the budget and reply saying I approve"

The assistant calls `zoho_search_messages` with `q: "from:bob subject:budget"`, reads the thread with `zoho_read_thread`, then calls `zoho_reply_to_message` with the body "Approved — looks good to me."

### Example 4: Organize messages

Prompt: "Star all unread emails from my manager and mark them as read"

The assistant calls `zoho_search_messages` to find unread messages from the manager, then calls `zoho_modify_message` on each with `isRead: true` and `isStarred: true`.

## Setup

### 1. Zoho OAuth Credentials

1. Go to [Zoho API Console](https://api-console.zoho.com/)
2. Create a Self Client
3. Generate a grant code with scopes:
   ```
   ZohoMail.messages.ALL,ZohoMail.folders.ALL,ZohoMail.tags.ALL,ZohoMail.accounts.READ,ZohoMail.attachments.READ
   ```
4. Exchange the grant code for a refresh token
5. Copy your Client ID, Client Secret, and Refresh Token

### 2. Configure

```bash
cp env.example .env
# Edit .env with your credentials
```

### 3. Install & Run

**Standalone:**
```bash
pip install -r requirements.txt
python server.py
```

**Docker:**
```bash
docker compose up --build
```

### 4. Connect to Claude

Add to your Claude MCP config (`~/.claude/claude_desktop_config.json` or Claude.ai settings):

```json
{
  "mcpServers": {
    "zoho-mail": {
      "command": "python",
      "args": ["/path/to/zoho-mail-mcp/server.py"],
      "env": {
        "ZOHO_CLIENT_ID": "your_client_id",
        "ZOHO_CLIENT_SECRET": "your_client_secret",
        "ZOHO_REFRESH_TOKEN": "your_refresh_token"
      }
    }
  }
}
```

## Testing

```bash
pip install pytest pytest-asyncio respx
pytest tests/ -v
```

## Data Centers

Set `ZOHO_MAIL_BASE_URL` and `ZOHO_ACCOUNTS_URL` for your region:

| Region | Mail URL | Accounts URL |
|---|---|---|
| US | `https://mail.zoho.com` | `https://accounts.zoho.com` |
| EU | `https://mail.zoho.eu` | `https://accounts.zoho.eu` |
| India | `https://mail.zoho.in` | `https://accounts.zoho.in` |
| Australia | `https://mail.zoho.com.au` | `https://accounts.zoho.com.au` |
| Japan | `https://mail.zoho.jp` | `https://accounts.zoho.jp` |

## Privacy Policy

This MCP server acts as a local bridge between your MCP client (Claude, etc.) and the Zoho Mail API. It does not collect, store, transmit, or log any user data beyond what is required for OAuth token management (refresh token stored in your local `.env` file). No data is sent to any third party. All API calls go directly from your machine to Zoho's servers using your own OAuth credentials. No telemetry, analytics, or tracking of any kind is included.

## Support

File issues at [github.com/ludoplex/zoho-mail-mcp/issues](https://github.com/ludoplex/zoho-mail-mcp/issues).

## License

MIT
