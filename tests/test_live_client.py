import os

import pytest

from hepdata_mcp.client import HEPDataClient

pytestmark = pytest.mark.skipif(
    os.environ.get("HEPDATA_MCP_LIVE_TESTS") != "1",
    reason="Set HEPDATA_MCP_LIVE_TESTS=1 to run live HEPData smoke tests.",
)


@pytest.mark.asyncio
async def test_live_get_known_record() -> None:
    async with HEPDataClient() as client:
        record = await client.get_record("ins3103133")

    assert record.identifier == "ins3103133"
    assert record.source.url.startswith("https://www.hepdata.net/record/ins3103133")
    assert record.data
