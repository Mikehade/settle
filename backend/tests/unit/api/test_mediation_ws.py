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
    async def mediate_stream(self, dispute_id, *, seller_id=None):
        yield {"type": "detected", "dispute_id": dispute_id}
        yield {"type": "gathering", "dispute_id": dispute_id}
        yield {"type": "reasoning_step", "stage": "classify", "text": "not_received"}
        yield {"type": "token", "text": "Tracking shows never shipped."}
        yield {"type": "decision", "decision": {"outcome": "refund", "confidence": 0.95, "refund_amount": 59.99}}
        yield {"type": "executed", "result": {"executed": True, "action_taken": "Issued refund of 59.99 USD"}, "decision": {"outcome": "refund"}}
        yield {"type": "explained", "rationale": "Fair refund.", "action_taken": "Issued refund"}


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
        for _ in range(7):
            msg = ws.receive_json()
            seen.append(msg["event"])
            if msg["event"] == "case.explained":
                break
    assert "case.detected" in seen
    assert "case.decision" in seen
    assert "case.executed" in seen
    assert "case.explained" in seen


def test_mediation_ws_rejects_missing_token(ws_app):
    with TestClient(ws_app) as http, pytest.raises(WebSocketDisconnect), http.websocket_connect("/api/v1/ws/mediation") as ws:
        ws.receive_json()
