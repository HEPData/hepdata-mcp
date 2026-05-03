import pytest

from hepdata_mcp import package_version
from hepdata_mcp.server import (
    ServerSettings,
    create_server,
    get_server_info,
    settings_from_args,
    validate_server_settings,
    validate_transport_security,
)


def test_package_version_has_fallback() -> None:
    assert package_version()


def test_server_info_is_mcp_tools_health_payload() -> None:
    info = get_server_info()

    assert info.name == "hepdata-mcp"
    assert info.status == "ok"


async def test_create_server_registers_mvp_tools() -> None:
    server = create_server()

    assert server.name == "hepdata-mcp"
    tools = await server.list_tools()
    tool_names = {tool.name for tool in tools}

    assert {
        "server_info",
        "search_records",
        "get_record",
        "list_tables",
        "describe_table",
        "get_table",
        "get_record_exports",
        "get_record_versions",
        "get_jsonld",
    } <= tool_names


async def test_create_server_registers_mvp_resource_templates() -> None:
    server = create_server()

    resource_templates = await server.list_resource_templates()
    uris = {str(resource.uriTemplate) for resource in resource_templates}

    assert {
        "hepdata://record/{identifier}",
        "hepdata://record/{identifier}/tables",
    } <= uris


async def test_server_info_can_be_called_through_fastmcp() -> None:
    server = create_server()

    result = await server.call_tool("server_info", {})

    assert isinstance(result, tuple)
    _, structured_content = result
    assert structured_content["name"] == "hepdata-mcp"
    assert structured_content["status"] == "ok"


def test_settings_default_to_stdio() -> None:
    settings = settings_from_args([])

    assert settings == ServerSettings()


def test_settings_parse_streamable_http() -> None:
    settings = settings_from_args(
        ["--transport", "streamable-http", "--host", "127.0.0.1", "--port", "9000"]
    )

    assert settings.transport == "streamable-http"
    assert settings.host == "127.0.0.1"
    assert settings.port == 9000


def test_transport_security_allows_stdio_and_loopback_http() -> None:
    validate_transport_security(ServerSettings())
    validate_transport_security(ServerSettings(transport="streamable-http", host="127.0.0.1"))
    validate_transport_security(ServerSettings(transport="streamable-http", host="localhost"))


def test_transport_security_rejects_remote_http_without_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("HEPDATA_MCP_ALLOW_REMOTE_HTTP", raising=False)
    monkeypatch.delenv("HEPDATA_MCP_TRUST_PROXY_AUTH", raising=False)

    with pytest.raises(RuntimeError, match="Refusing to bind"):
        validate_transport_security(ServerSettings(transport="streamable-http", host="0.0.0.0"))


def test_transport_security_requires_authenticated_proxy_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEPDATA_MCP_ALLOW_REMOTE_HTTP", "1")
    monkeypatch.delenv("HEPDATA_MCP_TRUST_PROXY_AUTH", raising=False)

    with pytest.raises(RuntimeError, match="authenticated reverse proxy"):
        validate_transport_security(ServerSettings(transport="streamable-http", host="0.0.0.0"))


def test_transport_security_allows_explicit_hardened_remote_deployment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HEPDATA_MCP_ALLOW_REMOTE_HTTP", "1")
    monkeypatch.setenv("HEPDATA_MCP_TRUST_PROXY_AUTH", "1")

    validate_transport_security(ServerSettings(transport="streamable-http", host="0.0.0.0"))


def test_server_settings_reject_empty_host() -> None:
    with pytest.raises(ValueError, match="host cannot be empty"):
        validate_server_settings(ServerSettings(host=" "))


def test_server_settings_reject_invalid_port() -> None:
    with pytest.raises(ValueError, match="port must be between"):
        validate_server_settings(ServerSettings(port=0))


def test_server_settings_reject_unsafe_http_path() -> None:
    with pytest.raises(ValueError, match="must start"):
        validate_server_settings(ServerSettings(path="mcp"))

    with pytest.raises(ValueError, match="whitespace"):
        validate_server_settings(ServerSettings(path="/bad path"))

    with pytest.raises(ValueError, match="query strings"):
        validate_server_settings(ServerSettings(path="/mcp?debug=true"))
