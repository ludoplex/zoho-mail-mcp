# Zoho Mail MCP Server

MCP server for Zoho Mail — gives Claude (and any MCP client) full access to your Zoho Mail account via 12 tools.

## Tools

| Tool | Description |
|---|---|
| `zoho_get_profile` | Get account profile |
| `zoho_search_messages` | Search emails by query |
| `zoho_read_message` | Read a specific email |
| `zoho_read_thread` | Read an email thread |
| `zoho_create_draft` | Create a draft |
| `zoho_send_message` | Send an email |
| `zoho_reply_to_message` | Reply / reply-all |
| `zoho_list_folders` | List mail folders |
| `zoho_list_labels` | List labels/tags |
| `zoho_modify_message` | Mark read/star/move |
| `zoho_delete_message` | Delete (trash) an email |
| `zoho_get_attachment` | Get attachment metadata |

## Setup

### 1. Zoho OAuth Credentials

1. Go to [Zoho API Console](https://api-console.zoho.com/)
2. Create a Self Client
3. Generate a refresh token with scopes:
   ```
   ZohoMail.messages.ALL,ZohoMail.folders.ALL,ZohoMail.tags.ALL,ZohoMail.accounts.READ,ZohoMail.attachments.READ
   ```
4. Copy your Client ID, Client Secret, and Refresh Token

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

## License

MIT
