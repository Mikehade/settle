"""Dispute lifecycle statuses — one source of truth for the state machine.

    open         a case the source knows about, not yet mediated (no DB row until seen)
    mediating    a run is in progress (claimed; blocks a second concurrent run)
    resolved     terminal: Settle executed (or dry-ran) an action
    escalated    waiting on the seller — show Approve / Reject (NOT terminal)
    rejected     terminal: the seller declined the recommendation, handling it manually
    failed       terminal: the run errored out before a decision could be acted on

`resolved_at` is stamped only for the terminal states (resolved, rejected,
failed), which is what lets the UI tell "waiting for you" (escalated, no date)
apart from "you rejected it" (rejected, dated).
"""
from enum import StrEnum


class DisputeStatus(StrEnum):
    OPEN = "open"
    MEDIATING = "mediating"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    REJECTED = "rejected"
    FAILED = "failed"


# States a run may already be in that must block a fresh mediation / action.
ACTIVE_OR_DONE = frozenset({DisputeStatus.MEDIATING.value, DisputeStatus.RESOLVED.value, DisputeStatus.REJECTED.value})

# Terminal states: these (and only these) get a resolved_at timestamp.
TERMINAL = frozenset({DisputeStatus.RESOLVED.value, DisputeStatus.REJECTED.value, DisputeStatus.FAILED.value})
