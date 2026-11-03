import pytest

from src.infrastructure.services.dispute_source import DisputeSource


class DummyClient:
    pass


@pytest.fixture
def source() -> DisputeSource:
    return DisputeSource(DummyClient(), mode="fixture")


async def test_list_open_returns_fixtures(source):
    items = await source.list_open()
    ids = {i["dispute_id"] for i in items}
    assert {"FIXTURE-NR-001", "FIXTURE-NAD-001", "FIXTURE-UNAUTH-001"} <= ids


async def test_get_case_file_builds_record(source):
    cf = await source.get_case_file("FIXTURE-NR-001")
    assert cf["dispute_type"] == "not_received"
    assert cf["tracking_status"] == "not_shipped"
    assert cf["currency"] == "USD"


async def test_unknown_fixture_raises(source):
    with pytest.raises(KeyError):
        await source.get_case_file("FIXTURE-DOES-NOT-EXIST")
