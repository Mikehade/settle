from httpx import ASGITransport, AsyncClient

from src.domain.exceptions import ConflictError


async def test_app_error_maps_to_status_and_code(app):
    @app.get("/boom-conflict")
    async def boom():
        raise ConflictError("THING_TAKEN", "Already taken")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res = await client.get("/boom-conflict")
    assert res.status_code == 409
    assert res.json()["code"] == "THING_TAKEN"


async def test_unhandled_error_returns_envelope_with_request_id(app):
    @app.get("/boom")
    async def boom():
        raise RuntimeError("kaboom")

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/boom", headers={"X-Request-ID": "trace-500"})
    assert res.status_code == 500
    body = res.json()
    assert body["code"] == "COMMON_INTERNAL_ERROR"
    assert body["meta"]["request_id"] == "trace-500"
