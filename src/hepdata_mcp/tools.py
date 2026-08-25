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
    """List tables advertised by a HEPData record without fetching table data payloads."""
    async with _client_context(client) as hepdata:
        try:
            record = await hepdata.get_record(identifier, version=version, light=False)
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


async def describe_table_tool(
    identifier: str,
    table: str,
    *,
    version: int | None = None,
    client: HEPDataClient | None = None,
) -> ToolPayload:
    """Return compact metadata and variable information for one HEPData table."""
    async with _client_context(client) as hepdata:
        try:
            record = await hepdata.get_record(identifier, version=version, light=False)
            table_metadata = _find_table_candidate_by_reference(record, table)
            if table_metadata is None:
                raise ValueError(f"Table '{table}' was not found in record {record.identifier}.")

            data_url = _table_data_url(table_metadata, "json")
            if data_url is not None:
                source, data = await hepdata.get_public_json_url(data_url)
                table_name = _first_string(table_metadata, ("name", "title", "table", "table_name"))
            else:
                result = await hepdata.get_table(
                    record.identifier,
                    table,
                    version=version,
                    format="json",
                )
                source = result.source
                data = result.data if isinstance(result.data, dict) else {}
                table_name = result.table
        except (HEPDataError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

    return _bounded_payload(
        {
            "source": source.model_dump(mode="json"),
            "identifier": record.identifier,
            "table": table,
            "version": version,
            "name": _first_string(data, ("name", "title")) or table_name or table,
            "description": _first_string(data, ("description", "caption")),
            "location": _first_string(data, ("location",)),
            "doi": _first_string(data, ("doi",)),
            "keywords": data.get("keywords") if isinstance(data.get("keywords"), dict) else {},
            "qualifiers": data.get("qualifiers")
            if isinstance(data.get("qualifiers"), dict)
            else {},
            "variables": _describe_variables(data),
            "value_count": _value_count(data),
            "resources": data.get("resources") if isinstance(data.get("resources"), list) else [],
            "related_tables": data.get("related_tables")
            if isinstance(data.get("related_tables"), list)
            else [],
            "available_fields": sorted(str(key) for key in data),
        },
        fields=("description", "keywords", "qualifiers", "resources", "related_tables"),
    )


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


async def get_record_versions_tool(
    identifier: str,
    *,
    client: HEPDataClient | None = None,
) -> ToolPayload:
    """Return version metadata and version-specific record URLs for a HEPData record."""
    async with _client_context(client) as hepdata:
        try:
            record = await hepdata.get_record(identifier, light=True)
        except (HEPDataError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

        current_version = _first_int(record.data, ("version",))
        version_count = _first_int(record.data, ("version_count",))
        record_body = record.data.get("record")
        if isinstance(record_body, dict):
            current_version = current_version or _first_int(record_body, ("version",))

        latest_version = version_count or current_version
        versions = [
            {
                "version": version_number,
                "record_url": hepdata.build_record_export_url(
                    record.identifier,
                    format="json",
                    version=version_number,
                    light=True,
                ),
                "is_current": version_number == current_version,
                "is_latest": version_number == latest_version,
            }
            for version_number in range(1, (latest_version or 0) + 1)
        ]

    return {
        "source": record.source.model_dump(mode="json"),
        "identifier": record.identifier,
        "current_version": current_version,
        "latest_version": latest_version,
        "version_count": version_count,
        "versions": versions,
    }


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


def _find_table_candidate_by_reference(
    record: RecordData,
    table_reference: str,
) -> ToolPayload | None:
    raw_tables = _find_table_candidates(record.data)
    clean_reference = table_reference.strip().casefold()
    for index, table in enumerate(raw_tables, start=1):
        if not isinstance(table, dict):
            if str(index) == clean_reference or (
                isinstance(table, str) and table.strip().casefold() == clean_reference
            ):
                return {"name": table} if isinstance(table, str) else {}
            continue

        references = {
            str(index),
            *(
                value.strip().casefold()
                for value in (
                    _first_scalar(table, ("id", "table_id", "record_id")),
                    _first_string(
                        table,
                        ("name", "title", "table", "table_name", "processed_name"),
                    ),
                    _first_string(table, ("doi",)),
                )
                if value is not None
            ),
        }
        if clean_reference in references:
            return table
    return None


def _table_data_url(table: ToolPayload, format_name: str) -> str | None:
    data = table.get("data")
    if isinstance(data, dict):
        value = data.get(format_name)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


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


def _describe_variables(data: ToolPayload) -> ToolPayload:
    independent_variables = data.get("independent_variables")
    dependent_variables = data.get("dependent_variables")
    if isinstance(independent_variables, list) or isinstance(dependent_variables, list):
        return {
            "independent": _summarize_variable_list(independent_variables),
            "dependent": _summarize_variable_list(dependent_variables),
        }

    headers = data.get("headers")
    values = data.get("values")
    if not isinstance(headers, list):
        return {"independent": [], "dependent": []}

    first_value = values[0] if isinstance(values, list) and values else {}
    x_count = len(first_value.get("x", [])) if isinstance(first_value.get("x"), list) else 0
    y_count = len(first_value.get("y", [])) if isinstance(first_value.get("y"), list) else 0

    independent_headers = headers[:x_count]
    dependent_headers = headers[x_count : x_count + y_count if y_count else None]
    return {
        "independent": _summarize_header_list(independent_headers),
        "dependent": _summarize_header_list(dependent_headers),
    }


def _summarize_variable_list(variables: Any) -> list[ToolPayload]:
    if not isinstance(variables, list):
        return []

    summaries: list[ToolPayload] = []
    for variable in variables:
        if not isinstance(variable, dict):
            continue
        header = variable.get("header")
        header_data = header if isinstance(header, dict) else variable
        summaries.append(
            {
                "name": _first_string(header_data, ("name", "title")),
                "units": _first_string(header_data, ("units", "unit")),
                "qualifier_count": _list_length(variable.get("qualifiers")),
                "value_count": _list_length(variable.get("values")),
            }
        )
    return summaries


def _summarize_header_list(headers: Sequence[Any]) -> list[ToolPayload]:
    summaries: list[ToolPayload] = []
    for header in headers:
        if isinstance(header, str):
            summaries.append({"name": header, "units": None})
            continue
        if isinstance(header, dict):
            summaries.append(
                {
                    "name": _first_string(header, ("name", "title")),
                    "units": _first_string(header, ("units", "unit")),
                }
            )
    return summaries


def _value_count(data: ToolPayload) -> int | None:
    values = data.get("values")
    if isinstance(values, list):
        return len(values)

    dependent_variables = data.get("dependent_variables")
    if isinstance(dependent_variables, list) and dependent_variables:
        first_dependent = dependent_variables[0]
        if isinstance(first_dependent, dict):
            return _list_length(first_dependent.get("values"))

    return None


def _list_length(value: Any) -> int | None:
    return len(value) if isinstance(value, list) else None


def _first_int(data: ToolPayload, keys: Sequence[str]) -> int | None:
    for key in keys:
        value = data.get(key)
        if isinstance(value, int):
            return value
        if isinstance(value, str) and value.isdigit():
            return int(value)
    return None
