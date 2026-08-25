import httpx
import pytest
import respx

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


@pytest.mark.asyncio
async def test_search_records_tool_returns_model_dump() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/search/?q=higgs&page=1&size=10&format=json").mock(
            return_value=httpx.Response(200, json={"results": [{"title": "Higgs"}]})
        )

        payload = await search_records_tool("higgs")

    assert payload["query"] == "higgs"
    assert payload["data"] == {"results": [{"title": "Higgs"}]}


@pytest.mark.asyncio
async def test_get_record_tool_returns_record_payload() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json&light=true").mock(
            return_value=httpx.Response(200, json={"record": {"title": "Paper"}, "tables": []})
        )

        payload = await get_record_tool("ins3103133")

    assert payload["identifier"] == "ins3103133"
    assert payload["light"] is True
    assert payload["data"] == {"record": {"title": "Paper"}, "tables": []}


@pytest.mark.asyncio
async def test_list_tables_tool_summarizes_top_level_tables() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json").mock(
            return_value=httpx.Response(
                200,
                json={
                    "tables": [
                        {
                            "id": 10,
                            "name": "Table 1",
                            "description": "Cross-section",
                            "data_file": "table1.yaml",
                            "extra": "ignored",
                        },
                        {"title": "Table 2"},
                    ]
                },
            )
        )

        payload = await list_tables_tool("ins3103133")

    assert payload["table_count"] == 2
    assert payload["tables"] == [
        {
            "name": "Table 1",
            "table_id": "10",
            "description": "Cross-section",
            "data_available": True,
            "available_fields": ["data_file", "description", "extra", "id", "name"],
        },
        {
            "name": "Table 2",
            "table_id": None,
            "description": None,
            "data_available": None,
            "available_fields": ["title"],
        },
    ]


@pytest.mark.asyncio
async def test_list_tables_tool_summarizes_nested_record_tables() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/12345?format=json").mock(
            return_value=httpx.Response(200, json={"record": {"data_tables": ["Table A"]}})
        )

        payload = await list_tables_tool("12345")

    assert payload["tables"] == [
        {
            "name": "Table A",
            "table_id": None,
            "description": None,
            "data_available": None,
            "available_fields": [],
        }
    ]


@pytest.mark.asyncio
async def test_get_table_tool_returns_table_payload() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=csv&table=Table+1").mock(
            return_value=httpx.Response(
                200,
                text="x,y\n1,2\n",
                headers={"Content-Type": "text/csv"},
            )
        )

        payload = await get_table_tool("ins3103133", "Table 1", format="csv")

    assert payload["format"] == "csv"
    assert payload["data"] == "x,y\n1,2\n"


@pytest.mark.asyncio
async def test_describe_table_tool_returns_compact_table_metadata() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data_tables": [
                        {
                            "id": 1888814,
                            "name": "Table 1",
                            "data": {
                                "json": (
                                    "https://www.hepdata.net/download/table/ins3103133/Table 1/json"
                                )
                            },
                        }
                    ]
                },
            )
        )
        router.get("https://www.hepdata.net/download/table/ins3103133/Table%201/json").mock(
            return_value=httpx.Response(
                302,
                headers={"Location": "/record/data/167818/1888814/1/"},
            )
        )
        router.get("https://www.hepdata.net/record/data/167818/1888814/1/").mock(
            return_value=httpx.Response(
                200,
                json={
                    "name": "Table 1",
                    "description": "Differential cross-section",
                    "doi": "10.17182/hepdata.167818.v1/t1",
                    "headers": [
                        {"name": "x", "units": "GeV"},
                        {"name": "y", "units": "pb"},
                    ],
                    "qualifiers": {"SQRT(S)": "13 TeV"},
                    "values": [{"x": [{"low": "0", "high": "1"}], "y": [{"value": "2"}]}],
                    "resources": [{"description": "Image", "type": "png"}],
                },
                headers={"Content-Type": "application/json"},
            )
        )

        payload = await describe_table_tool("ins3103133", "Table 1")

    assert payload["name"] == "Table 1"
    assert payload["doi"] == "10.17182/hepdata.167818.v1/t1"
    assert payload["value_count"] == 1
    assert payload["variables"] == {
        "independent": [{"name": "x", "units": "GeV"}],
        "dependent": [{"name": "y", "units": "pb"}],
    }
    assert payload["qualifiers"] == {"SQRT(S)": "13 TeV"}


@pytest.mark.asyncio
async def test_get_table_tool_truncates_large_text_payload() -> None:
    large_csv = "x\n" + ("1\n" * 20_000)
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=csv&table=Table+1").mock(
            return_value=httpx.Response(200, text=large_csv, headers={"Content-Type": "text/csv"})
        )

        payload = await get_table_tool("ins3103133", "Table 1", format="csv")

    assert payload["truncation"]["truncated"] is True
    assert payload["data"]["_truncated"] is True
    assert payload["data"]["shown_length"] == 20_000


@pytest.mark.asyncio
async def test_get_record_exports_tool_returns_links_without_network() -> None:
    payload = await get_record_exports_tool("ins3103133", version=1)

    assert payload["identifier"] == "ins3103133"
    assert any(export["format"] == "json" for export in payload["exports"])


@pytest.mark.asyncio
async def test_get_record_versions_tool_returns_version_urls() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133?format=json&light=true").mock(
            return_value=httpx.Response(
                200,
                json={"record": {"version": 2}, "version_count": 3},
            )
        )

        payload = await get_record_versions_tool("ins3103133")

    assert payload["current_version"] == 2
    assert payload["latest_version"] == 3
    assert payload["version_count"] == 3
    assert payload["versions"] == [
        {
            "version": 1,
            "record_url": "https://www.hepdata.net/record/ins3103133?format=json&version=1&light=true",
            "is_current": False,
            "is_latest": False,
        },
        {
            "version": 2,
            "record_url": "https://www.hepdata.net/record/ins3103133?format=json&version=2&light=true",
            "is_current": True,
            "is_latest": False,
        },
        {
            "version": 3,
            "record_url": "https://www.hepdata.net/record/ins3103133?format=json&version=3&light=true",
            "is_current": False,
            "is_latest": True,
        },
    ]


@pytest.mark.asyncio
async def test_get_jsonld_tool_returns_jsonld_payload() -> None:
    with respx.mock(assert_all_called=True) as router:
        route = router.get("https://www.hepdata.net/record/ins3103133").mock(
            return_value=httpx.Response(200, json={"@type": "Dataset"})
        )

        payload = await get_jsonld_tool("ins3103133")

    assert route.calls.last.request.headers["Accept"] == "application/ld+json"
    assert payload["data"] == {"@type": "Dataset"}


@pytest.mark.asyncio
async def test_get_jsonld_tool_truncates_large_payload() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/ins3103133").mock(
            return_value=httpx.Response(200, json={"description": "x" * 25_000})
        )

        payload = await get_jsonld_tool("ins3103133")

    assert payload["truncation"]["truncated"] is True
    assert payload["data"]["description"]["_truncated"] is True


@pytest.mark.asyncio
async def test_tool_errors_are_user_safe_value_errors() -> None:
    with pytest.raises(ValueError, match="Search query cannot be empty"):
        await search_records_tool(" ")


@pytest.mark.asyncio
async def test_tool_http_errors_include_source_url_and_upstream_detail() -> None:
    with respx.mock(assert_all_called=True) as router:
        router.get("https://www.hepdata.net/record/missing?format=json&light=true").mock(
            return_value=httpx.Response(
                404,
                text="record not found",
                headers={"Content-Type": "text/plain"},
            )
        )

        with pytest.raises(ValueError) as exc_info:
            await get_record_tool("missing")

    message = str(exc_info.value)
    assert "https://www.hepdata.net/record/missing" in message
    assert "record not found" in message
