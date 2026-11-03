"""
MediationService — the use case that resolves one dispute end to end.

detect → gather → reason (streamed) → gate/act → explain. It owns the
orchestration and the (short) persistence transactions; it does NOT hold
a DB transaction open across the LLM call or the PayPal call. It yields a
stream of neutral event dicts that the WebSocket consumer maps onto the
`case.*` wire events — so core stays free of any api import.

The mediator agent is built fresh per run (via an injected factory) so
each case gets its own proposal-tool state and concurrent cases never
clash.
"""
import uuid
from collections.abc import AsyncGenerator, Callable
from typing import Any

from src.core.audit import AuditService
from src.core.disputes import DisputeService
from src.core.policy import FairnessPolicyService
from src.domain.core.agents.mediator import MediatorAgent
from src.domain.core.constants.outcomes import GateDecision
from src.domain.entities.decision import Decision
from src.domain.interfaces.services import DisputeSourceInterface, PayPalExecutorInterface
from src.shared.logging import get_logger

logger = get_logger(__name__)


class MediationService:
    def __init__(
        self,
        dispute_source: DisputeSourceInterface,
        executor: PayPalExecutorInterface,
        mediator_factory: Callable[[], MediatorAgent],
        dispute_service: DisputeService,
        policy_service: FairnessPolicyService,
        audit_service: AuditService,
    ) -> None:
        self._source = dispute_source
        self._executor = executor
        self._mediator_factory = mediator_factory
        self._disputes = dispute_service
        self._policies = policy_service
        self._audit = audit_service

    async def list_open(self) -> list[dict[str, Any]]:
        return await self._source.list_open()

    async def mediate(self, dispute_id: str, *, seller_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Run a full mediation and return a summary (drains the stream).

        Used by the REST trigger and tests; the WebSocket path consumes
        `mediate_stream` directly so the reasoning shows live."""
        summary: dict[str, Any] = {"dispute_id": dispute_id, "decision": None, "gate": None, "executed": False, "action_taken": ""}
        async for ev in self.mediate_stream(dispute_id, seller_id=seller_id):
            t = ev.get("type")
            if t == "decision":
                summary["decision"] = ev["decision"]
                summary["gate"] = ev["decision"].get("gate")
            elif t == "executed":
                summary["executed"] = ev["result"].get("executed", False)
                summary["action_taken"] = ev["result"].get("action_taken", "")
            elif t == "escalated":
                summary["action_taken"] = "Escalated to the seller"
                summary["recommendation"] = ev.get("recommendation")
            elif t == "explained":
                summary["rationale"] = ev.get("rationale", "")
            elif t == "error":
                summary["error"] = ev.get("error")
        return summary

    async def approve(self, paypal_dispute_id: str, *, seller_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Seller approved an escalated recommendation — perform it now (the human is the gate)."""
        dispute = await self._disputes.get_by_paypal(paypal_dispute_id)
        entries = await self._audit.list_for_dispute(dispute["id"])
        if not entries:
            return {"dispute_id": paypal_dispute_id, "error": "No prior decision to approve."}
        latest = entries[0]
        decision: Decision = latest["decision"]  # type: ignore[assignment]
        case_file = latest["case_file"]

        if not decision.get("outcome"):
            await self._disputes.mark_resolved(dispute["id"], status="resolved", outcome=None, refund_amount=None, confidence=decision.get("confidence"))
            return {"dispute_id": paypal_dispute_id, "executed": False, "action_taken": "Acknowledged — resolve manually in PayPal."}

        result = await self._executor.execute(case_file, decision, None, approved=True)
        gated = result["decision"]
        await self._audit.record(
            dispute_id=dispute["id"], paypal_dispute_id=paypal_dispute_id, case_file=case_file,
            decision=dict(gated), result=result, engine="approved", served_by=None,
        )
        await self._disputes.mark_resolved(dispute["id"], status="resolved", outcome=gated.get("outcome"), refund_amount=gated.get("refund_amount"), confidence=gated.get("confidence"))
        return {"dispute_id": paypal_dispute_id, "executed": result.get("executed", False), "action_taken": result.get("action_taken", ""), "decision": dict(gated)}

    async def reject(self, paypal_dispute_id: str, *, seller_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Seller rejected the recommendation — mark it for manual handling."""
        dispute = await self._disputes.get_by_paypal(paypal_dispute_id)
        await self._disputes.mark_resolved(dispute["id"], status="escalated", outcome=None, refund_amount=None, confidence=None)
        return {"dispute_id": paypal_dispute_id, "executed": False, "action_taken": "Recommendation rejected — left for manual handling."}

    async def mediate_stream(self, dispute_id: str, *, seller_id: uuid.UUID | None = None) -> AsyncGenerator[dict, None]:
        yield {"type": "detected", "dispute_id": dispute_id}
        yield {"type": "gathering", "dispute_id": dispute_id}

        try:
            case_file = await self._source.get_case_file(dispute_id)
        except Exception as e:  # noqa: BLE001
            logger.error("Gather failed", extra={"event": "mediation.gather_error", "dispute": dispute_id, "error": str(e)}, exc_info=True)
            yield {"type": "error", "error": f"Could not gather the dispute: {e}"}
            return

        source = "fixture" if str(dispute_id).startswith("FIXTURE-") else "paypal"
        dispute = await self._disputes.record_from_case_file(case_file, seller_id=seller_id, source=source)
        yield {"type": "gathered", "dispute_id": dispute_id, "case_file": dict(case_file)}

        policy = await self._policies.get_for_seller(seller_id) if seller_id else None
        policy_text = policy.get("rules_text", "") if policy else ""
        guardrails = self._policies.as_guardrail_dict(policy)

        agent = self._mediator_factory()
        decision: Decision | None = None
        async for ev in agent.mediate_stream(case_file, policy_text):
            if ev.get("type") == "decision":
                decision = ev["decision"]  # pre-gate; held back until the executor gates it
                continue
            yield ev

        if decision is None:
            decision = Decision(dispute_id=dispute_id, outcome=None, confidence=0.0, rationale="No decision produced.", gate="escalate")

        # Gate + act (no DB txn held across the PayPal call).
        result = await self._executor.execute(case_file, decision, guardrails)
        gated: Decision = result["decision"]

        yield {"type": "decision", "decision": dict(gated)}

        if result.get("gate") == GateDecision.ESCALATE.value:
            yield {"type": "escalated", "recommendation": gated.get("escalation_recommendation"), "gate_reason": result.get("gate_reason"), "decision": dict(gated)}
            status = "escalated"
        else:
            yield {"type": "executed", "result": {k: v for k, v in result.items() if k != "decision"}, "decision": dict(gated)}
            status = "resolved"

        # Persist audit + resolve (short transactions).
        await self._audit.record(
            dispute_id=dispute["id"],
            paypal_dispute_id=dispute_id,
            case_file=dict(case_file),
            decision=dict(gated),
            result=result,
            engine=agent.engine,
            served_by=getattr(agent.llm, "last_served_by", None),
        )
        await self._disputes.mark_resolved(
            dispute["id"],
            status=status,
            outcome=gated.get("outcome"),
            refund_amount=gated.get("refund_amount"),
            confidence=gated.get("confidence"),
        )

        yield {"type": "explained", "rationale": gated.get("rationale", ""), "action_taken": result.get("action_taken", ""), "decision": dict(gated)}
