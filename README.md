# HEPData MCP

This is an MCP server for discovering HEPData records, listing tables, fetching table data, and exposing HEPData export links. This is an early MVP implementation, focused on read-only access to public HEPData content.

Local stdio is the default and recommended mode. HTTP support exists for local testing and hardened central deployments, but remote HTTP is also supported for multiple clients support.

## Run From PyPI

HEPData MCP is published on PyPI as [`hepdata-mcp`](https://pypi.org/project/hepdata-mcp/).
The easiest way to run it is with `uvx`:

```bash
uvx hepdata-mcp
```

If you want to avoid package resolution during MCP client startup, install the tool once:

```bash
uv tool install hepdata-mcp
hepdata-mcp
```

Upgrade that installed tool with `uv tool upgrade hepdata-mcp`.
For MCP client configs in this mode, use `hepdata-mcp` as the command with no arguments.

## Install From Source

For development, install this checkout in editable mode:

```bash
git clone https://github.com/HEPData/hepdata-mcp ~/.local/uv/hepdata-mcp-src
cd ~/.local/uv/hepdata-mcp-src
uv sync --all-groups
```

For development checks:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

## Docker

The Docker image is published on Docker Hub as [`hepdata/hepdata-mcp`](https://hub.docker.com/r/hepdata/hepdata-mcp).
Pull the latest release:

```bash
docker pull hepdata/hepdata-mcp:latest
```

For reproducible deployments, pin a release tag such as `hepdata/hepdata-mcp:0.1.0`.

Run over stdio for clients that can launch Docker commands:

```bash
docker run --rm -i hepdata/hepdata-mcp:latest
```

Example stdio client command:

```json
{
  "mcpServers": {
    "hepdata": {
      "command": "docker",
      "args": ["run", "--rm", "-i", "hepdata/hepdata-mcp:latest"]
    }
  }
}
```

Run local streamable HTTP:

```bash
docker run --rm \
  -p 127.0.0.1:8000:8000 \
  -e HEPDATA_MCP_ALLOW_REMOTE_HTTP=1 \
  -e HEPDATA_MCP_TRUST_PROXY_AUTH=1 \
  hepdata/hepdata-mcp:latest \
  --transport streamable-http --host 0.0.0.0 --port 8000
```

The container runs as a non-root user. For remote HTTP deployment, keep the same reverse-proxy, TLS, authentication, and rate-limit requirements described below.

Build the image from this checkout for local development:

```bash
docker build -t hepdata-mcp:local .
```

## Tools

- `search_records`
- `get_record`
- `list_tables`
- `describe_table`
- `get_table`
- `get_record_exports`
- `get_record_versions`
- `get_jsonld`
- `server_info`

Resources:

- `hepdata://record/{identifier}`
- `hepdata://record/{identifier}/tables`

## Local MCP Client Setup

Most MCP clients launch commands directly, without a shell. Use `uvx` as the command and pass the package name as an argument.

Warm the `uvx` cache once before configuring a client, especially on machines with slow or restricted network access:

```bash
uvx hepdata-mcp --help
```

Useful variants:

```bash
uvx hepdata-mcp==0.1.0
uvx --refresh hepdata-mcp
```

If a GUI-launched client cannot find `uvx`, check where `uvx` is installed with `command -v uvx` and use that path as the command.
On macOS this is commonly needed for clients such as Claude Code; Homebrew installs often use `/opt/homebrew/bin/uvx`, while standalone `uv` installs may use `/Users/<you>/.local/bin/uvx`.
Use the expanded absolute path because MCP clients usually do not expand `~` or `$HOME`.

### GitHub Copilot In VS Code

Create or edit `.vscode/mcp.json`:

```json
{
  "servers": {
    "hepdata": {
      "command": "uvx",
      "args": ["hepdata-mcp"]
    }
  }
}
```

Then run `MCP: List Servers` from the VS Code command palette and start `hepdata`.

For GitHub Copilot CLI:

```bash
copilot mcp add hepdata --type stdio -- uvx hepdata-mcp
```

### Codex

Add to `~/.codex/config.toml`:

```toml
[mcp_servers.hepdata]
command = "uvx"
args = ["hepdata-mcp"]
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
      "command": "uvx",
      "args": ["hepdata-mcp"]
    }
  }
}
```

On macOS, if Claude Code cannot find `uvx`, expand the command:

```json
{
  "mcpServers": {
    "hepdata": {
      "type": "stdio",
      "command": "/opt/homebrew/bin/uvx",
      "args": ["hepdata-mcp"]
    }
  }
}
```

CLI alternative:

```bash
claude mcp add-json hepdata '{"type":"stdio","command":"uvx","args":["hepdata-mcp"]}'
```

### Qwen Code

Add to `~/.qwen/settings.json` or `.qwen/settings.json`:

```json
{
  "mcpServers": {
    "hepdata": {
      "command": "uvx",
      "args": ["hepdata-mcp"],
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
      "command": "uvx",
      "args": ["hepdata-mcp"]
    }
  }
}
```

## HTTP Mode

Start local streamable HTTP:

```bash
uvx hepdata-mcp --transport streamable-http --host 127.0.0.1 --port 8000
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
uvx hepdata-mcp --transport streamable-http --host 0.0.0.0 --port 8000
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
