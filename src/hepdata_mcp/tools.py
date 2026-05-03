"""Agent-facing tool functions for the HEPData MCP server."""

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

from hepdata_mcp.client import HEPDataClient
from hepdata_mcp.errors import HEPDataError
from hepdata_mcp.identifiers import TableFormat
from hepdata_mcp.limits import truncate_value, truncation_metadata
from hepdata_mcp.models import RecordData

ToolPayload = dict[str, Any]


async def search_records_tool(
    query: str,
    *,
    page: int = 1,
    size: int = 10,
    client: HEPDataClient | None = None,
) -> ToolPayload:
    """Search HEPData records and return compact upstream JSON plus source metadata."""
    async with _client_context(client) as hepdata:
        try:
            result = await hepdata.search_records(query, page=page, size=size)
        except (HEPDataError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
    return result.model_dump(mode="json")


async def get_record_tool(
    identifier: str,
    *,
    version: int | None = None,
    light: bool = True,
    client: HEPDataClient | None = None,
) -> ToolPayload:
    """Fetch HEPData record metadata or full record JSON."""
    async with _client_context(client) as hepdata:
        try:
            result = await hepdata.get_record(identifier, version=version, light=light)
        except (HEPDataError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
    return result.model_dump(mode="json")


async def list_tables_tool(
    identifier: str,
    *,
    version: int | None = None,
    client: HEPDataClient | None = None,
) -> ToolPayload:
    """List tables advertised by a HEPData record without fetching full table payloads."""
    async with _client_context(client) as hepdata:
        try:
            record = await hepdata.get_record(identifier, version=version, light=True)
        except (HEPDataError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

    tables = _extract_table_summaries(record)
    return {
        "source": record.source.model_dump(mode="json"),
        "identifier": record.identifier,
        "version": record.version,
        "tables": tables,
        "table_count": len(tables),
    }


async def get_table_tool(
    identifier: str,
    table: str,
    *,
    version: int | None = None,
    format: TableFormat = "json",
    client: HEPDataClient | None = None,
) -> ToolPayload:
    """Fetch one HEPData table in JSON, YAML, or CSV format."""
    async with _client_context(client) as hepdata:
        try:
            result = await hepdata.get_table(identifier, table, version=version, format=format)
        except (HEPDataError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
    return _bounded_payload(result.model_dump(mode="json"), fields=("data",))


async def get_record_exports_tool(
    identifier: str,
    *,
    version: int | None = None,
    client: HEPDataClient | None = None,
) -> ToolPayload:
    """Return supported HEPData export URLs without downloading the files."""
    async with _client_context(client) as hepdata:
        try:
            result = hepdata.get_record_exports(identifier, version=version)
        except (HEPDataError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
    return _bounded_payload(result.model_dump(mode="json"), fields=("data",))


async def get_jsonld_tool(
    identifier: str,
    *,
    client: HEPDataClient | None = None,
) -> ToolPayload:
    """Fetch JSON-LD metadata for a HEPData record."""
    async with _client_context(client) as hepdata:
        try:
            result = await hepdata.get_jsonld(identifier)
        except (HEPDataError, ValueError) as exc:
            raise ValueError(str(exc)) from exc
    return _bounded_payload(result.model_dump(mode="json"), fields=("data",))


@asynccontextmanager
async def _client_context(client: HEPDataClient | None) -> AsyncIterator[HEPDataClient]:
    if client is not None:
        yield client
        return

    async with HEPDataClient() as created_client:
        yield created_client


def _extract_table_summaries(record: RecordData) -> list[ToolPayload]:
    raw_tables = _find_table_candidates(record.data)
    summaries: list[ToolPayload] = []
    for index, table in enumerate(raw_tables, start=1):
        summaries.append(_summarize_table_candidate(table, index))
    return summaries


def _bounded_payload(payload: ToolPayload, *, fields: Sequence[str]) -> ToolPayload:
    bounded = dict(payload)
    truncated = False
    for field in fields:
        if field not in bounded:
            continue
        result = truncate_value(bounded[field])
        bounded[field] = result.value
        truncated = truncated or result.truncated

    if truncated:
        bounded["truncation"] = truncation_metadata()
    return bounded


def _find_table_candidates(data: ToolPayload) -> Sequence[Any]:
    for key in ("data_tables", "tables"):
        value = data.get(key)
        if isinstance(value, list):
            return value

    record = data.get("record")
    if isinstance(record, dict):
        for key in ("data_tables", "tables"):
            value = record.get(key)
            if isinstance(value, list):
                return value

    return []


def _summarize_table_candidate(table: Any, index: int) -> ToolPayload:
    if isinstance(table, str):
        return {
            "name": table,
            "table_id": None,
            "description": None,
            "data_available": None,
            "available_fields": [],
        }

    if not isinstance(table, dict):
        return {
            "name": f"table-{index}",
            "table_id": None,
            "description": None,
            "data_available": None,
            "available_fields": [],
        }

    name = _first_string(table, ("name", "title", "table", "table_name")) or f"table-{index}"
    table_id = _first_scalar(table, ("id", "table_id", "record_id"))
    description = _first_string(table, ("description", "caption", "location"))
    data_available = _table_data_available(table)
    available_fields = sorted(str(key) for key in table)
    return {
        "name": name,
        "table_id": table_id,
        "description": description,
        "data_available": data_available,
        "available_fields": available_fields,
    }


def _first_string(data: ToolPayload, keys: Sequence[str]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _first_scalar(data: ToolPayload, keys: Sequence[str]) -> str | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return None


def _table_data_available(table: ToolPayload) -> bool | None:
    explicit = table.get("data_available")
    if isinstance(explicit, bool):
        return explicit

    for key in ("data", "values", "independent_variables", "dependent_variables"):
        value = table.get(key)
        if isinstance(value, list | dict):
            return bool(value)

    for key in ("data_file", "data_url", "url", "download_url"):
        value = table.get(key)
        if isinstance(value, str) and value.strip():
            return True

    return None
