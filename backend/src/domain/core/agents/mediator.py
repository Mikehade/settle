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


class _StageSplitter:
    """Parses the model's live narration into stages as it streams.

    The native engine narrates the fixed chain with explicit markers
    (`<<<CLASSIFY>>>` …). This turns that single token stream into live
    `reasoning_step` + `token` events: tokens carry the active `stage`, and a
    `reasoning_step` is emitted the moment a stage completes (when the next
    marker arrives, and the last at flush). Split markers across token
    boundaries are handled by holding back a short tail; markers themselves are
    stripped from the emitted text. If the model never emits markers, nothing is
    produced here and the caller falls back to reconstructing steps from the
    finished decision — so behaviour never regresses.
    """

    MARKERS: tuple[tuple[str, str], ...] = (
        ("<<<CLASSIFY>>>", "classify"),
        ("<<<WEIGH>>>", "weigh"),
        ("<<<POLICY>>>", "policy"),
        ("<<<CHOOSE>>>", "choose"),
    )
    _MAX_MARKER = max(len(m) for m, _ in MARKERS)

    def __init__(self) -> None:
        self._buf = ""
        self._stage: str | None = None
        self._texts: dict[str, str] = {}
        self.seen: list[str] = []

    def _emit_text(self, text: str) -> list[dict]:
        if not text:
            return []
        if self._stage is not None:
            self._texts[self._stage] = self._texts.get(self._stage, "") + text
        return [{"type": "token", "text": text, "stage": self._stage}]

    def _partial_tail_len(self) -> int:
        """Longest suffix of the buffer that could be the start of a marker."""
        for size in range(min(self._MAX_MARKER - 1, len(self._buf)), 0, -1):
            tail = self._buf[-size:]
            if any(m.startswith(tail) for m, _ in self.MARKERS):
                return size
        return 0

    def feed(self, text: str) -> list[dict]:
        events: list[dict] = []
        self._buf += text
        while True:
            hit_pos: int | None = None
            hit_marker = hit_stage = ""
            for marker, stage in self.MARKERS:
                idx = self._buf.find(marker)
                if idx != -1 and (hit_pos is None or idx < hit_pos):
                    hit_pos, hit_marker, hit_stage = idx, marker, stage
            if hit_pos is None:
                break
            events += self._emit_text(self._buf[:hit_pos])
            if self._stage is not None:  # close the stage that just ended
                events.append({"type": "reasoning_step", "stage": self._stage, "text": self._texts.get(self._stage, "").strip()})
            self._stage = hit_stage
            if hit_stage not in self.seen:
                self.seen.append(hit_stage)
            self._texts.setdefault(hit_stage, "")
            self._buf = self._buf[hit_pos + len(hit_marker):]
        hold = self._partial_tail_len()
        if hold:
            emit_now, self._buf = self._buf[:-hold], self._buf[-hold:]
        else:
            emit_now, self._buf = self._buf, ""
        events += self._emit_text(emit_now)
        return events

    def flush(self) -> list[dict]:
        events = self._emit_text(self._buf)
        self._buf = ""
        if self._stage is not None:
            events.append({"type": "reasoning_step", "stage": self._stage, "text": self._texts.get(self._stage, "").strip()})
        return events


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
        splitter = _StageSplitter()
        try:
            async for event in self.stream_turn(
                text="Mediate this dispute now. Reason through the chain out loud, then call exactly one proposal tool.",
                system_prompt=system,
            ):
                t = event.get("type")
                if t == "token":
                    # Split the narration into live, stage-tagged tokens + per-stage steps.
                    for ev in splitter.feed(event["text"]):
                        yield ev
                elif t == "tool_call":
                    yield {"type": "tool_call", "name": event.get("name"), "input": event.get("input", {})}
                elif t == "tool_result":
                    yield {"type": "tool_result", "name": event.get("name"), "ok": event.get("ok", True)}
        except Exception as e:  # noqa: BLE001
            logger.error("Native mediation stream failed", extra={"event": "mediator.stream_error", "error": str(e)}, exc_info=True)
            # An error ends the run — no decision follows.
            yield {"type": "error", "error": str(e)}
            return

        for ev in splitter.flush():
            yield ev

        decision = self.proposal_tools.proposal or _fallback_decision(case_file, "No proposal tool was called.")
        decision["dispute_id"] = case_file.get("dispute_id", "")
        if not decision.get("dispute_type"):
            decision["dispute_type"] = case_file.get("dispute_type", DisputeType.UNAUTHORIZED_OR_OTHER.value)
        # Fallback: emit any stage the model didn't mark live, from the decision, so
        # the UI always gets all four steps even if the model ignored the markers.
        seen = set(splitter.seen)
        for stage, text in (
            ("classify", decision.get("classification") or decision.get("dispute_type", "")),
            ("weigh", decision.get("evidence_summary", "")),
            ("policy", decision.get("policy_application", "")),
            ("choose", f"{decision.get('outcome') or 'escalate'} (confidence {decision.get('confidence', 0):.2f})"),
        ):
            if stage not in seen and text:
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
