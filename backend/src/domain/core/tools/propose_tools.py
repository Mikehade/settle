"""
Proposal tools — the mediator's entire action surface, and its safety boundary.

The agent can ONLY call these four. None of them moves money or touches
PayPal: each simply records a structured proposal (a Decision) onto the
tool instance. The MediationService then hands that proposal to the
PayPalExecutor (infrastructure), which enforces the guardrails and makes
the real PayPal call. So every money movement passes through code the
team controls — the model merely chooses.
"""
from typing import Any

from src.domain.core.constants.outcomes import Outcome
from src.domain.core.tools.base import BaseTool
from src.domain.entities.decision import Decision
from src.shared.logging import get_logger

logger = get_logger(__name__)

PROPOSAL_TOOL_NAMES = ["propose_refund", "propose_reship", "propose_accept", "escalate_to_seller"]


class ProposalTools(BaseTool):
    """Captures exactly one proposal per case. Call `begin_case()` to reset."""

    def __init__(self, enabled_tools: list | None = None, **kwargs) -> None:
        super().__init__(enabled_tools=enabled_tools or PROPOSAL_TOOL_NAMES, **kwargs)
        self.proposal: Decision | None = None

    def begin_case(self, dispute_id: str) -> None:
        self.proposal = None
        self.kwargs["dispute_id"] = dispute_id

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        method = self.get_tool_method(tool_name)
        if not method:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}
        try:
            return await method(**tool_input)
        except Exception as e:  # noqa: BLE001
            logger.error("Proposal tool error", extra={"event": "proposal.error", "tool": tool_name, "error": str(e)}, exc_info=True)
            return {"success": False, "error": str(e)}

    def _record(self, decision: Decision) -> dict[str, Any]:
        decision["dispute_id"] = self.kwargs.get("dispute_id", "")
        self.proposal = decision
        logger.info("Proposal recorded", extra={"event": "proposal.recorded", "outcome": decision.get("outcome"), "confidence": decision.get("confidence")})
        return {"success": True, "recorded": decision.get("outcome") or "escalate", "confidence": decision.get("confidence")}

    # fmt: off
    async def _propose_refund(
        self,
        amount: float,
        confidence: float,
        rationale: str,
        dispute_type: str = "",
        evidence_summary: str = "",
        policy_application: str = "",
        **kwargs,
    ) -> dict[str, Any]:
        """Propose refunding the buyer (full or partial). Use when the buyer's claim holds up."""
        return self._record(Decision(
            outcome=Outcome.REFUND.value, refund_amount=float(amount), confidence=float(confidence),
            rationale=rationale, dispute_type=dispute_type, evidence_summary=evidence_summary,
            policy_application=policy_application, classification=dispute_type,
        ))

    async def _propose_reship(
        self,
        confidence: float,
        rationale: str,
        dispute_type: str = "",
        evidence_summary: str = "",
        policy_application: str = "",
        **kwargs,
    ) -> dict[str, Any]:
        """Propose a replacement / reshipment instead of money back. Use when the fair fix is a replacement."""
        return self._record(Decision(
            outcome=Outcome.RESHIP.value, refund_amount=None, confidence=float(confidence),
            rationale=rationale, dispute_type=dispute_type, evidence_summary=evidence_summary,
            policy_application=policy_application, classification=dispute_type,
        ))

    async def _propose_accept(
        self,
        confidence: float,
        rationale: str,
        dispute_type: str = "",
        evidence_summary: str = "",
        policy_application: str = "",
        **kwargs,
    ) -> dict[str, Any]:
        """Propose accepting the claim on the seller's behalf. Use when evidence clearly favours the buyer and fighting is pointless."""
        return self._record(Decision(
            outcome=Outcome.ACCEPT.value, refund_amount=None, confidence=float(confidence),
            rationale=rationale, dispute_type=dispute_type, evidence_summary=evidence_summary,
            policy_application=policy_application, classification=dispute_type,
        ))

    async def _escalate_to_seller(
        self,
        recommendation: str,
        confidence: float,
        rationale: str,
        dispute_type: str = "",
        evidence_summary: str = "",
        policy_application: str = "",
        **kwargs,
    ) -> dict[str, Any]:
        """Escalate to the seller with a recommendation and the evidence. Use when the case is unclear, high-value, or policy demands a human."""
        return self._record(Decision(
            outcome=None, refund_amount=None, confidence=float(confidence),
            rationale=rationale, dispute_type=dispute_type, evidence_summary=evidence_summary,
            policy_application=policy_application, classification=dispute_type,
            escalation_recommendation=recommendation,
        ))
    # fmt: on
