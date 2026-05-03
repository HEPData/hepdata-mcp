"""Identifier normalization and URL helpers for HEPData."""

import re
from dataclasses import dataclass
from typing import Literal, cast
from urllib.parse import ParseResult, quote, urlparse

from hepdata_mcp.errors import HEPDataFormatError, HEPDataIdentifierError

RecordExportFormat = Literal["json", "original", "yaml", "csv", "root", "yoda", "yoda1", "yoda.h5"]
TableFormat = Literal["json", "yaml", "csv"]

SUPPORTED_RECORD_EXPORT_FORMATS: frozenset[str] = frozenset(
    {"json", "original", "yaml", "csv", "root", "yoda", "yoda1", "yoda.h5"}
)
SUPPORTED_TABLE_FORMATS: frozenset[str] = frozenset({"json", "yaml", "csv"})
MAX_RECORD_IDENTIFIER_LENGTH = 100
RECORD_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z0-9._-]+$")


@dataclass(frozen=True)
class RecordIdentifier:
    """A normalized HEPData record identifier usable as one URL path segment."""

    value: str

    @property
    def path_segment(self) -> str:
        """Return a safely encoded path segment."""
        return quote(self.value, safe="")


def normalize_record_identifier(identifier: str) -> RecordIdentifier:
    """Normalize common record identifiers to the value used in `/record/{identifier}`."""
    value = identifier.strip()
    if not value:
        raise HEPDataIdentifierError("HEPData record identifier cannot be empty.")

    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        value = _record_identifier_from_url(parsed)

    if value.lower().startswith("doi:"):
        value = value[4:]

    doi_record_id = _record_id_from_hepdata_doi(value)
    if doi_record_id is not None:
        value = doi_record_id

    if len(value) > MAX_RECORD_IDENTIFIER_LENGTH:
        raise HEPDataIdentifierError("HEPData record identifier is too long.")

    has_path_syntax = "/" in value or "?" in value or "#" in value
    if has_path_syntax or not RECORD_IDENTIFIER_PATTERN.fullmatch(value):
        raise HEPDataIdentifierError(
            "HEPData record identifier must be an INSPIRE ID, record ID, HEPData record URL, "
            "or HEPData DOI."
        )

    return RecordIdentifier(value=value)


def validate_record_export_format(format_name: str) -> RecordExportFormat:
    """Validate and narrow a record export format."""
    if format_name not in SUPPORTED_RECORD_EXPORT_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_RECORD_EXPORT_FORMATS))
        raise HEPDataFormatError(
            f"Unsupported HEPData export format '{format_name}'. Use one of: {supported}."
        )
    return cast(RecordExportFormat, format_name)


def validate_table_format(format_name: str) -> TableFormat:
    """Validate and narrow a table export format."""
    if format_name not in SUPPORTED_TABLE_FORMATS:
        supported = ", ".join(sorted(SUPPORTED_TABLE_FORMATS))
        raise HEPDataFormatError(
            f"Unsupported HEPData table format '{format_name}'. Use one of: {supported}."
        )
    return cast(TableFormat, format_name)


def _record_identifier_from_url(parsed: ParseResult) -> str:
    netloc = parsed.netloc.lower()
    path = parsed.path.strip("/")

    if netloc in {"www.hepdata.net", "hepdata.net"} and path.startswith("record/"):
        parts = path.split("/")
        if len(parts) >= 2 and parts[1]:
            return parts[1]

    if netloc in {"doi.org", "dx.doi.org"}:
        return path

    raise HEPDataIdentifierError("Only HEPData record URLs and HEPData DOI URLs are supported.")


def _record_id_from_hepdata_doi(value: str) -> str | None:
    marker = "hepdata."
    lower_value = value.lower()
    index = lower_value.find(marker)
    if index == -1:
        return None

    tail = value[index + len(marker) :]
    record_id = tail.split(".", maxsplit=1)[0]
    return record_id if record_id.isdigit() else None
