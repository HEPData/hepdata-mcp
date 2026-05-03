import gzip

import httpx
import pytest
import respx

from hepdata_mcp.client import HEPDataClient
from hepdata_mcp.errors import (
    HEPDataHTTPError,
    HEPDataResponseTooLargeError,
    HEPDataTransportError,
)


@pytest.mark.asyncio
async def test_search_records_fetches_json_with_pagination() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/search/?q=lhcb&page=2&size=5&format=json").mock(
            return_value=httpx.Response(200, json={"results": [{"title": "LHCb"}], "total": 1})
        )

        async with HEPDataClient() as client:
            result = await client.search_records(" lhcb ", page=2, size=5)

    assert result.query == "lhcb"
    assert result.page == 2
    assert result.size == 5
    assert result.data["total"] == 1
    assert result.source.url == "https://www.hepdata.net/search/?q=lhcb&page=2&size=5&format=json"


@pytest.mark.asyncio
async def test_get_record_fetches_light_json_record() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get(
            "https://www.hepdata.net/record/ins3103133?format=json&version=2&light=true"
        ).mock(
            return_value=httpx.Response(200, json={"record": {"id": "ins3103133"}, "tables": []})
        )

        async with HEPDataClient() as client:
            result = await client.get_record("ins3103133", version=2)

    assert result.identifier == "ins3103133"
    assert result.version == 2
    assert result.light is True
    assert result.data["tables"] == []


@pytest.mark.asyncio
async def test_get_table_fetches_json_table() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json&table=Table+1").mock(
            return_value=httpx.Response(
                200,
                json={"independent_variables": [], "dependent_variables": []},
                headers={"Content-Type": "application/json"},
            )
        )

        async with HEPDataClient() as client:
            result = await client.get_table("ins3103133", "Table 1")

    assert result.table == "Table 1"
    assert result.format == "json"
    assert result.content_type == "application/json"
    assert isinstance(result.data, dict)


@pytest.mark.asyncio
async def test_get_table_fetches_text_export() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=csv&table=Table+1").mock(
            return_value=httpx.Response(
                200,
                text="x,y\n1,2\n",
                headers={"Content-Type": "text/csv"},
            )
        )

        async with HEPDataClient() as client:
            result = await client.get_table("ins3103133", "Table 1", format="csv")

    assert result.format == "csv"
    assert result.content_type == "text/csv"
    assert result.data == "x,y\n1,2\n"


@pytest.mark.asyncio
async def test_get_jsonld_uses_accept_header() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get("https://www.hepdata.net/record/ins3103133").mock(
            return_value=httpx.Response(200, json={"@context": "https://schema.org"})
        )

        async with HEPDataClient() as client:
            result = await client.get_jsonld("ins3103133")

    request = route.calls.last.request
    assert request.headers["Accept"] == "application/ld+json"
    assert result.data == {"@context": "https://schema.org"}


@pytest.mark.asyncio
async def test_get_record_exports_builds_all_supported_links() -> None:
    async with HEPDataClient() as client:
        exports = client.get_record_exports("https://doi.org/10.17182/hepdata.167818.v1", version=1)

        assert exports.identifier == "167818"
        assert {export.format for export in exports.exports} == {
            "csv",
            "json",
            "original",
            "root",
            "yaml",
            "yoda",
            "yoda.h5",
            "yoda1",
        }
        assert {export.format for export in exports.exports if export.binary} == {
            "csv",
            "original",
            "root",
            "yaml",
            "yoda",
            "yoda.h5",
            "yoda1",
        }
        assert not any(export.binary for export in exports.exports if export.format == "json")
        assert "version=1" in exports.exports[0].url


@pytest.mark.asyncio
async def test_build_record_export_url_includes_optional_parameters() -> None:
    async with HEPDataClient() as client:
        url = client.build_record_export_url(
            "ins3103133",
            format="yaml",
            version=3,
            table="Table 1",
            light=True,
            qualifiers=True,
            rivet="LHCB_2025_I3103133",
        )

    assert url == (
        "https://www.hepdata.net/record/ins3103133?format=yaml&version=3&table=Table+1"
        "&light=true&qualifiers=true&rivet=LHCB_2025_I3103133"
    )


@pytest.mark.asyncio
async def test_http_errors_are_mapped() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/missing?format=json&light=true").mock(
            return_value=httpx.Response(404, text="not found")
        )

        async with HEPDataClient() as client:
            with pytest.raises(HEPDataHTTPError) as exc_info:
                await client.get_record("missing")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_transport_errors_are_mapped() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json&light=true").mock(
            side_effect=httpx.ConnectError("boom")
        )

        async with HEPDataClient() as client:
            with pytest.raises(HEPDataTransportError):
                await client.get_record("ins3103133")


@pytest.mark.asyncio
async def test_redirects_are_rejected() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json&light=true").mock(
            return_value=httpx.Response(
                302,
                headers={"Location": "http://127.0.0.1/private"},
            )
        )

        async with HEPDataClient() as client:
            with pytest.raises(HEPDataHTTPError) as exc_info:
                await client.get_record("ins3103133")

    assert exc_info.value.status_code == 302
    assert "Unexpected redirect" in str(exc_info.value)


@pytest.mark.asyncio
async def test_same_origin_redirects_are_followed() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json&table=Table+1").mock(
            return_value=httpx.Response(
                302,
                headers={"Location": "/record/data/167818/1888814/1/"},
            )
        )
        router.get("https://www.hepdata.net/record/data/167818/1888814/1/").mock(
            return_value=httpx.Response(
                200,
                json={"name": "Table 1", "values": []},
                headers={"Content-Type": "application/json"},
            )
        )

        async with HEPDataClient() as client:
            result = await client.get_table("ins3103133", "Table 1")

    assert (
        result.source.url == "https://www.hepdata.net/record/ins3103133?format=json&table=Table+1"
    )
    assert result.data == {"name": "Table 1", "values": []}


@pytest.mark.asyncio
async def test_response_size_limit_uses_declared_content_length() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json&light=true").mock(
            return_value=httpx.Response(
                200,
                json={"ok": True},
                headers={"Content-Length": "100"},
            )
        )

        async with HEPDataClient(max_response_bytes=5) as client:
            with pytest.raises(HEPDataResponseTooLargeError):
                await client.get_record("ins3103133")


@pytest.mark.asyncio
async def test_response_size_limit_applies_while_reading_body() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json&light=true").mock(
            return_value=httpx.Response(
                200,
                content=b'{"too":"large"}',
                headers={"Content-Length": "invalid"},
            )
        )

        async with HEPDataClient(max_response_bytes=5) as client:
            with pytest.raises(HEPDataResponseTooLargeError):
                await client.get_record("ins3103133")


@pytest.mark.asyncio
async def test_decoded_stream_response_does_not_reapply_content_encoding() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json&light=true").mock(
            return_value=httpx.Response(
                200,
                content=gzip.compress(b'{"record":{"id":"ins3103133"}}'),
                headers={"Content-Encoding": "gzip"},
            )
        )

        async with HEPDataClient(max_response_bytes=1_000) as client:
            result = await client.get_record("ins3103133")

    assert result.data == {"record": {"id": "ins3103133"}}


def test_base_url_must_use_https() -> None:
    with pytest.raises(ValueError, match="HTTPS"):
        HEPDataClient(base_url="http://www.hepdata.net")


def test_client_rejects_non_positive_limits() -> None:
    with pytest.raises(ValueError, match="timeout"):
        HEPDataClient(timeout=0)

    with pytest.raises(ValueError, match="response size"):
        HEPDataClient(max_response_bytes=0)


@pytest.mark.asyncio
async def test_search_query_rejects_control_characters() -> None:
    async with HEPDataClient() as client:
        with pytest.raises(ValueError, match="control characters"):
            await client.search_records("lhcb\natlas")


@pytest.mark.asyncio
async def test_table_name_rejects_overlong_input() -> None:
    async with HEPDataClient() as client:
        with pytest.raises(ValueError, match="at most 200 characters"):
            await client.get_table("ins3103133", "x" * 201)
