"""The three dispute types Settle handles.

The mediator classifies every incoming dispute into exactly one of these.
PayPal's own `reason` codes are mapped onto these three buckets so the
reasoning chain, the prompts and the test fixtures all speak one
vocabulary. Keeping the set closed (three, not open-ended) is what makes
the mediator testable and the demo legible.
"""
from enum import StrEnum


class DisputeType(StrEnum):
    NOT_RECEIVED = "not_received"           # item never arrived
    NOT_AS_DESCRIBED = "not_as_described"   # arrived, but wrong/defective/not as described
    UNAUTHORIZED_OR_OTHER = "unauthorized_or_other"  # unauthorized, billing, everything else


# PayPal Customer Disputes `reason` values → our three buckets.
# https://developer.paypal.com/docs/api/customer-disputes/v1/#definition-dispute_reason
PAYPAL_REASON_TO_TYPE: dict[str, DisputeType] = {
    "MERCHANDISE_OR_SERVICE_NOT_RECEIVED": DisputeType.NOT_RECEIVED,
    "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED": DisputeType.NOT_AS_DESCRIBED,
    "UNAUTHORISED": DisputeType.UNAUTHORIZED_OR_OTHER,
    "CREDIT_NOT_PROCESSED": DisputeType.UNAUTHORIZED_OR_OTHER,
    "DUPLICATE_TRANSACTION": DisputeType.UNAUTHORIZED_OR_OTHER,
    "INCORRECT_AMOUNT": DisputeType.UNAUTHORIZED_OR_OTHER,
    "PAYMENT_BY_OTHER_MEANS": DisputeType.UNAUTHORIZED_OR_OTHER,
    "CANCELED_RECURRING_BILLING": DisputeType.UNAUTHORIZED_OR_OTHER,
    "PROBLEM_WITH_REMITTANCE": DisputeType.UNAUTHORIZED_OR_OTHER,
}


def classify_reason(paypal_reason: str | None) -> DisputeType:
    """Best-effort map from a PayPal reason code to a DisputeType.

    Unknown or missing reasons fall back to UNAUTHORIZED_OR_OTHER, the
    catch-all bucket — the LLM classifier still refines this from the
    written complaint, but this gives the case file a sensible default.
    """
    if not paypal_reason:
        return DisputeType.UNAUTHORIZED_OR_OTHER
    return PAYPAL_REASON_TO_TYPE.get(paypal_reason.strip().upper(), DisputeType.UNAUTHORIZED_OR_OTHER)
