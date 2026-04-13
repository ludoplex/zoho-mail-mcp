---
name: add-or-update-tool-endpoint
description: Workflow command scaffold for add-or-update-tool-endpoint in zoho-mail-mcp.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /add-or-update-tool-endpoint

Use this workflow when working on **add-or-update-tool-endpoint** in `zoho-mail-mcp`.

## Goal

Implements a new Zoho Mail tool or updates an existing one, including API logic, client integration, and tests.

## Common Files

- `server.py`
- `zoho_client.py`
- `tests/test_tools.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Edit or add implementation in server.py to expose the tool endpoint.
- Update or extend zoho_client.py to support the tool's API logic.
- Add or modify tests in tests/test_tools.py to cover the new or updated tool.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.