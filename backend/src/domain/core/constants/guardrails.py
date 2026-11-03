"""Guardrail defaults — the trust boundary.

These are the *fallback* values. The effective values for a given case
come from the seller's FairnessPolicy (see domain/entities/policy.py);
these apply when the policy leaves a field unset. The guardrails are
checked in the PayPalExecutor (infrastructure), BEFORE any PayPal call —
never in the prompt — so the boundary is code the team controls, not a
model instruction the model could talk itself past.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GuardrailDefaults:
    # Below this model confidence, never auto-act — escalate with a recommendation.
    confidence_threshold: float = 0.80
    # Any dispute whose disputed amount is at or above this always escalates.
    human_in_loop_amount: float = 200.0
    # The largest auto-refund (absolute) the executor will issue without a seller tap.
    partial_refund_ceiling: float = 150.0


DEFAULT_GUARDRAILS = GuardrailDefaults()
