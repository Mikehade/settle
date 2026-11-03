"""
MediatorAgent — the brain that decides a dispute.

Two engines, one decision mechanism:

  * graph=False (native LLM + tools): streams the model narrating the
    fixed chain token-by-token via `stream_agentic`, then the single
    proposal tool call the model makes becomes the decision.
  * graph=True (LangGraph): runs classify → weigh → policy → choose as
    explicit graph nodes (BaseGraphAgent), emitting one reasoning step
    per node; the `choose` node makes the proposal.

Either way the agent only ever *proposes* (via ProposalTools). The
MediationService hands the proposal to the executor, which gates it and
performs or escalates it. The agent never imports infrastructure.
"""
from collections.abc import AsyncGenerator
from datetime import date
from typing import Any

from src.domain.core.agents.base import AgentResult, BaseAgent
from src.domain.core.agents.graph_base import BaseGraphAgent, Node
from src.domain.core.constants.dispute_types import DisputeType
from src.domain.core.prompts.mediator import MediatorPrompt
from src.domain.core.tools.base import ToolRegistry
from src.domain.core.tools.evidence_tools import EvidenceTools
from src.domain.core.tools.propose_tools import ProposalTools
from src.domain.entities.case_file import CaseFile
from src.domain.entities.decision import Decision
from src.domain.interfaces.services import LLMModelInterface
from src.shared.logging import get_logger

logger = get_logger(__name__)


def _case_file_json(case_file: CaseFile) -> str:
    import json

    return json.dumps(case_file, indent=2, default=str)


def _fallback_decision(case_file: CaseFile, reason: str) -> Decision:
    return Decision(
        dispute_id=case_file.get("dispute_id", ""),
        outcome=None,
        refund_amount=None,
        confidence=0.0,
        rationale="The mediator could not reach a confident decision, so this dispute is being referred to the seller.",
        classification=case_file.get("dispute_type", DisputeType.UNAUTHORIZED_OR_OTHER.value),
        dispute_type=case_file.get("dispute_type", DisputeType.UNAUTHORIZED_OR_OTHER.value),
        evidence_summary=reason,
        policy_application="",
        escalation_recommendation="Review this dispute manually and respond in the PayPal Resolution Center.",
    )


class MediatorAgent(BaseAgent, BaseGraphAgent):
    def __init__(
        self,
        llm_model: LLMModelInterface,
        proposal_tools: ProposalTools,
        evidence_tools: EvidenceTools,
        graph: bool = False,
    ) -> None:
        self.proposal_tools = proposal_tools
        self.evidence_tools = evidence_tools
        registry = ToolRegistry([proposal_tools, evidence_tools])
        self.prompt = MediatorPrompt()
        BaseAgent.__init__(
            self,
            llm_model=llm_model,
            system_prompt="",  # built per case
            agent_type="mediator",
            tool_registry=registry,
            graph=graph,
        )
        BaseGraphAgent.__init__(self)

    @property
    def engine(self) -> str:
        return "langgraph" if self.graph else "llm_tools"

    def _begin(self, case_file: CaseFile) -> None:
        self.proposal_tools.begin_case(case_file.get("dispute_id", ""))
        self.evidence_tools.begin_case(dict(case_file))

    def _system(self, case_file: CaseFile, policy_text: str) -> str:
        return self.prompt.get_system_prompt(
            case_file=dict(case_file),
            policy_text=policy_text,
            current_date=date.today().isoformat(),
        )

    # ---- BaseAgent contract -----------------------------------------------
    async def process_message(self, *args: Any, **kwargs: Any) -> AgentResult:
        case_file: CaseFile = kwargs["case_file"]
        policy_text: str = kwargs.get("policy_text", "")
        decision = await self.mediate(case_file, policy_text)
        return AgentResult(text=decision.get("rationale", ""), data=dict(decision))

    # ---- Non-streaming decision (used by tests and as the fallback) -------
    async def mediate(self, case_file: CaseFile, policy_text: str = "") -> Decision:
        self._begin(case_file)
        result = await self.generate_llm_response(
            text="Mediate this dispute now. Reason through the chain, then call exactly one proposal tool.",
            system_prompt=self._system(case_file, policy_text),
            enable_tools=True,
            reasoning=True,
        )
        decision = self.proposal_tools.proposal
        if not decision:
            logger.warning("No proposal recorded — escalating", extra={"event": "mediator.no_proposal", "dispute": case_file.get("dispute_id")})
            decision = _fallback_decision(case_file, "No proposal tool was called.")
        decision["dispute_id"] = case_file.get("dispute_id", "")
        if not decision.get("dispute_type"):
            decision["dispute_type"] = case_file.get("dispute_type", DisputeType.UNAUTHORIZED_OR_OTHER.value)
        if not decision.get("rationale") and result.text:
            decision["rationale"] = result.text
        return decision

    # ---- Streaming (the live reasoning trace) ------------------------------
    async def mediate_stream(self, case_file: CaseFile, policy_text: str = "") -> AsyncGenerator[dict, None]:
        if self.graph:
            async for ev in self._mediate_stream_graph(case_file, policy_text):
                yield ev
        else:
            async for ev in self._mediate_stream_native(case_file, policy_text):
                yield ev

    async def _mediate_stream_native(self, case_file: CaseFile, policy_text: str) -> AsyncGenerator[dict, None]:
        self._begin(case_file)
        system = self._system(case_file, policy_text)
        try:
            async for event in self.stream_turn(
                text="Mediate this dispute now. Reason through the chain out loud, then call exactly one proposal tool.",
                system_prompt=system,
            ):
                t = event.get("type")
                if t == "token":
                    yield {"type": "token", "text": event["text"]}
                elif t == "tool_call":
                    yield {"type": "tool_call", "name": event.get("name"), "input": event.get("input", {})}
                elif t == "tool_result":
                    yield {"type": "tool_result", "name": event.get("name"), "ok": event.get("ok", True)}
        except Exception as e:  # noqa: BLE001
            logger.error("Native mediation stream failed", extra={"event": "mediator.stream_error", "error": str(e)}, exc_info=True)
            yield {"type": "error", "error": str(e)}

        decision = self.proposal_tools.proposal or _fallback_decision(case_file, "No proposal tool was called.")
        decision["dispute_id"] = case_file.get("dispute_id", "")
        if not decision.get("dispute_type"):
            decision["dispute_type"] = case_file.get("dispute_type", DisputeType.UNAUTHORIZED_OR_OTHER.value)
        # Replay the chain as discrete steps for the UI, sourced from the decision.
        for stage, text in (
            ("classify", decision.get("classification") or decision.get("dispute_type", "")),
            ("weigh", decision.get("evidence_summary", "")),
            ("policy", decision.get("policy_application", "")),
            ("choose", f"{decision.get('outcome') or 'escalate'} (confidence {decision.get('confidence', 0):.2f})"),
        ):
            if text:
                yield {"type": "reasoning_step", "stage": stage, "text": text}
        yield {"type": "decision", "decision": dict(decision)}

    async def _mediate_stream_graph(self, case_file: CaseFile, policy_text: str) -> AsyncGenerator[dict, None]:
        self._begin(case_file)
        initial = {"case_file": dict(case_file), "policy_text": policy_text, "cfj": _case_file_json(case_file)}
        _stage_of = {"classify": "classify", "weigh": "weigh", "policy": "policy", "choose": "choose"}
        try:
            async for node_name, state in self.astream_nodes(initial):
                stage = _stage_of.get(node_name)
                if stage == "classify":
                    yield {"type": "reasoning_step", "stage": "classify", "text": state.get("classification", "")}
                elif stage == "weigh":
                    yield {"type": "reasoning_step", "stage": "weigh", "text": state.get("evidence_summary", "")}
                elif stage == "policy":
                    yield {"type": "reasoning_step", "stage": "policy", "text": state.get("policy_application", "")}
                elif stage == "choose":
                    decision = state.get("decision") or _fallback_decision(case_file, "No proposal tool was called.")
                    yield {"type": "reasoning_step", "stage": "choose", "text": f"{decision.get('outcome') or 'escalate'} (confidence {decision.get('confidence', 0):.2f})"}
                    yield {"type": "decision", "decision": dict(decision)}
        except Exception as e:  # noqa: BLE001
            logger.error("Graph mediation stream failed", extra={"event": "mediator.graph_error", "error": str(e)}, exc_info=True)
            yield {"type": "error", "error": str(e)}
            yield {"type": "decision", "decision": dict(_fallback_decision(case_file, str(e)))}

    # ---- LangGraph nodes ---------------------------------------------------
    def nodes(self) -> list[tuple[str, Node]]:
        return [
            ("classify", self._node_classify),
            ("weigh", self._node_weigh),
            ("policy", self._node_policy),
            ("choose", self._node_choose),
        ]

    async def _node_classify(self, state: dict) -> dict:
        r = await self.generate_llm_response(
            text=self.prompt.classify_prompt(state["cfj"]), system_prompt="You are a precise dispute classifier.",
            enable_tools=False, reasoning=False,
        )
        return {"classification": r.text}

    async def _node_weigh(self, state: dict) -> dict:
        r = await self.generate_llm_response(
            text=self.prompt.weigh_prompt(state["cfj"]), system_prompt="You weigh dispute evidence objectively.",
            enable_tools=False, reasoning=False,
        )
        return {"evidence_summary": r.text}

    async def _node_policy(self, state: dict) -> dict:
        r = await self.generate_llm_response(
            text=self.prompt.policy_prompt(state["policy_text"], state["cfj"]),
            system_prompt="You apply a seller's fairness policy faithfully.", enable_tools=False, reasoning=False,
        )
        return {"policy_application": r.text}

    async def _node_choose(self, state: dict) -> dict:
        case_file: CaseFile = state["case_file"]  # type: ignore[assignment]
        decision = await self.mediate(case_file, state["policy_text"])
        # Enrich with the per-node reasoning already produced.
        decision.setdefault("classification", state.get("classification", ""))
        if state.get("evidence_summary"):
            decision["evidence_summary"] = decision.get("evidence_summary") or state["evidence_summary"]
        if state.get("policy_application"):
            decision["policy_application"] = decision.get("policy_application") or state["policy_application"]
        return {"decision": decision}
