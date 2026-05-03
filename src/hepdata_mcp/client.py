"""Async direct HTTP client for public HEPData endpoints."""

import logging
import uuid
from collections.abc import Mapping
from typing import Self, cast

import httpx
from pydantic import JsonValue

from hepdata_mcp.errors import (
    HEPDataHTTPError,
    HEPDataResponseTooLargeError,
    HEPDataTransportError,
)
from hepdata_mcp.identifiers import (
    SUPPORTED_RECORD_EXPORT_FORMATS,
    RecordExportFormat,
    TableFormat,
    normalize_record_identifier,
    validate_record_export_format,
    validate_table_format,
)
from hepdata_mcp.models import (
    ExportLink,
    ExportLinks,
    JSONLDData,
    RecordData,
    SearchResult,
    SourceInfo,
    TableData,
)

DEFAULT_BASE_URL = "https://www.hepdata.net"
DEFAULT_TIMEOUT_SECONDS = 20.0
DEFAULT_MAX_RESPONSE_BYTES = 5_000_000
DEFAULT_USER_AGENT = "hepdata-mcp/0.1.0 (+https://www.hepdata.net/)"
BINARY_EXPORT_FORMATS = SUPPORTED_RECORD_EXPORT_FORMATS - {"json"}
MAX_SEARCH_QUERY_LENGTH = 500
MAX_TABLE_NAME_LENGTH = 200
MAX_RIVET_ANALYSIS_LENGTH = 100
MAX_SAFE_REDIRECTS = 3
LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


class HEPDataClient:
    """Small async client for HEPData's public JSON and export endpoints."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        user_agent: str = DEFAULT_USER_AGENT,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if timeout <= 0:
            raise ValueError("HEPData request timeout must be greater than zero.")
        if max_response_bytes < 1:
            raise ValueError("HEPData maximum response size must be at least one byte.")
        self._base_url = _validate_base_url(base_url)
        self._max_response_bytes = max_response_bytes
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent},
            follow_redirects=False,
        )

    async def __aenter__(self) -> Self:
        return self

    async def __aexit__(self, *_exc_info: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Close the underlying HTTP client when this instance owns it."""
        if self._owns_http_client:
            await self._http_client.aclose()

    async def search_records(self, query: str, *, page: int = 1, size: int = 10) -> SearchResult:
        """Search HEPData records using HEPData's native search query syntax."""
        clean_query = _clean_input_text(
            query,
            field_name="Search query",
            max_length=MAX_SEARCH_QUERY_LENGTH,
        )
        _validate_page_size(page=page, size=size)

        url = self._build_url(
            "/search/",
            {"q": clean_query, "page": page, "size": size, "format": "json"},
        )
        data = await self._get_json_object(url)
        return SearchResult(
            source=SourceInfo(url=str(url)),
            query=clean_query,
            page=page,
            size=size,
            data=data,
        )

    async def get_record(
        self,
        identifier: str,
        *,
        version: int | None = None,
        light: bool = True,
    ) -> RecordData:
        """Fetch a HEPData record as JSON."""
        record_identifier = normalize_record_identifier(identifier)
        params: dict[str, str | int | bool] = {"format": "json"}
        if version is not None:
            params["version"] = _validate_version(version)
        if light:
            params["light"] = "true"

        url = self._record_url(record_identifier.path_segment, params)
        data = await self._get_json_object(url)
        return RecordData(
            source=SourceInfo(url=str(url)),
            identifier=record_identifier.value,
            version=version,
            light=light,
            data=data,
        )

    async def get_table(
        self,
        identifier: str,
        table: str,
        *,
        version: int | None = None,
        format: TableFormat = "json",
    ) -> TableData:
        """Fetch one HEPData table in JSON, YAML, or CSV export form."""
        clean_table = _clean_input_text(
            table,
            field_name="Table name",
            max_length=MAX_TABLE_NAME_LENGTH,
        )

        table_format = validate_table_format(format)
        record_identifier = normalize_record_identifier(identifier)
        params: dict[str, str | int] = {"format": table_format, "table": clean_table}
        if version is not None:
            params["version"] = _validate_version(version)

        url = self._record_url(record_identifier.path_segment, params)
        if table_format == "json":
            response = await self._get(url)
            try:
                data: JsonValue = cast(JsonValue, response.json())
            except ValueError as exc:
                raise HEPDataHTTPError(
                    response.status_code,
                    str(url),
                    "Response was not valid JSON.",
                ) from exc
        else:
            response = await self._get(url)
            data = response.text

        return TableData(
            source=SourceInfo(url=str(url)),
            identifier=record_identifier.value,
            table=clean_table,
            version=version,
            format=table_format,
            content_type=response.headers.get("Content-Type"),
            data=data,
        )

    async def get_jsonld(self, identifier: str) -> JSONLDData:
        """Fetch JSON-LD metadata for a HEPData record using content negotiation."""
        record_identifier = normalize_record_identifier(identifier)
        url = self._record_url(record_identifier.path_segment)
        data = await self._get_json_value(url, headers={"Accept": "application/ld+json"})
        return JSONLDData(
            source=SourceInfo(url=str(url)),
            identifier=record_identifier.value,
            data=data,
        )

    async def get_public_json_url(self, url: str) -> tuple[SourceInfo, dict[str, JsonValue]]:
        """Fetch a same-origin public HEPData JSON URL discovered from HEPData metadata."""
        public_url = self._validate_public_url(url)
        return SourceInfo(url=str(public_url)), await self._get_json_object(public_url)

    def get_record_exports(self, identifier: str, *, version: int | None = None) -> ExportLinks:
        """Build supported HEPData record export URLs without downloading them."""
        record_identifier = normalize_record_identifier(identifier)
        validated_version = _validate_version(version) if version is not None else None
        exports = [
            ExportLink(
                format=format_name,
                url=self.build_record_export_url(
                    record_identifier.value,
                    format=validate_record_export_format(format_name),
                    version=validated_version,
                ),
                binary=format_name in BINARY_EXPORT_FORMATS,
            )
            for format_name in sorted(SUPPORTED_RECORD_EXPORT_FORMATS)
        ]
        return ExportLinks(identifier=record_identifier.value, version=version, exports=exports)

    def build_record_export_url(
        self,
        identifier: str,
        *,
        format: RecordExportFormat,
        version: int | None = None,
        table: str | None = None,
        light: bool = False,
        qualifiers: bool = False,
        rivet: str | None = None,
    ) -> str:
        """Build a HEPData record export URL for supported public formats."""
        export_format = validate_record_export_format(format)
        record_identifier = normalize_record_identifier(identifier)
        params: dict[str, str | int] = {"format": export_format}
        if version is not None:
            params["version"] = _validate_version(version)
        if table is not None:
            clean_table = _clean_input_text(
                table,
                field_name="Table name",
                max_length=MAX_TABLE_NAME_LENGTH,
            )
            params["table"] = clean_table
        if light:
            params["light"] = "true"
        if qualifiers:
            params["qualifiers"] = "true"
        if rivet is not None:
            clean_rivet = _clean_input_text(
                rivet,
                field_name="Rivet analysis name",
                max_length=MAX_RIVET_ANALYSIS_LENGTH,
            )
            params["rivet"] = clean_rivet

        return str(self._record_url(record_identifier.path_segment, params))

    def _record_url(
        self,
        record_path_segment: str,
        params: Mapping[str, str | int | bool] | None = None,
    ) -> httpx.URL:
        return self._build_url(f"/record/{record_path_segment}", params)

    def _build_url(
        self,
        path: str,
        params: Mapping[str, str | int | bool] | None = None,
    ) -> httpx.URL:
        url = self._base_url.join(path)
        if params:
            url = url.copy_merge_params({key: str(value) for key, value in params.items()})
        return url

    def _validate_public_url(self, url: str) -> httpx.URL:
        public_url = httpx.URL(url)
        if public_url.scheme != self._base_url.scheme or public_url.host != self._base_url.host:
            raise ValueError("HEPData metadata URL must use the configured HEPData origin.")
        return public_url

    async def _get_json_object(
        self,
        url: httpx.URL,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> dict[str, JsonValue]:
        data = await self._get_json_value(url, headers=headers)
        if not isinstance(data, dict):
            raise HEPDataHTTPError(200, str(url), "Expected a JSON object from HEPData.")
        return data

    async def _get_json_value(
        self,
        url: httpx.URL,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> JsonValue:
        response = await self._get(url, headers=headers)
        try:
            data = response.json()
        except ValueError as exc:
            raise HEPDataHTTPError(
                response.status_code,
                str(url),
                "Response was not valid JSON.",
            ) from exc
        return cast(JsonValue, data)

    async def _get(
        self,
        url: httpx.URL,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> httpx.Response:
        request_id = uuid.uuid4().hex[:12]
        LOGGER.debug(
            "Starting HEPData request",
            extra={"request_id": request_id, "url": str(url)},
        )
        current_url = url
        for redirect_count in range(MAX_SAFE_REDIRECTS + 1):
            response: httpx.Response | None = None
            try:
                request = self._http_client.build_request("GET", current_url, headers=headers)
                response = await self._http_client.send(request, stream=True)
                response = await self._read_bounded_response(response, str(current_url))
            except httpx.TransportError as exc:
                LOGGER.debug(
                    "HEPData request failed",
                    extra={"request_id": request_id, "url": str(current_url), "error": str(exc)},
                )
                raise HEPDataTransportError(str(current_url), str(exc)) from exc
            finally:
                if response is not None:
                    await response.aclose()

            if not response.is_redirect:
                break

            redirect_url = _safe_redirect_url(response, current_url)
            if redirect_url is None:
                LOGGER.debug(
                    "HEPData request returned unexpected redirect",
                    extra={
                        "request_id": request_id,
                        "url": str(current_url),
                        "status_code": response.status_code,
                    },
                )
                raise HEPDataHTTPError(
                    response.status_code,
                    str(current_url),
                    "Unexpected redirect from HEPData.",
                )
            if redirect_count == MAX_SAFE_REDIRECTS:
                raise HEPDataHTTPError(
                    response.status_code,
                    str(current_url),
                    "Too many redirects from HEPData.",
                )
            current_url = redirect_url

        assert response is not None
        content = response.content

        if response.is_error:
            LOGGER.debug(
                "HEPData request returned error status",
                extra={
                    "request_id": request_id,
                    "url": str(url),
                    "status_code": response.status_code,
                },
            )
            raise HEPDataHTTPError(
                response.status_code,
                str(url),
                _response_error_detail(response),
            )

        LOGGER.debug(
            "Completed HEPData request",
            extra={
                "request_id": request_id,
                "url": str(url),
                "status_code": response.status_code,
                "response_bytes": len(content),
            },
        )
        return response

    async def _read_bounded_response(self, response: httpx.Response, url: str) -> httpx.Response:
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                declared_length = int(content_length)
            except ValueError:
                declared_length = None
            if declared_length is not None and declared_length > self._max_response_bytes:
                raise HEPDataResponseTooLargeError(url, self._max_response_bytes)

        chunks: list[bytes] = []
        total_bytes = 0
        async for chunk in response.aiter_bytes():
            total_bytes += len(chunk)
            if total_bytes > self._max_response_bytes:
                raise HEPDataResponseTooLargeError(url, self._max_response_bytes)
            chunks.append(chunk)

        headers = {
            key: value
            for key, value in response.headers.items()
            if key.lower() not in {"content-encoding", "content-length"}
        }
        return httpx.Response(
            status_code=response.status_code,
            headers=headers,
            content=b"".join(chunks),
            request=response.request,
            extensions=response.extensions,
        )


def _validate_page_size(*, page: int, size: int) -> None:
    if page < 1:
        raise ValueError("Page must be greater than or equal to 1.")
    if not 1 <= size <= 100:
        raise ValueError("Size must be between 1 and 100.")


def _validate_version(version: int) -> int:
    if version < 1:
        raise ValueError("Version must be greater than or equal to 1.")
    return version


def _validate_base_url(base_url: str) -> httpx.URL:
    url = httpx.URL(base_url)
    if url.scheme != "https":
        raise ValueError("HEPData base URL must use HTTPS.")
    if url.username or url.password:
        raise ValueError("HEPData base URL must not include credentials.")
    if not url.host:
        raise ValueError("HEPData base URL must include a host.")
    return url


def _clean_input_text(value: str, *, field_name: str, max_length: int) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} cannot be empty.")
    if len(cleaned) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters.")
    if any(_is_control_character(character) for character in cleaned):
        raise ValueError(f"{field_name} must not contain control characters.")
    return cleaned


def _is_control_character(character: str) -> bool:
    codepoint = ord(character)
    return codepoint < 32 or codepoint == 127


def _safe_redirect_url(response: httpx.Response, current_url: httpx.URL) -> httpx.URL | None:
    location = response.headers.get("Location")
    if not location:
        return None

    redirect_url = current_url.join(location)
    if redirect_url.scheme != current_url.scheme:
        return None
    if redirect_url.host != current_url.host:
        return None
    return redirect_url


def _response_error_detail(response: httpx.Response, *, max_chars: int = 300) -> str | None:
    content_type = response.headers.get("Content-Type", "")
    if "text" not in content_type and "json" not in content_type and "html" not in content_type:
        return None

    text = " ".join(response.text.split())
    if not text:
        return None
    if len(text) > max_chars:
        return f"{text[:max_chars]}..."
    return text
