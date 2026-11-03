"""~15 labelled dispute cases spanning the 3 types and 3 outcomes.

Each case is a (case_file, proposed_decision, expected_gate, label) tuple.
The regression test runs each proposal through the real PayPalExecutor
(with a fake PayPal client) and asserts the gate decision — so the
guardrail behaviour for every type/outcome/amount/confidence combination
is pinned and runs offline. The model's *judgment* is covered separately
by the live demo; this pins the deterministic safety layer.
"""
from src.domain.core.constants.dispute_types import DisputeType
from src.domain.core.constants.outcomes import GateDecision, Outcome
from src.domain.entities.case_file import CaseFile
from src.domain.entities.decision import Decision


def _cf(dispute_id, dtype, amount, capture="CAP", prior=0.0, currency="USD") -> CaseFile:
    return CaseFile(dispute_id=dispute_id, dispute_type=dtype, disputed_amount=amount, currency=currency, capture_id=capture, prior_refunds=prior)


def _d(outcome, confidence, amount=None, rec=None) -> Decision:
    return Decision(outcome=outcome, refund_amount=amount, confidence=confidence, rationale="r", escalation_recommendation=rec)


# (label, case_file, decision, expected_gate)
LABELLED_CASES = [
    # --- not_received ---
    ("NR full refund, not shipped, high confidence",
     _cf("C1", DisputeType.NOT_RECEIVED.value, 40), _d(Outcome.REFUND.value, 0.95, 40), GateDecision.EXECUTE),
    ("NR escalate: low confidence",
     _cf("C2", DisputeType.NOT_RECEIVED.value, 40), _d(Outcome.REFUND.value, 0.6, 40), GateDecision.ESCALATE),
    ("NR escalate: high amount",
     _cf("C3", DisputeType.NOT_RECEIVED.value, 350), _d(Outcome.REFUND.value, 0.97, 350), GateDecision.ESCALATE),
    ("NR accept small, confident",
     _cf("C4", DisputeType.NOT_RECEIVED.value, 30), _d(Outcome.ACCEPT.value, 0.9), GateDecision.EXECUTE),
    ("NR reship confident",
     _cf("C5", DisputeType.NOT_RECEIVED.value, 45), _d(Outcome.RESHIP.value, 0.9), GateDecision.EXECUTE),

    # --- not_as_described ---
    ("NAD partial refund within ceiling",
     _cf("C6", DisputeType.NOT_AS_DESCRIBED.value, 120), _d(Outcome.REFUND.value, 0.9, 30), GateDecision.EXECUTE),
    ("NAD partial refund over ceiling escalates",
     _cf("C7", DisputeType.NOT_AS_DESCRIBED.value, 190), _d(Outcome.REFUND.value, 0.95, 160), GateDecision.ESCALATE),
    ("NAD reship confident",
     _cf("C8", DisputeType.NOT_AS_DESCRIBED.value, 32), _d(Outcome.RESHIP.value, 0.9), GateDecision.EXECUTE),
    ("NAD escalate: borderline confidence",
     _cf("C9", DisputeType.NOT_AS_DESCRIBED.value, 60), _d(Outcome.REFUND.value, 0.79, 20), GateDecision.ESCALATE),
    ("NAD refund exceeds balance escalates",
     _cf("C10", DisputeType.NOT_AS_DESCRIBED.value, 50, prior=40), _d(Outcome.REFUND.value, 0.95, 40), GateDecision.ESCALATE),

    # --- unauthorized_or_other ---
    ("UNAUTH high-value always escalates",
     _cf("C11", DisputeType.UNAUTHORIZED_OR_OTHER.value, 500), _d(Outcome.ACCEPT.value, 0.99), GateDecision.ESCALATE),
    ("UNAUTH small accept executes",
     _cf("C12", DisputeType.UNAUTHORIZED_OR_OTHER.value, 25), _d(Outcome.ACCEPT.value, 0.9), GateDecision.EXECUTE),
    ("UNAUTH explicit escalate (no outcome)",
     _cf("C13", DisputeType.UNAUTHORIZED_OR_OTHER.value, 80), _d(None, 0.5, rec="manual"), GateDecision.ESCALATE),

    # --- edge cases ---
    ("Refund missing amount escalates",
     _cf("C14", DisputeType.NOT_RECEIVED.value, 40), _d(Outcome.REFUND.value, 0.95, None), GateDecision.ESCALATE),
    ("Boundary confidence exactly at threshold executes",
     _cf("C15", DisputeType.NOT_RECEIVED.value, 20), _d(Outcome.REFUND.value, 0.80, 20), GateDecision.EXECUTE),
]
