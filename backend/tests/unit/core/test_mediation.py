"""MediationService approve/reject guards — the money-safety logic.

These are the tests the frontend flagged as missing. They prove a case can't
be executed twice, can't be acted on unless it's actually awaiting the seller,
and that reject is a distinct terminal state."""
import uuid

import pytest

from src.core.mediation import MediationService
from src.domain.core.constants.statuses import DisputeStatus
from src.domain.exceptions import BusinessRuleError, ConflictError
from src.shared.errors import ErrorCode

SELLER = uuid.uuid4()
DID = uuid.uuid4()


class FakeDisputes:
    def __init__(self, status):
        self.dispute = {"id": DID, "seller_id": SELLER, "status": status}
        self.status_calls = []

    async def get_by_paypal(self, paypal_dispute_id, *, seller_id=None):
        # Mimics ownership: raises if not owned would be NotFoundError, but these
        # tests pass the owning seller.
        return self.dispute

    async def set_status(self, dispute_id, *, status, outcome=None, refund_amount=None, confidence=None):
        self.status_calls.append(status)


class FakeAudit:
    def __init__(self, entries):
        self._entries = entries
        self.recorded = []

    async def list_for_dispute(self, dispute_id, *, seller_id=None):
        return list(self._entries)

    async def record(self, **kwargs):
        self.recorded.append(kwargs)
        return {}


class FakeExecutor:
    def __init__(self):
        self.calls = []

    async def execute(self, case_file, decision, policy=None, approved=False):
        self.calls.append((approved, dict(decision)))
        gated = dict(decision)
        gated["gate"] = "execute"
        return {"executed": True, "gate": "execute", "action_taken": "Issued refund of 59.99 USD", "paypal_result": {"ok": True}, "decision": gated}


def _svc(disputes, audit, executor):
    return MediationService(
        dispute_source=None, executor=executor, mediator_factory=None,
        dispute_service=disputes, policy_service=None, audit_service=audit,
    )


def _escalation_entry(executed=False):
    return {
        "gate": DisputeStatus.ESCALATED.value if False else "escalate",
        "executed": executed,
        "decision": {"outcome": "refund", "confidence": 0.7, "refund_amount": 59.99},
        "case_file": {"dispute_id": "FIXTURE-NR-001", "capture_id": None},
    }


async def test_approve_executes_once_and_resolves():
    disputes = FakeDisputes(DisputeStatus.ESCALATED.value)
    audit = FakeAudit([_escalation_entry()])
    executor = FakeExecutor()
    out = await _svc(disputes, audit, executor).approve("FIXTURE-NR-001", seller_id=SELLER)
    assert len(executor.calls) == 1 and executor.calls[0][0] is True  # approved=True, once
    assert "resolved" in disputes.status_calls
    assert out["result"]["executed"] is True
    assert out["decision"]["outcome"] == "refund"


async def test_approve_on_resolved_case_does_not_refund_again():
    # The double-refund hole: approving a case that already executed must be blocked.
    disputes = FakeDisputes(DisputeStatus.RESOLVED.value)
    audit = FakeAudit([_escalation_entry(executed=True)])
    executor = FakeExecutor()
    with pytest.raises(ConflictError) as ei:
        await _svc(disputes, audit, executor).approve("FIXTURE-NR-001", seller_id=SELLER)
    assert ei.value.code == ErrorCode.DISPUTE_ALREADY_RESOLVED
    assert executor.calls == []  # no PayPal call


async def test_approve_when_latest_already_executed_is_blocked():
    disputes = FakeDisputes(DisputeStatus.ESCALATED.value)  # status stale but entry says executed
    audit = FakeAudit([_escalation_entry(executed=True)])
    executor = FakeExecutor()
    with pytest.raises(ConflictError):
        await _svc(disputes, audit, executor).approve("FIXTURE-NR-001", seller_id=SELLER)
    assert executor.calls == []


async def test_approve_without_prior_decision_errors():
    disputes = FakeDisputes(DisputeStatus.ESCALATED.value)
    audit = FakeAudit([])
    executor = FakeExecutor()
    with pytest.raises(BusinessRuleError):
        await _svc(disputes, audit, executor).approve("FIXTURE-NR-001", seller_id=SELLER)
    assert executor.calls == []


async def test_reject_sets_rejected_and_returns_shape():
    disputes = FakeDisputes(DisputeStatus.ESCALATED.value)
    audit = FakeAudit([_escalation_entry()])
    out = await _svc(disputes, audit, FakeExecutor()).reject("FIXTURE-NR-001", seller_id=SELLER)
    assert disputes.status_calls == [DisputeStatus.REJECTED.value]
    assert out["rationale"] and out["action_taken"]
    assert out["decision"]["outcome"] == "refund"


async def test_reject_on_resolved_case_blocked():
    disputes = FakeDisputes(DisputeStatus.RESOLVED.value)
    with pytest.raises(ConflictError):
        await _svc(disputes, FakeAudit([]), FakeExecutor()).reject("FIXTURE-NR-001", seller_id=SELLER)
