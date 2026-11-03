"""MediatorAgent tested with a fake LLM (no AWS). The fake simulates the
model calling exactly one proposal tool, so these assert the agent +
tool-registry wiring, the native and LangGraph engines, and the
escalate-on-no-proposal fallback — all offline."""
from typing import Any

import pytest

from src.domain.core.agents.mediator import MediatorAgent
from src.domain.core.constants.outcomes import Outcome
from src.domain.core.tools.evidence_tools import EvidenceTools
from src.domain.core.tools.propose_tools import ProposalTools
from src.domain.entities.case_file import CaseFile


class FakeLLM:
    """Executes a preset proposal tool when tools are enabled; returns text otherwise."""

    def __init__(self, tool_name: str | None, tool_input: dict[str, Any] | None, text: str = "reasoned") -> None:
        self.tool_registry = None
        self.last_served_by = "fake-model"
        self._tool_name = tool_name
        self._tool_input = tool_input or {}
        self._text = text

    def render_template(self, template: str, context: dict | None = None) -> str:
        return template

    def extract_text_from_llm_response(self, response: dict, with_tokens: bool = True, llm_type: str = "bedrock"):
        return response.get("_text", self._text), {"total_tokens": 1, "tool_tokens": 0, "tool_count": 0}

    async def prompt(self, *, text=None, system_prompt=None, message_history=None, enable_tools=False, model_id=None, reasoning=False, **kwargs):
        if enable_tools and self.tool_registry and self._tool_name:
            await self.tool_registry.execute_tool(self._tool_name, self._tool_input)
        yield {"_text": self._text, "servedByModel": self.last_served_by}

    async def stream_agentic(self, *, messages=None, system=None, tool_registry=None, **kwargs):
        yield {"type": "token", "text": self._text}
        registry = tool_registry or self.tool_registry
        if registry and self._tool_name:
            await registry.execute_tool(self._tool_name, self._tool_input)
            yield {"type": "tool_call", "name": self._tool_name, "input": self._tool_input}
            yield {"type": "tool_result", "name": self._tool_name, "ok": True}
        yield {"type": "done", "total_tokens": 1}


def _case() -> CaseFile:
    return CaseFile(dispute_id="FIXTURE-NR-001", dispute_type="not_received", disputed_amount=59.99, currency="USD", capture_id=None, prior_refunds=0.0)


def _agent(llm: FakeLLM, graph: bool = False) -> MediatorAgent:
    return MediatorAgent(llm_model=llm, proposal_tools=ProposalTools(), evidence_tools=EvidenceTools(), graph=graph)


async def test_native_refund_proposal_recorded():
    llm = FakeLLM("propose_refund", {"amount": 59.99, "confidence": 0.92, "rationale": "tracking shows never shipped", "dispute_type": "not_received"})
    decision = await _agent(llm).mediate(_case(), policy_text="Refund if not shipped.")
    assert decision["outcome"] == Outcome.REFUND.value
    assert decision["refund_amount"] == pytest.approx(59.99)
    assert decision["confidence"] == pytest.approx(0.92)
    assert decision["dispute_id"] == "FIXTURE-NR-001"


async def test_no_proposal_falls_back_to_escalate():
    llm = FakeLLM(None, None)  # model called no tool
    decision = await _agent(llm).mediate(_case(), policy_text="")
    assert decision["outcome"] is None
    assert decision["confidence"] == 0.0
    assert decision["escalation_recommendation"]


async def test_graph_engine_runs_chain_and_decides():
    llm = FakeLLM("propose_accept", {"confidence": 0.88, "rationale": "clear buyer win", "dispute_type": "not_received"})
    agent = _agent(llm, graph=True)
    assert agent.engine == "langgraph"
    decision = await agent.mediate(_case(), policy_text="")
    assert decision["outcome"] == Outcome.ACCEPT.value


async def test_native_stream_emits_reasoning_and_decision():
    llm = FakeLLM("propose_refund", {"amount": 30.0, "confidence": 0.9, "rationale": "r", "dispute_type": "not_as_described"})
    events = [ev async for ev in _agent(llm).mediate_stream(_case(), policy_text="")]
    types = [e["type"] for e in events]
    assert "token" in types
    assert "decision" in types
    decision = next(e["decision"] for e in events if e["type"] == "decision")
    assert decision["outcome"] == Outcome.REFUND.value
