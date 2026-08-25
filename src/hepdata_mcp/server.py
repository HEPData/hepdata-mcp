"""MCP server entry point for HEPData."""

import argparse
import functools
import os
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Literal

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from hepdata_mcp.__about__ import package_version
from hepdata_mcp.identifiers import TableFormat
from hepdata_mcp.tools import (
    describe_table_tool,
    get_jsonld_tool,
    get_record_exports_tool,
    get_record_tool,
    get_record_versions_tool,
    get_table_tool,
    list_tables_tool,
    search_records_tool,
)

Transport = Literal["stdio", "sse", "streamable-http"]
DEFAULT_HTTP_HOST = "127.0.0.1"
DEFAULT_HTTP_PORT = 8000
DEFAULT_HTTP_PATH = "/mcp"
MAX_HTTP_PATH_LENGTH = 128
READ_ONLY_TOOL_ANNOTATIONS = ToolAnnotations(
    title="Read-only HEPData query",
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=True,
)


_AnyTool = Callable[..., Awaitable[object]]


def _agent_facing(fn: _AnyTool) -> _AnyTool:
    """Surface domain validation failures as tool errors agents can act on.

    The SDK only forwards ``ToolError`` messages to clients; any other
    exception is replaced with a generic crash notice, hiding the useful
    HEPData error text from the agent.
    """

    @functools.wraps(fn)
    async def wrapper(*args: object, **kwargs: object) -> object:
        try:
            return await fn(*args, **kwargs)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc

    return wrapper


class ServerInfo(BaseModel):
    """Structured health and capability metadata for the MCP server."""

    name: str = Field(description="Server package name.")
    version: str = Field(description="Installed package version.")
    status: Literal["ok"] = Field(description="Server health status.")
    description: str = Field(description="Short human-readable server description.")


@dataclass(frozen=True)
class ServerSettings:
    """Runtime settings for local and HTTP MCP transports."""

    transport: Transport = "stdio"
    host: str = DEFAULT_HTTP_HOST
    port: int = DEFAULT_HTTP_PORT
    path: str = DEFAULT_HTTP_PATH
    stateless_http: bool = False


def get_server_info() -> ServerInfo:
    """Return basic server metadata without touching external services."""
    return ServerInfo(
        name="hepdata-mcp",
        version=package_version(),
        status="ok",
        description=(
            "Read-only MCP server for bounded HEPData record discovery and table retrieval."
        ),
    )


def create_server(settings: ServerSettings | None = None) -> MCPServer:
    """Create and configure the MCP server application."""
    runtime_settings = settings or ServerSettings()
    validate_server_settings(runtime_settings)
    mcp = MCPServer(
        "hepdata-mcp",
        title="HEPData MCP Server",
        description=(
            "Read-only MCP server for bounded HEPData record discovery and table retrieval."
        ),
        version=package_version(),
    )

    @mcp.tool(
        title="Server Info",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    def server_info() -> ServerInfo:
        """Return server health, version, and capability metadata."""
        return get_server_info()

    @mcp.tool(
        title="Search Records",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    @_agent_facing
    async def search_records(query: str, page: int = 1, size: int = 10) -> dict[str, object]:
        """Search HEPData records using HEPData's native search syntax."""
        return await search_records_tool(query, page=page, size=size)

    @mcp.tool(
        title="Get Record",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    @_agent_facing
    async def get_record(
        identifier: str,
        version: int | None = None,
        light: bool = True,
    ) -> dict[str, object]:
        """Fetch HEPData record metadata or full record JSON."""
        return await get_record_tool(identifier, version=version, light=light)

    @mcp.tool(
        title="List Tables",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    @_agent_facing
    async def list_tables(identifier: str, version: int | None = None) -> dict[str, object]:
        """List tables advertised by a HEPData record."""
        return await list_tables_tool(identifier, version=version)

    @mcp.tool(
        title="Describe Table",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    @_agent_facing
    async def describe_table(
        identifier: str,
        table: str,
        version: int | None = None,
    ) -> dict[str, object]:
        """Describe one HEPData table's metadata, variables, qualifiers, and size."""
        return await describe_table_tool(identifier, table, version=version)

    @mcp.tool(
        title="Get Table",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    @_agent_facing
    async def get_table(
        identifier: str,
        table: str,
        version: int | None = None,
        format: TableFormat = "json",
    ) -> dict[str, object]:
        """Fetch one HEPData table in JSON, YAML, or CSV format."""
        return await get_table_tool(identifier, table, version=version, format=format)

    @mcp.tool(
        title="Get Record Exports",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    @_agent_facing
    async def get_record_exports(identifier: str, version: int | None = None) -> dict[str, object]:
        """Return supported HEPData export URLs without downloading files."""
        return await get_record_exports_tool(identifier, version=version)

    @mcp.tool(
        title="Get Record Versions",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    @_agent_facing
    async def get_record_versions(identifier: str) -> dict[str, object]:
        """Return available HEPData record versions and version-specific record URLs."""
        return await get_record_versions_tool(identifier)

    @mcp.tool(
        title="Get JSON-LD",
        annotations=READ_ONLY_TOOL_ANNOTATIONS,
    )
    @_agent_facing
    async def get_jsonld(identifier: str) -> dict[str, object]:
        """Fetch JSON-LD metadata for a HEPData record."""
        return await get_jsonld_tool(identifier)

    @mcp.resource(
        "hepdata://record/{identifier}",
        description="Light HEPData record metadata for a record identifier.",
        mime_type="application/json",
    )
    async def record_resource(identifier: str) -> dict[str, object]:
        return await get_record_tool(identifier, light=True)

    @mcp.resource(
        "hepdata://record/{identifier}/tables",
        description="Table summaries for a HEPData record identifier.",
        mime_type="application/json",
    )
    async def record_tables_resource(identifier: str) -> dict[str, object]:
        return await list_tables_tool(identifier)

    return mcp


def main(argv: Sequence[str] | None = None) -> None:
    """Run the MCP server over the selected transport."""
    settings = settings_from_args(argv)
    validate_transport_security(settings)
    server = create_server()
    if settings.transport == "stdio":
        server.run(transport="stdio")
    elif settings.transport == "sse":
        server.run(
            transport="sse",
            host=settings.host,
            port=settings.port,
        )
    else:
        server.run(
            transport="streamable-http",
            host=settings.host,
            port=settings.port,
            streamable_http_path=settings.path,
            stateless_http=settings.stateless_http,
        )


def settings_from_args(argv: Sequence[str] | None = None) -> ServerSettings:
    """Parse command-line and environment settings."""
    parser = argparse.ArgumentParser(prog="hepdata-mcp")
    parser.add_argument(
        "--transport",
        choices=("stdio", "sse", "streamable-http"),
        default=os.environ.get("HEPDATA_MCP_TRANSPORT", "stdio"),
        help="MCP transport to run. Defaults to stdio.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("HEPDATA_MCP_HOST", DEFAULT_HTTP_HOST),
        help="Host for HTTP transports. Defaults to 127.0.0.1.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.environ.get("HEPDATA_MCP_PORT", str(DEFAULT_HTTP_PORT))),
        help="Port for HTTP transports. Defaults to 8000.",
    )
    parser.add_argument(
        "--path",
        default=os.environ.get("HEPDATA_MCP_PATH", DEFAULT_HTTP_PATH),
        help="Streamable HTTP mount path. Defaults to /mcp.",
    )
    parser.add_argument(
        "--stateless-http",
        action="store_true",
        default=_env_flag("HEPDATA_MCP_STATELESS_HTTP"),
        help="Use stateless HTTP sessions for compatible deployments.",
    )
    namespace = parser.parse_args(argv)
    return ServerSettings(
        transport=namespace.transport,
        host=namespace.host,
        port=namespace.port,
        path=namespace.path,
        stateless_http=namespace.stateless_http,
    )


def validate_transport_security(settings: ServerSettings) -> None:
    """Refuse unsafe HTTP binds unless deployment hardening is explicit."""
    validate_server_settings(settings)

    if settings.transport == "stdio" or _is_loopback_host(settings.host):
        return

    if not _env_flag("HEPDATA_MCP_ALLOW_REMOTE_HTTP"):
        raise RuntimeError(
            "Refusing to bind an HTTP MCP transport to a non-loopback host. "
            "Use 127.0.0.1 for local use, or set HEPDATA_MCP_ALLOW_REMOTE_HTTP=1 "
            "for a hardened deployment behind TLS and authentication."
        )

    if not _env_flag("HEPDATA_MCP_TRUST_PROXY_AUTH"):
        raise RuntimeError(
            "Remote HTTP deployment requires an authenticated reverse proxy or ingress. "
            "Set HEPDATA_MCP_TRUST_PROXY_AUTH=1 only when TLS, authentication, and "
            "rate limiting are enforced before requests reach this process."
        )


def validate_server_settings(settings: ServerSettings) -> None:
    """Validate runtime settings before they reach the transport layer."""
    if not settings.host.strip():
        raise ValueError("HTTP host cannot be empty.")
    if not 1 <= settings.port <= 65535:
        raise ValueError("HTTP port must be between 1 and 65535.")
    _validate_http_path(settings.path)


def _validate_http_path(path: str) -> None:
    if not path.startswith("/"):
        raise ValueError("HTTP path must start with '/'.")
    if len(path) > MAX_HTTP_PATH_LENGTH:
        raise ValueError(f"HTTP path must be at most {MAX_HTTP_PATH_LENGTH} characters.")
    if any(character.isspace() or _is_control_character(character) for character in path):
        raise ValueError("HTTP path must not contain whitespace or control characters.")
    if any(character in path for character in ("?", "#")):
        raise ValueError("HTTP path must not contain query strings or fragments.")


def _is_loopback_host(host: str) -> bool:
    normalized = host.strip().lower()
    if normalized in {"localhost", "localhost.localdomain"}:
        return True
    try:
        return ip_address(normalized).is_loopback
    except ValueError:
        return False


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _is_control_character(character: str) -> bool:
    codepoint = ord(character)
    return codepoint < 32 or codepoint == 127


mcp = create_server()


if __name__ == "__main__":
    main()
