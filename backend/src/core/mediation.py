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

Money safety lives here, not in the prompt:
  * every event carries its `dispute_id`, so overlapping runs on one
    seller's channel never blur together;
  * a case is *claimed* (open/escalated/failed → mediating) atomically
    before any reasoning, so two runs of the same case can't both act;
  * approve/reject are ownership-checked and state-checked, so a case
    can't be executed twice or acted on by someone who doesn't own it;
  * any failure sets the dispute to `failed` and ends the run — no case
    is left stuck on `mediating`.
"""
import asyncio
import uuid
from collections import defaultdict
from collections.abc import AsyncGenerator, Callable
from typing import Any

from src.core.audit import AuditService
from src.core.disputes import DisputeService
from src.core.policy import FairnessPolicyService
from src.domain.core.agents.mediator import MediatorAgent
from src.domain.core.constants.outcomes import GateDecision
from src.domain.core.constants.statuses import DisputeStatus
from src.domain.entities.decision import Decision
from src.domain.exceptions import BusinessRuleError, ConflictError
from src.domain.interfaces.services import DisputeSourceInterface, PayPalExecutorInterface
from src.shared.errors import ErrorCode
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
        # Per-dispute in-process locks: belt-and-suspenders over the DB claim
        # for the common single-worker deployment.
        self._locks: dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)

    def _lock_for(self, dispute_id: str) -> asyncio.Lock:
        return self._locks[str(dispute_id)]

    # ---- Open list ---------------------------------------------------------
    async def list_open(self, *, seller_id: uuid.UUID | None = None) -> list[dict[str, Any]]:
        """Open disputes from the source, reconciled against this seller's DB rows
        so a case that's already been mediated reflects its real status (not a
        hardcoded "open"), and carries amount/item/date for the list view."""
        summaries = await self._source.list_open()
        out: list[dict[str, Any]] = []
        for s in summaries:
            row = dict(s)
            persisted = await self._disputes.find_by_paypal(str(s.get("dispute_id")))
            # Only overlay the seller's own view; another seller's progress on a
            # shared fixture must not leak into this seller's list.
            if persisted and (seller_id is None or persisted.get("seller_id") == seller_id):
                row["status"] = persisted.get("status", row.get("status"))
                row["disputed_amount"] = persisted.get("disputed_amount", row.get("amount"))
                row["currency"] = persisted.get("currency", row.get("currency"))
                row["dispute_type"] = persisted.get("dispute_type", row.get("dispute_type"))
                row["updated_at"] = persisted.get("updated_at")
                row["resolved_at"] = persisted.get("resolved_at")
            out.append(row)
        return out

    async def preview(self, paypal_dispute_id: str, *, seller_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Assemble and return a case file WITHOUT running mediation, so the detail
        page for a case that hasn't run yet isn't nearly empty. Includes the
        persisted status when the case has been seen before."""
        case_file = await self._source.get_case_file(paypal_dispute_id)
        persisted = await self._disputes.find_by_paypal(paypal_dispute_id)
        status = DisputeStatus.OPEN.value
        if persisted and (seller_id is None or persisted.get("seller_id") == seller_id):
            status = persisted.get("status", status)
        return {"dispute_id": paypal_dispute_id, "status": status, "case_file": dict(case_file)}

    # ---- REST summary ------------------------------------------------------
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

    # ---- Approve / reject (money-moving; the human is the gate) ------------
    async def approve(self, paypal_dispute_id: str, *, seller_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Seller approved an escalated recommendation — perform it now.

        Guards: the caller must own the case; the case must actually be waiting
        on the seller (status `escalated`); and the latest decision must be an
        un-executed escalation. This is what stops a second approve from
        refunding twice."""
        if not paypal_dispute_id:
            raise BusinessRuleError(ErrorCode.COMMON_BAD_REQUEST, "dispute_id is required")
        async with self._lock_for(paypal_dispute_id):
            dispute = await self._disputes.get_by_paypal(paypal_dispute_id, seller_id=seller_id)
            self._assert_actionable(dispute)

            entries = await self._audit.list_for_dispute(dispute["id"], seller_id=seller_id)
            if not entries:
                raise BusinessRuleError(ErrorCode.COMMON_BAD_REQUEST, "No prior decision to approve.")
            latest = entries[0]
            if latest.get("executed") or latest.get("gate") != GateDecision.ESCALATE.value:
                raise ConflictError(ErrorCode.DISPUTE_ALREADY_RESOLVED, "This case has already been acted on.")

            decision: Decision = latest["decision"]  # type: ignore[assignment]
            case_file = latest["case_file"]

            if not decision.get("outcome"):
                await self._disputes.set_status(dispute["id"], status=DisputeStatus.RESOLVED.value, outcome=None, refund_amount=None, confidence=decision.get("confidence"))
                return {"dispute_id": paypal_dispute_id, "result": {"executed": False, "action_taken": "Acknowledged — resolve manually in PayPal."}, "decision": dict(decision)}

            result = await self._executor.execute(case_file, decision, None, approved=True)
            gated = result["decision"]
            await self._audit.record(
                dispute_id=dispute["id"], paypal_dispute_id=paypal_dispute_id, case_file=case_file,
                decision=dict(gated), result=result, engine="approved", served_by=None, seller_id=dispute.get("seller_id"),
            )
            await self._disputes.set_status(dispute["id"], status=DisputeStatus.RESOLVED.value, outcome=gated.get("outcome"), refund_amount=gated.get("refund_amount"), confidence=gated.get("confidence"))
            return {
                "dispute_id": paypal_dispute_id,
                "result": {k: v for k, v in result.items() if k != "decision"},
                "decision": dict(gated),
            }

    async def reject(self, paypal_dispute_id: str, *, seller_id: uuid.UUID | None = None) -> dict[str, Any]:
        """Seller rejected the recommendation — mark it rejected (terminal,
        distinct from a case still awaiting the seller)."""
        if not paypal_dispute_id:
            raise BusinessRuleError(ErrorCode.COMMON_BAD_REQUEST, "dispute_id is required")
        async with self._lock_for(paypal_dispute_id):
            dispute = await self._disputes.get_by_paypal(paypal_dispute_id, seller_id=seller_id)
            self._assert_actionable(dispute)

            entries = await self._audit.list_for_dispute(dispute["id"], seller_id=seller_id)
            decision = dict(entries[0]["decision"]) if entries else {}
            await self._disputes.set_status(dispute["id"], status=DisputeStatus.REJECTED.value, outcome=None, refund_amount=None, confidence=None)
            return {
                "dispute_id": paypal_dispute_id,
                "rationale": "The seller declined the recommendation; this dispute is left for manual handling.",
                "action_taken": "Recommendation rejected — left for manual handling.",
                "decision": decision,
            }

    @staticmethod
    def _assert_actionable(dispute: dict[str, Any]) -> None:
        status = dispute.get("status")
        if status in (DisputeStatus.RESOLVED.value, DisputeStatus.REJECTED.value):
            raise ConflictError(ErrorCode.DISPUTE_ALREADY_RESOLVED, "This dispute has already been resolved.")
        if status != DisputeStatus.ESCALATED.value:
            raise ConflictError(ErrorCode.DISPUTE_ALREADY_RESOLVED, "This dispute is not awaiting seller approval.")

    # ---- Streaming run -----------------------------------------------------
    async def mediate_stream(self, dispute_id: str, *, seller_id: uuid.UUID | None = None, force_escalate: bool = False) -> AsyncGenerator[dict, None]:
        """Drive one mediation, yielding dispute_id-stamped events.

        `force_escalate` (autonomous/unattributed webhook) never lets money move
        automatically — the case is escalated for seller confirmation regardless
        of the guardrails."""
        async with self._lock_for(dispute_id):
            async for ev in self._run(dispute_id, seller_id=seller_id, force_escalate=force_escalate):
                yield ev

    async def _run(self, dispute_id: str, *, seller_id: uuid.UUID | None, force_escalate: bool) -> AsyncGenerator[dict, None]:
        yield {"type": "detected", "dispute_id": dispute_id}
        yield {"type": "gathering", "dispute_id": dispute_id}

        try:
            case_file = await self._source.get_case_file(dispute_id)
        except Exception as e:  # noqa: BLE001
            logger.error("Gather failed", extra={"event": "mediation.gather_error", "dispute": dispute_id, "error": str(e)}, exc_info=True)
            yield {"type": "error", "dispute_id": dispute_id, "error": f"Could not gather the dispute: {e}"}
            return

        source = "fixture" if str(dispute_id).startswith("FIXTURE-") else "paypal"
        dispute = await self._disputes.record_from_case_file(case_file, seller_id=seller_id, source=source, claim=True)
        if dispute is None:
            # Already mediating / resolved / rejected — don't start a second run.
            raise ConflictError(ErrorCode.DISPUTE_ALREADY_RESOLVED, "This dispute is already being mediated or has been resolved.")

        yield {"type": "gathered", "dispute_id": dispute_id, "case_file": dict(case_file)}

        try:
            policy = await self._policies.get_for_seller(seller_id) if seller_id else None
            policy_text = policy.get("rules_text", "") if policy else ""
            guardrails = self._policies.as_guardrail_dict(policy)

            agent = self._mediator_factory()
            decision: Decision | None = None
            async for ev in agent.mediate_stream(case_file, policy_text):
                etype = ev.get("type")
                if etype == "error":
                    # An error ends the run: no decision follows, status → failed.
                    await self._disputes.set_status(dispute["id"], status=DisputeStatus.FAILED.value, outcome=None, refund_amount=None, confidence=None)
                    yield {"type": "error", "dispute_id": dispute_id, "error": ev.get("error", "Mediation failed")}
                    return
                if etype == "decision":
                    decision = ev["decision"]  # pre-gate; held back until the executor gates it
                    continue
                yield {**ev, "dispute_id": dispute_id}

            if decision is None:
                decision = Decision(dispute_id=dispute_id, outcome=None, confidence=0.0, rationale="No decision produced.", gate="escalate")

            # Gate + act (no DB txn held across the PayPal call).
            if force_escalate:
                decision["gate"] = GateDecision.ESCALATE.value
                decision["gate_reason"] = "Unattributed webhook — seller confirmation required before any action."
                decision.setdefault("escalation_recommendation", "Review this autonomous case and approve to proceed.")
                result = {
                    "executed": False, "gate": GateDecision.ESCALATE.value, "gate_reason": decision["gate_reason"],
                    "action_taken": "Escalated — unattributed webhook", "paypal_result": {"escalated": True}, "decision": dict(decision),
                }
            else:
                result = await self._executor.execute(case_file, decision, guardrails)
            gated: Decision = result["decision"]

            yield {"type": "decision", "dispute_id": dispute_id, "decision": dict(gated)}

            if result.get("gate") == GateDecision.ESCALATE.value:
                yield {"type": "escalated", "dispute_id": dispute_id, "recommendation": gated.get("escalation_recommendation"), "gate_reason": result.get("gate_reason"), "decision": dict(gated)}
                status = DisputeStatus.ESCALATED.value
            else:
                yield {"type": "executed", "dispute_id": dispute_id, "result": {k: v for k, v in result.items() if k != "decision"}, "decision": dict(gated)}
                status = DisputeStatus.RESOLVED.value

            # Persist audit + status (short transactions).
            await self._audit.record(
                dispute_id=dispute["id"],
                paypal_dispute_id=dispute_id,
                case_file=dict(case_file),
                decision=dict(gated),
                result=result,
                engine=agent.engine,
                served_by=getattr(agent.llm, "last_served_by", None),
                seller_id=dispute.get("seller_id"),
            )
            await self._disputes.set_status(
                dispute["id"],
                status=status,
                outcome=gated.get("outcome"),
                refund_amount=gated.get("refund_amount"),
                confidence=gated.get("confidence"),
            )

            yield {"type": "explained", "dispute_id": dispute_id, "rationale": gated.get("rationale", ""), "action_taken": result.get("action_taken", ""), "decision": dict(gated)}
        except Exception as e:  # noqa: BLE001
            # Anything after the claim failing leaves the case stuck on `mediating`
            # unless we move it to `failed` and end the run with a terminal error.
            logger.error("Mediation run failed", extra={"event": "mediation.run_error", "dispute": dispute_id, "error": str(e)}, exc_info=True)
            try:
                await self._disputes.set_status(dispute["id"], status=DisputeStatus.FAILED.value, outcome=None, refund_amount=None, confidence=None)
            except Exception:  # noqa: BLE001
                logger.error("Could not mark dispute failed", extra={"event": "mediation.fail_mark_error", "dispute": dispute_id}, exc_info=True)
            yield {"type": "error", "dispute_id": dispute_id, "error": f"Mediation failed: {e}"}
