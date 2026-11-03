"""API tests through httpx with the container overridden — no DB, no AWS,
no PayPal. Confirms auth is enforced and the mediation trigger returns the
service summary in the standard envelope."""
import uuid
from datetime import UTC, datetime

import pytest

AUTH = {"Authorization": "Bearer test"}


class FakeAuth:
    async def resolve_token(self, token):
        now = datetime.now(UTC)
        return {"id": uuid.uuid4(), "email": "seller@example.com", "full_name": "Seller", "is_active": True, "is_superuser": False, "created_at": now, "updated_at": now}


class FakeMediation:
    async def list_open(self):
        return [{"dispute_id": "FIXTURE-NR-001", "status": "open", "reason": "NOT_RECEIVED", "source": "fixture"}]

    async def mediate(self, dispute_id, *, seller_id=None):
        return {"dispute_id": dispute_id, "gate": "execute", "executed": True, "action_taken": "Issued refund of 59.99 USD", "rationale": "tracking shows never shipped", "decision": {"outcome": "refund"}}


@pytest.fixture
def authed(app):
    app.container.auth_service.override(FakeAuth())
    app.container.mediation_service.override(FakeMediation())
    return app


async def test_open_requires_auth(client):
    resp = await client.get("/api/v1/disputes/open")
    assert resp.status_code == 401
    assert resp.json()["status"] == "error"


async def test_list_open(client, authed):
    resp = await client.get("/api/v1/disputes/open", headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "success"
    assert body["data"][0]["dispute_id"] == "FIXTURE-NR-001"


async def test_mediate_returns_summary(client, authed):
    resp = await client.post("/api/v1/disputes/FIXTURE-NR-001/mediate", headers=AUTH)
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["executed"] is True
    assert data["gate"] == "execute"
    assert "refund" in data["action_taken"].lower()
