"""WebSocket integration test via Starlette's TestClient — proves the
mediation socket authenticates, accepts a trigger, and streams the mapped
case.* events. Container overridden: no AWS, no PayPal, no DB."""
import uuid
from datetime import UTC, datetime

import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect


class FakeAuth:
    async def resolve_token(self, token):
        now = datetime.now(UTC)
        return {"id": uuid.uuid4(), "email": "seller@example.com", "full_name": "S", "is_active": True, "is_superuser": False, "created_at": now, "updated_at": now}


class FakeMediation:
    async def mediate_stream(self, dispute_id, *, seller_id=None, force_escalate=False):
        yield {"type": "detected", "dispute_id": dispute_id}
        yield {"type": "gathering", "dispute_id": dispute_id}
        yield {"type": "reasoning_step", "stage": "classify", "text": "not_received", "dispute_id": dispute_id}
        yield {"type": "token", "text": "Tracking shows never shipped.", "stage": "weigh", "dispute_id": dispute_id}
        yield {"type": "decision", "dispute_id": dispute_id, "decision": {"outcome": "refund", "confidence": 0.95, "refund_amount": 59.99}}
        yield {"type": "executed", "dispute_id": dispute_id, "result": {"executed": True, "action_taken": "Issued refund of 59.99 USD"}, "decision": {"outcome": "refund"}}
        yield {"type": "explained", "dispute_id": dispute_id, "rationale": "Fair refund.", "action_taken": "Issued refund"}

    # Approve/reject exercised by the dedicated unit tests; present here so the
    # consumer can broadcast their results without a missing-attribute error.
    async def approve(self, dispute_id, *, seller_id=None):
        return {"dispute_id": dispute_id, "result": {"executed": True, "action_taken": "Issued refund"}, "decision": {"outcome": "refund"}}

    async def reject(self, dispute_id, *, seller_id=None):
        return {"dispute_id": dispute_id, "rationale": "declined", "action_taken": "rejected", "decision": {}}


@pytest.fixture
def ws_app(app):
    app.container.auth_service.override(FakeAuth())
    app.container.mediation_service.override(FakeMediation())
    return app


def test_mediation_ws_streams_case_events(ws_app):
    with TestClient(ws_app) as http, http.websocket_connect("/api/v1/ws/mediation?token=test") as ws:
        ready = ws.receive_json()
        assert ready["event"] == "connection.ready"
        ws.send_json({"event": "seller.mediate", "data": {"dispute_id": "FIXTURE-NR-001"}})
        seen = []
        msgs = []
        for _ in range(7):
            msg = ws.receive_json()
            seen.append(msg["event"])
            msgs.append(msg)
            if msg["event"] == "case.explained":
                break
    assert "case.detected" in seen
    assert "case.decision" in seen
    assert "case.executed" in seen
    assert "case.explained" in seen
    # Every case.* frame carries its dispute_id so overlapping runs don't blur.
    for m in msgs:
        if m["event"].startswith("case."):
            assert m["data"].get("dispute_id") == "FIXTURE-NR-001", m
    # Tokens carry their stage so the UI can place them under the right step.
    token = next(m for m in msgs if m["event"] == "case.token")
    assert token["data"].get("stage") == "weigh"


class FakeMediationBadApprove(FakeMediation):
    async def approve(self, dispute_id, *, seller_id=None):
        from src.domain.exceptions import ConflictError
        from src.shared.errors import ErrorCode
        raise ConflictError(ErrorCode.DISPUTE_ALREADY_RESOLVED, "Already resolved")


def test_bad_approve_sends_error_not_close(app):
    app.container.auth_service.override(FakeAuth())
    app.container.mediation_service.override(FakeMediationBadApprove())
    with TestClient(app) as http, http.websocket_connect("/api/v1/ws/mediation?token=test") as ws:
        assert ws.receive_json()["event"] == "connection.ready"
        ws.send_json({"event": "seller.approve", "data": {"dispute_id": "FIXTURE-NR-001"}})
        err = ws.receive_json()
        assert err["event"] == "case.error"
        assert err["data"]["dispute_id"] == "FIXTURE-NR-001"
        assert err["data"].get("code") == "DISPUTE_ALREADY_RESOLVED"
        # The socket must still be alive after a failed action.
        ws.send_json({"event": "ping", "data": {}})
        assert ws.receive_json()["event"] == "agent.typing"


def test_mediation_ws_rejects_missing_token(ws_app):
    with TestClient(ws_app) as http, pytest.raises(WebSocketDisconnect), http.websocket_connect("/api/v1/ws/mediation") as ws:
        ws.receive_json()
