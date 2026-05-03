"""Pydantic models exposed by the HEPData client."""

from typing import Any, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue

JsonObject: TypeAlias = dict[str, Any]


class SourceInfo(BaseModel):
    """Details about the upstream HEPData request."""

    url: str


class SearchResult(BaseModel):
    """Raw HEPData search results plus source metadata."""

    source: SourceInfo
    query: str
    page: int = Field(ge=1)
    size: int = Field(ge=1, le=100)
    data: JsonObject

    model_config = ConfigDict(extra="forbid")


class RecordData(BaseModel):
    """Raw HEPData record payload plus source metadata."""

    source: SourceInfo
    identifier: str
    version: int | None
    light: bool
    data: JsonObject

    model_config = ConfigDict(extra="forbid")


class TableData(BaseModel):
    """One HEPData table payload in the requested export format."""

    source: SourceInfo
    identifier: str
    table: str
    version: int | None
    format: str
    content_type: str | None
    data: JsonValue

    model_config = ConfigDict(extra="forbid")


class JSONLDData(BaseModel):
    """JSON-LD metadata returned through HEPData content negotiation."""

    source: SourceInfo
    identifier: str
    data: JsonValue

    model_config = ConfigDict(extra="forbid")


class ExportLink(BaseModel):
    """A stable HEPData record export URL."""

    format: str
    url: str
    binary: bool

    model_config = ConfigDict(extra="forbid")


class ExportLinks(BaseModel):
    """Supported export links for one HEPData record."""

    identifier: str
    version: int | None
    exports: list[ExportLink]

    model_config = ConfigDict(extra="forbid")
