```markdown
# zoho-mail-mcp Development Patterns

> Auto-generated skill from repository analysis

## Overview

This skill teaches the core development patterns and workflows for contributing to the `zoho-mail-mcp` Python codebase. The repository manages Zoho Mail MCP tools and integrations, with a focus on API endpoint development and robust testing. You'll learn the project's coding conventions, how to add or update tool endpoints, and how to maintain and expand integration tests.

## Coding Conventions

- **File Naming:**  
  Use `snake_case` for all Python files.  
  _Example:_  
  ```
  zoho_client.py
  test_tools.py
  ```

- **Import Style:**  
  Use relative imports within the package.  
  _Example:_  
  ```python
  from .zoho_client import ZohoClient
  ```

- **Export Style:**  
  Use named exports (explicit class/function definitions).  
  _Example:_  
  ```python
  class ZohoClient:
      ...
  ```

- **Commit Messages:**  
  Follow [Conventional Commits](https://www.conventionalcommits.org/) with these prefixes:  
    - `feat`: New features  
    - `fix`: Bug fixes  
    - `docs`: Documentation changes  
    - `test`: Test-related changes  
  _Example:_  
  ```
  feat: add support for mail folder listing endpoint
  ```

## Workflows

### Add or Update Tool Endpoint
**Trigger:** When you want to add a new Zoho Mail tool (API endpoint) or enhance an existing one.  
**Command:** `/add-tool-endpoint`

1. **Edit or add implementation in `server.py`**  
   Expose the new or updated tool endpoint.
   ```python
   @app.route('/api/new_tool', methods=['POST'])
   def new_tool():
       # Endpoint logic here
   ```
2. **Update or extend `zoho_client.py`**  
   Implement the API logic for the tool.
   ```python
   class ZohoClient:
       def new_tool_method(self, ...):
           # API interaction logic
   ```
3. **Add or modify tests in `tests/test_tools.py`**  
   Ensure the endpoint is covered by tests.
   ```python
   def test_new_tool(client):
       response = client.post('/api/new_tool', json={...})
       assert response.status_code == 200
   ```

### Add or Update Integration Tests
**Trigger:** When you want to verify or expand test coverage for authentication or tool endpoints.  
**Command:** `/add-integration-tests`

1. **Edit or add test modules in `tests/`**  
   For example, update `tests/test_auth.py` or `tests/test_tools.py`.
   ```python
   def test_auth_success(client):
       response = client.post('/api/auth', json={...})
       assert response.status_code == 200
   ```
2. **Update or add fixtures in `tests/conftest.py`**  
   Define shared fixtures for test setup.
   ```python
   import pytest

   @pytest.fixture
   def client():
       # Setup test client
   ```
3. **Add or update test initialization in `tests/__init__.py`** if needed.

## Testing Patterns

- **Test File Naming:**  
  Use `snake_case` and prefix with `test_`.  
  _Example:_  
  ```
  tests/test_tools.py
  tests/test_auth.py
  ```

- **Framework:**  
  While not explicitly detected, the use of `pytest`-style fixtures and assertions is recommended.

- **Test Structure:**  
  - Place all tests in the `tests/` directory.
  - Use fixtures in `conftest.py` for setup.
  - Group related tests by module or feature.

- **Example Test:**
  ```python
  def test_tool_endpoint(client):
      response = client.post('/api/tool', json={'param': 'value'})
      assert response.status_code == 200
      assert response.json['result'] == 'expected'
  ```

## Commands

| Command                | Purpose                                                         |
|------------------------|-----------------------------------------------------------------|
| /add-tool-endpoint     | Add or update a Zoho Mail tool (API endpoint)                   |
| /add-integration-tests | Add or update integration tests for authentication or endpoints  |
```
