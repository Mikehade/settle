"""Seller fairness policy — plain-English rules plus numeric guardrails.

The seller sets this once. `rules_text` is fed to the mediator verbatim
(the plain-English policy it must apply); the numeric fields are the
guardrail bounds the executor enforces before any money moves. Numeric
fields left as None fall back to DEFAULT_GUARDRAILS.
"""
import uuid
from datetime import datetime
from typing import TypedDict


class FairnessPolicy(TypedDict, total=False):
    id: uuid.UUID
    seller_id: uuid.UUID
    rules_text: str                     # e.g. "Always refund under $25. Replace before refunding."
    confidence_threshold: float | None  # below this, escalate
    human_in_loop_amount: float | None  # at/above this disputed amount, always escalate
    partial_refund_ceiling: float | None  # largest auto-refund without a seller tap
    auto_accept_max: float | None        # never auto-accept above this
    always_refund_under: float | None    # auto-refund in full below this amount
    created_at: datetime
    updated_at: datetime


class FairnessPolicyUpdate(TypedDict, total=False):
    rules_text: str
    confidence_threshold: float | None
    human_in_loop_amount: float | None
    partial_refund_ceiling: float | None
    auto_accept_max: float | None
    always_refund_under: float | None
