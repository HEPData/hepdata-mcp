# HEPData MCP

This is an MCP server for discovering HEPData records, listing tables, fetching table data, and exposing HEPData export links. This is an early MVP implementation, focused on read-only access to public HEPData content.

Local stdio is the default and recommended mode. HTTP support exists for local testing and hardened central deployments, but remote HTTP is also supported for multiple clients support.

## Install From This Checkout

This package is not published to PyPI yet. Install it into a local virtual environment with `uv`:

```bash
mkdir -p ~/.local/uv
git clone https://github.com/HEPData/hepdata-mcp ~/.local/uv/hepdata-mcp
cd ~/.local/uv/hepdata-mcp
uv venv .venv
uv pip install -e .
```

The examples below install into `~/.local/uv/hepdata-mcp`. You can install the checkout somewhere else; just replace that path with your chosen directory.

MCP client config files should use the full absolute path to the executable. Do not use `~` in JSON or TOML command fields, because many clients launch commands directly without shell expansion.

For development checks:

```bash
uv sync --all-groups
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Run the server locally over stdio:

```bash
.venv/bin/hepdata-mcp
```

## Tools

- `search_records`
- `get_record`
- `list_tables`
- `get_table`
- `get_record_exports`
- `get_jsonld`
- `server_info`

Resources:

- `hepdata://record/{identifier}`
- `hepdata://record/{identifier}/tables`

## Local MCP Client Setup

Use the absolute path to the installed executable:

```text
/home/<your-user>/.local/uv/hepdata-mcp/.venv/bin/hepdata-mcp
```

On Linux/macOS, print the exact path with:

```bash
realpath ~/.local/uv/hepdata-mcp/.venv/bin/hepdata-mcp
```

### GitHub Copilot In VS Code

Create or edit `.vscode/mcp.json`:

```json
{
  "servers": {
    "hepdata": {
      "command": "/home/<your-user>/.local/uv/hepdata-mcp/.venv/bin/hepdata-mcp",
      "args": []
    }
  }
}
```

Then run `MCP: List Servers` from the VS Code command palette and start `hepdata`.

For GitHub Copilot CLI:

```bash
copilot mcp add hepdata --type stdio -- ~/.local/uv/hepdata-mcp/.venv/bin/hepdata-mcp
```

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.hepdata]
command = "/home/<your-user>/.local/uv/hepdata-mcp/.venv/bin/hepdata-mcp"
supports_parallel_tool_calls = true
```

Or, if using a local HTTP server:

```bash
codex mcp add hepdata --url http://127.0.0.1:8000/mcp
```

### Claude Code

Project `.mcp.json` example:

```json
{
  "mcpServers": {
    "hepdata": {
      "type": "stdio",
      "command": "/home/<your-user>/.local/uv/hepdata-mcp/.venv/bin/hepdata-mcp",
      "args": []
    }
  }
}
```

CLI alternative:

```bash
claude m cp add-json hepdata '{"type":"stdio","command":"/home/<your-user>/.local/uv/hepdata-mcp/.venv/bin/hepdata-mcp","args":[]}'
```

### Qwen Code

Add to `~/.qwen/settings.json` or `.qwen/settings.json`:

```json
{
  "mcpServers": {
    "hepdata": {
      "command": "/home/<your-user>/.local/uv/hepdata-mcp/.venv/bin/hepdata-mcp",
      "args": [],
      "timeout": 30000,
      "trust": false
    }
  }
}
```

### Other MCP Clients

Most stdio MCP clients support a similar shape:

```json
{
  "mcpServers": {
    "hepdata": {
      "command": "/home/<your-user>/.local/uv/hepdata-mcp/.venv/bin/hepdata-mcp",
      "args": []
    }
  }
}
```

## HTTP Mode

First create a new .venv like 

```bash
uv venv .venv-http
uv pip install -e .
```

Start local streamable HTTP:

```bash
.venv-http/bin/hepdata-mcp --transport streamable-http --host 127.0.0.1 --port 8000
```

Local URL:

```text
http://127.0.0.1:8000/mcp
```

Example VS Code / GitHub Copilot HTTP config:

```json
{
  "servers": {
    "hepdata": {
      "type": "http",
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

Example Qwen Code HTTP config:

```json
{
  "mcpServers": {
    "hepdata": {
      "httpUrl": "http://127.0.0.1:8000/mcp",
      "timeout": 30000
    }
  }
}
```

## Central Deployment

Remote HTTP binds are intentionally blocked unless both deployment opt-ins are set:

```bash
HEPDATA_MCP_ALLOW_REMOTE_HTTP=1 \
HEPDATA_MCP_TRUST_PROXY_AUTH=1 \
.venv/bin/hepdata-mcp --transport streamable-http --host 0.0.0.0 --port 8000
```

Only use this behind hardened ingress:

- TLS at the edge.
- Authentication and authorization before requests reach this process.
- Per-user or per-token rate limits.
- No request-body or table-payload logging.


## Notes

- HEPData upstream access is public and read-only.
- Large tool payloads are truncated before being returned to agents.
- Whole-record download exports are returned as HEPData URLs, not downloaded by default.
- Live integration tests are opt-in:

```bash
HEPDATA_MCP_LIVE_TESTS=1 uv run pytest tests/test_live_client.py
```

## License

This project follows the main HEPData project license: GNU General Public License version 2 or later (`GPL-2.0-or-later`). See [LICENSE](LICENSE).
