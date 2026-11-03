"""The three outcomes the mediator may choose, plus escalation.

The agent can only *propose* one of these; a thin executor (infrastructure)
performs the real PayPal call. Keeping outcomes to exactly three is the
scope discipline that makes the build finishable and the demo clear.
"""
from enum import StrEnum


class Outcome(StrEnum):
    REFUND = "refund"       # full or partial refund of the captured payment
    RESHIP = "reship"       # offer a replacement / reshipment instead of money back
    ACCEPT = "accept"       # accept the claim on the seller's behalf to stop fees/escalation


class GateDecision(StrEnum):
    """What the gate step decides to do with a chosen outcome."""

    EXECUTE = "execute"     # confidence + amount within bounds → perform it now
    ESCALATE = "escalate"   # hand to the seller with a recommendation + evidence
