"""
PayPalExecutor — the trust boundary.

Takes the mediator's proposed Decision and, BEFORE any PayPal call,
enforces the guardrails (confidence floor, human-in-the-loop amount
ceiling, partial-refund ceiling, auto-accept ceiling, amount validation).
It then either performs the real PayPal money movement / offer, or
returns an escalation for the seller. The AI never calls PayPal; this
does. Guardrails here are code — not a prompt instruction the model
could talk itself past.

A proposal targeting a dispute with no real `capture_id` (e.g. a seeded
fixture, or sandbox without a linked capture) is executed as a DRY RUN:
the decision and gate are real, but no PayPal call is made, so the full
flow still streams end to end offline. With a real capture_id and
configured credentials, the refund genuinely moves balance.
"""
from typing import Any

from src.domain.core.constants.guardrails import DEFAULT_GUARDRAILS
from src.domain.core.constants.outcomes import GateDecision, Outcome
from src.domain.entities.case_file import CaseFile
from src.domain.entities.decision import Decision
from src.infrastructure.services.paypal_client import PayPalClient
from src.shared.logging import get_logger

logger = get_logger(__name__)


class PayPalExecutor:
    def __init__(
        self,
        paypal_client: PayPalClient,
        *,
        confidence_threshold: float = DEFAULT_GUARDRAILS.confidence_threshold,
        human_in_loop_amount: float = DEFAULT_GUARDRAILS.human_in_loop_amount,
        partial_refund_ceiling: float = DEFAULT_GUARDRAILS.partial_refund_ceiling,
    ) -> None:
        self._client = paypal_client
        self._confidence_threshold = confidence_threshold
        self._human_in_loop_amount = human_in_loop_amount
        self._partial_refund_ceiling = partial_refund_ceiling

    def _effective(self, policy: dict[str, Any] | None) -> dict[str, float]:
        policy = policy or {}

        def pick(key: str, default: float) -> float:
            val = policy.get(key)
            return float(val) if val is not None else default

        return {
            "confidence_threshold": pick("confidence_threshold", self._confidence_threshold),
            "human_in_loop_amount": pick("human_in_loop_amount", self._human_in_loop_amount),
            "partial_refund_ceiling": pick("partial_refund_ceiling", self._partial_refund_ceiling),
            "auto_accept_max": pick("auto_accept_max", self._human_in_loop_amount),
            "always_refund_under": pick("always_refund_under", 0.0),
        }

    def _gate(self, case_file: CaseFile, decision: Decision, g: dict[str, float]) -> tuple[GateDecision, str]:
        outcome = decision.get("outcome")
        confidence = float(decision.get("confidence", 0.0))
        amount = float(case_file.get("disputed_amount", 0.0))
        prior = float(case_file.get("prior_refunds", 0.0))

        if outcome is None:
            return GateDecision.ESCALATE, "Mediator chose to escalate."
        if confidence < g["confidence_threshold"]:
            return GateDecision.ESCALATE, f"Confidence {confidence:.2f} below threshold {g['confidence_threshold']:.2f}."
        if amount >= g["human_in_loop_amount"]:
            return GateDecision.ESCALATE, f"Disputed amount {amount:.2f} at/above human-in-the-loop ceiling {g['human_in_loop_amount']:.2f}."

        if outcome == Outcome.REFUND.value:
            refund = float(decision.get("refund_amount") or 0.0)
            if refund <= 0:
                return GateDecision.ESCALATE, "Refund amount missing or non-positive."
            if refund > (amount - prior) + 1e-6:
                return GateDecision.ESCALATE, f"Refund {refund:.2f} exceeds refundable balance {amount - prior:.2f}."
            # always_refund_under short-circuits the ceiling for tiny amounts.
            if amount < g["always_refund_under"]:
                return GateDecision.EXECUTE, f"Auto-refund: amount {amount:.2f} under always-refund threshold {g['always_refund_under']:.2f}."
            if refund > g["partial_refund_ceiling"]:
                return GateDecision.ESCALATE, f"Refund {refund:.2f} above partial-refund ceiling {g['partial_refund_ceiling']:.2f}."

        if outcome == Outcome.ACCEPT.value and amount > g["auto_accept_max"]:
            return GateDecision.ESCALATE, f"Auto-accept blocked: amount {amount:.2f} above auto-accept max {g['auto_accept_max']:.2f}."

        return GateDecision.EXECUTE, "Within guardrails."

    async def execute(self, case_file: CaseFile, decision: Decision, policy: dict[str, Any] | None = None, approved: bool = False) -> dict[str, Any]:
        if approved and decision.get("outcome"):
            # Seller tapped approve on an escalated recommendation — the human IS the gate.
            decision["gate"] = GateDecision.EXECUTE.value
            decision["gate_reason"] = "Approved by the seller."
            return await self._perform(case_file, decision, "Approved by the seller.")

        g = self._effective(policy)
        gate, gate_reason = self._gate(case_file, decision, g)
        decision["gate"] = gate.value
        decision["gate_reason"] = gate_reason

        if gate == GateDecision.ESCALATE:
            if not decision.get("escalation_recommendation"):
                decision["escalation_recommendation"] = self._default_recommendation(decision)
            logger.info("Mediation escalated", extra={"event": "executor.escalate", "dispute": case_file.get("dispute_id"), "reason": gate_reason})
            return {"executed": False, "gate": gate.value, "gate_reason": gate_reason, "action_taken": "Escalated to the seller", "paypal_result": {"escalated": True}, "decision": dict(decision)}

        return await self._perform(case_file, decision, gate_reason)

    async def _perform(self, case_file: CaseFile, decision: Decision, gate_reason: str) -> dict[str, Any]:
        dispute_id = case_file.get("dispute_id", "")
        capture_id = case_file.get("capture_id")
        currency = case_file.get("currency", "USD")
        outcome = decision.get("outcome")
        is_dry_run = not capture_id or str(dispute_id).startswith("FIXTURE-")

        try:
            if outcome == Outcome.REFUND.value:
                refund = float(decision.get("refund_amount") or 0.0)
                action = f"Issued refund of {refund:.2f} {currency}"
                if is_dry_run:
                    result = {"dry_run": True, "would_refund": {"amount": refund, "currency": currency, "capture_id": capture_id}}
                else:
                    result = await self._client.refund_capture(capture_id, refund, currency)
            elif outcome == Outcome.RESHIP.value:
                action = "Offered a replacement to the buyer"
                if is_dry_run or not str(dispute_id).isalnum():
                    result = {"dry_run": True, "would_offer": "REFUND_WITH_REPLACEMENT"}
                else:
                    result = await self._client.make_offer(dispute_id, 0.0, currency, decision.get("rationale", ""), "REFUND_WITH_REPLACEMENT")
            elif outcome == Outcome.ACCEPT.value:
                action = "Accepted the claim on the seller's behalf"
                if is_dry_run:
                    result = {"dry_run": True, "would_accept": True}
                else:
                    result = await self._client.accept_claim(dispute_id, decision.get("rationale", ""))
            else:
                return {"executed": False, "gate": GateDecision.ESCALATE.value, "gate_reason": "Unknown outcome", "action_taken": "Escalated", "paypal_result": {}, "decision": dict(decision)}
        except Exception as e:  # noqa: BLE001
            logger.error("PayPal execution failed", extra={"event": "executor.paypal_error", "dispute": dispute_id, "error": str(e)}, exc_info=True)
            decision["gate"] = GateDecision.ESCALATE.value
            decision["gate_reason"] = f"PayPal execution failed: {e}"
            decision.setdefault("escalation_recommendation", "Automatic execution failed; resolve this dispute manually.")
            return {"executed": False, "gate": GateDecision.ESCALATE.value, "gate_reason": decision["gate_reason"], "action_taken": "Execution failed — escalated", "paypal_result": {"error": str(e)}, "decision": dict(decision)}

        logger.info("Mediation executed", extra={"event": "executor.executed", "dispute": dispute_id, "outcome": outcome, "dry_run": is_dry_run})
        return {"executed": not is_dry_run, "dry_run": is_dry_run, "gate": GateDecision.EXECUTE.value, "gate_reason": gate_reason, "action_taken": action + (" (dry run — no live capture)" if is_dry_run else ""), "paypal_result": result, "decision": dict(decision)}

    @staticmethod
    def _default_recommendation(decision: Decision) -> str:
        outcome = decision.get("outcome")
        if outcome == Outcome.REFUND.value:
            return f"Recommended: refund {decision.get('refund_amount')}. Review and approve to proceed."
        if outcome == Outcome.RESHIP.value:
            return "Recommended: offer a replacement. Review and approve to proceed."
        if outcome == Outcome.ACCEPT.value:
            return "Recommended: accept the claim. Review and approve to proceed."
        return "Review this dispute manually in the PayPal Resolution Center."
