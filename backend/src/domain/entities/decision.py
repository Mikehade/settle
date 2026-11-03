"""The mediator's decision — the output of the fixed reasoning chain.

Carries both the chosen action and the full, legible trace of how it was
reached (one field per reasoning step), so the audit trail and the demo
can show the thinking, not just the verdict.
"""
from typing import TypedDict


class Decision(TypedDict, total=False):
    dispute_id: str
    dispute_type: str               # final classification (DisputeType value)
    outcome: str | None             # Outcome value, or None when escalating with no clear outcome
    refund_amount: float | None     # for partial/full refunds; None otherwise
    confidence: float               # 0..1
    rationale: str                  # neutral, plain-language explanation for both parties

    # The chain, step by step (populated as the mediator reasons):
    classification: str             # why this dispute type
    evidence_summary: str           # what the evidence objectively shows
    policy_application: str         # how the seller's fairness policy applies

    # Gate (filled by the executor/guardrails, not the model):
    gate: str                       # GateDecision value: execute | escalate
    escalation_recommendation: str | None  # what the seller is advised to do, if escalated
    gate_reason: str | None         # why it executed or escalated (which guardrail fired)
