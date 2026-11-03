async def test_liveness(client):
    res = await client.get("/api/v1/health")
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "success" and body["data"] == {"alive": True}
    assert res.headers["X-Request-ID"]


async def test_readiness_uses_the_database(client):
    res = await client.get("/api/v1/health/ready")
    assert res.status_code == 200
    assert res.json()["data"] == {"database": True}


async def test_readiness_fails_when_a_check_fails(app, client):
    class DownCheck:
        name = "database"

        async def ping(self) -> bool:
            raise ConnectionError("down")

    from src.core.health import HealthService

    app.container.health_service.override(HealthService(checks=[DownCheck()]))
    res = await client.get("/api/v1/health/ready")
    assert res.status_code == 503
    assert res.json()["code"] == "COMMON_SERVICE_UNAVAILABLE"


async def test_unknown_route_uses_envelope(client):
    res = await client.get("/api/v1/nope", headers={"X-Request-ID": "trace-123"})
    assert res.status_code == 404
    body = res.json()
    assert body["code"] == "COMMON_NOT_FOUND"
    assert body["meta"]["request_id"] == "trace-123"
    assert res.headers["X-Request-ID"] == "trace-123"
