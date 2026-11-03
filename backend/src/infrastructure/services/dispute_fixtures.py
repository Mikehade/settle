"""Seeded demo disputes — one per type.

These let Settle run end to end (and demo) even where the sandbox will
not let you *create* a realistic test dispute. The mediator logic and the
money movement stay 100% real; only the triggering dispute is seeded.
The larger labelled regression set lives under tests/fixtures.

`capture_id` points at a real sandbox capture when you have one (so the
refund genuinely moves balance); leave it None to let the executor treat
the refund as a dry-run and still stream the full decision.
"""
from typing import Any

from src.domain.core.constants.dispute_types import DisputeType

DEMO_FIXTURES: dict[str, dict[str, Any]] = {
    "FIXTURE-NR-001": {
        "dispute_id": "FIXTURE-NR-001",
        "dispute_type": DisputeType.NOT_RECEIVED.value,
        "reason_code": "MERCHANDISE_OR_SERVICE_NOT_RECEIVED",
        "buyer_complaint": "I ordered this three weeks ago and it never arrived. Tracking hasn't updated since the label was created.",
        "seller_response": "We shipped it; sometimes the carrier is slow.",
        "item_name": "Wireless earbuds",
        "item_value": 59.99,
        "disputed_amount": 59.99,
        "currency": "USD",
        "transaction_id": "TXN-NR-001",
        "capture_id": None,
        "tracking_status": "not_shipped",
        "tracking_carrier": None,
        "tracking_number": None,
        "prior_refunds": 0.0,
        "buyer_message_count": 2,
        "seller_message_count": 1,
        "raw": {"note": "seeded fixture"},
    },
    "FIXTURE-NAD-001": {
        "dispute_id": "FIXTURE-NAD-001",
        "dispute_type": DisputeType.NOT_AS_DESCRIBED.value,
        "reason_code": "MERCHANDISE_OR_SERVICE_NOT_AS_DESCRIBED",
        "buyer_complaint": "The shirt arrived but it's a size M, not the L I ordered. Otherwise fine.",
        "seller_response": "We can send the correct size if the buyer returns the wrong one.",
        "item_name": "Cotton shirt",
        "item_value": 32.00,
        "disputed_amount": 32.00,
        "currency": "USD",
        "transaction_id": "TXN-NAD-001",
        "capture_id": None,
        "tracking_status": "delivered",
        "tracking_carrier": "USPS",
        "tracking_number": "9400100000000000000000",
        "prior_refunds": 0.0,
        "buyer_message_count": 1,
        "seller_message_count": 1,
        "raw": {"note": "seeded fixture"},
    },
    "FIXTURE-UNAUTH-001": {
        "dispute_id": "FIXTURE-UNAUTH-001",
        "dispute_type": DisputeType.UNAUTHORIZED_OR_OTHER.value,
        "reason_code": "UNAUTHORISED",
        "buyer_complaint": "I never made this purchase. I don't recognise the charge at all.",
        "seller_response": "The order used the buyer's verified account and shipped to their saved address.",
        "item_name": "Gift card",
        "item_value": 500.00,
        "disputed_amount": 500.00,
        "currency": "USD",
        "transaction_id": "TXN-UNAUTH-001",
        "capture_id": None,
        "tracking_status": "delivered",
        "tracking_carrier": "FedEx",
        "tracking_number": "770000000000",
        "prior_refunds": 0.0,
        "buyer_message_count": 1,
        "seller_message_count": 1,
        "raw": {"note": "seeded fixture"},
    },
}
