"""Audit-trail entry — every mediation decision, fully explainable after the fact.

Stores the inputs (case file), the chain of reasoning (decision), the
confidence, and the action actually taken, so any resolution can be
reconstructed and defended. This is also the demo's closing screen.
"""
import uuid
from datetime import datetime
from typing import Any, TypedDict


class AuditEntry(TypedDict, total=False):
    id: uuid.UUID
    dispute_id: uuid.UUID
    seller_id: uuid.UUID | None     # owning seller (scopes the audit trail)
    paypal_dispute_id: str
    case_file: dict[str, Any]       # the inputs the model saw
    decision: dict[str, Any]        # the full Decision (classification, evidence, policy, outcome, rationale)
    outcome: str | None
    confidence: float
    gate: str                       # execute | escalate
    action_taken: str               # human phrase, e.g. "Issued partial refund of 24.00 USD"
    executed: bool                  # did money/an offer actually move via PayPal
    paypal_result: dict[str, Any]   # the PayPal API response (or escalation marker)
    engine: str                     # "llm_tools" | "langgraph"
    served_by: str | None           # which model produced the decision
    created_at: datetime
