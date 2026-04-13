---
name: add-or-update-integration-tests
description: Workflow command scaffold for add-or-update-integration-tests in zoho-mail-mcp.
allowed_tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---

# /add-or-update-integration-tests

Use this workflow when working on **add-or-update-integration-tests** in `zoho-mail-mcp`.

## Goal

Adds or updates integration tests for authentication and tool endpoints, ensuring coverage and correct behavior.

## Common Files

- `tests/test_auth.py`
- `tests/test_tools.py`
- `tests/conftest.py`
- `tests/__init__.py`

## Suggested Sequence

1. Understand the current state and failure mode before editing.
2. Make the smallest coherent change that satisfies the workflow goal.
3. Run the most relevant verification for touched files.
4. Summarize what changed and what still needs review.

## Typical Commit Signals

- Edit or add test modules in tests/ (e.g., tests/test_auth.py, tests/test_tools.py).
- Update or add fixtures in tests/conftest.py as needed.
- Add or update test initialization in tests/__init__.py if necessary.

## Notes

- Treat this as a scaffold, not a hard-coded script.
- Update the command if the workflow evolves materially.