"""The executor is the guardrail boundary — tested exhaustively with a
fake PayPal client (no network). These assert that no proposal bypasses
the gate and that each guardrail fires where it should."""
from typing import Any

import pytest

from src.domain.core.constants.outcomes import GateDecision, Outcome
from src.domain.entities.case_file import CaseFile
from src.domain.entities.decision import Decision
from src.infrastructure.services.executor import PayPalExecutor


class FakePayPalClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple, dict]] = []

    async def refund_capture(self, capture_id, amount, currency) -> dict[str, Any]:
        self.calls.append(("refund", (capture_id, amount, currency), {}))
        return {"id": "REFUND-1", "status": "COMPLETED"}

    async def accept_claim(self, dispute_id, note="") -> dict[str, Any]:
        self.calls.append(("accept", (dispute_id,), {"note": note}))
        return {"status": "RESOLVED"}

    async def make_offer(self, dispute_id, amount, currency, note, offer_type) -> dict[str, Any]:
        self.calls.append(("offer", (dispute_id, amount, currency, offer_type), {}))
        return {"status": "OFFER_MADE"}


def _case(amount: float, capture_id: str | None = "CAP-1") -> CaseFile:
    return CaseFile(dispute_id="D-1", disputed_amount=amount, currency="USD", capture_id=capture_id, prior_refunds=0.0)


def _refund(amount: float, confidence: float) -> Decision:
    return Decision(outcome=Outcome.REFUND.value, refund_amount=amount, confidence=confidence, rationale="r")


@pytest.fixture
def client() -> FakePayPalClient:
    return FakePayPalClient()


@pytest.fixture
def executor(client) -> PayPalExecutor:
    return PayPalExecutor(client, confidence_threshold=0.8, human_in_loop_amount=200.0, partial_refund_ceiling=150.0)


async def test_low_confidence_escalates(executor):
    result = await executor.execute(_case(50), _refund(50, 0.5))
    assert result["gate"] == GateDecision.ESCALATE.value
    assert not result["executed"]


async def test_high_amount_escalates(executor):
    result = await executor.execute(_case(500), _refund(500, 0.99))
    assert result["gate"] == GateDecision.ESCALATE.value


async def test_refund_over_ceiling_escalates(executor):
    # confidence + amount ok, but refund above the partial-refund ceiling
    result = await executor.execute(_case(180), _refund(160, 0.95))
    # amount 180 < 200 human-in-loop, but refund 160 > 150 ceiling → escalate
    assert result["gate"] == GateDecision.ESCALATE.value


async def test_valid_refund_executes(executor, client):
    result = await executor.execute(_case(40), _refund(40, 0.95))
    assert result["gate"] == GateDecision.EXECUTE.value
    assert client.calls and client.calls[0][0] == "refund"
    assert result["executed"] is True


async def test_refund_exceeding_balance_escalates(executor):
    result = await executor.execute(_case(40), _refund(90, 0.95))
    assert result["gate"] == GateDecision.ESCALATE.value


async def test_fixture_dispute_is_dry_run(executor, client):
    case = CaseFile(dispute_id="FIXTURE-X", disputed_amount=40, currency="USD", capture_id=None, prior_refunds=0.0)
    result = await executor.execute(case, _refund(40, 0.95))
    assert result["gate"] == GateDecision.EXECUTE.value
    assert result["executed"] is False  # dry run — no live capture
    assert result["paypal_result"].get("dry_run") is True
    assert not client.calls  # never hit PayPal


async def test_always_refund_under_overrides_ceiling(executor, client):
    policy = {"always_refund_under": 25.0}
    result = await executor.execute(_case(20), _refund(20, 0.95), policy)
    assert result["gate"] == GateDecision.EXECUTE.value


async def test_accept_over_auto_accept_max_escalates(executor):
    policy = {"auto_accept_max": 50.0, "human_in_loop_amount": 1000.0}
    decision = Decision(outcome=Outcome.ACCEPT.value, confidence=0.95, rationale="r")
    result = await executor.execute(_case(120), decision, policy)
    assert result["gate"] == GateDecision.ESCALATE.value


async def test_approved_bypasses_gate_and_executes(executor, client):
    # Would normally escalate (high amount), but the seller approved.
    result = await executor.execute(_case(500), _refund(500, 0.6), approved=True)
    assert result["gate"] == GateDecision.EXECUTE.value
    assert client.calls and client.calls[0][0] == "refund"


async def test_escalate_outcome_none(executor):
    decision = Decision(outcome=None, confidence=0.4, rationale="unsure", escalation_recommendation="look")
    result = await executor.execute(_case(30), decision)
    assert result["gate"] == GateDecision.ESCALATE.value
    assert result["decision"]["escalation_recommendation"]
