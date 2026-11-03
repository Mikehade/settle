"""
Base agent (LLM + tools).

`BaseAgent` is the native engine: it drives a Bedrock model directly
through the `ToolRegistry`, with a non-streaming helper
(`generate_llm_response`) and a streaming helper (`stream_turn`) that
surfaces token / tool_call / tool_result events for the UI.

Agents depend ONLY on an injected LLM model (typed against
LLMModelInterface) and a ToolRegistry. They never import infrastructure,
so `src.domain.core` stays a clean domain package.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any

from src.domain.interfaces.services import LLMModelInterface
from src.shared.logging import get_logger

logger = get_logger(__name__)

DEFAULT_LLM_MAX_ATTEMPTS = 3


@dataclass
class AgentResult:
    text: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    sources: list[dict[str, Any]] = field(default_factory=list)
    total_tokens: int = 0
    tool_tokens: int = 0
    tool_count: int = 0
    served_by: str | None = None


class BaseAgent(ABC):
    def __init__(
        self,
        llm_model: LLMModelInterface,
        system_prompt: str,
        agent_type: str,
        tool_registry: Any = None,
        graph: bool = False,
        **kwargs: Any,
    ) -> None:
        self.llm = llm_model
        self.system_prompt = system_prompt
        self.agent_type = agent_type
        self.tool_registry = tool_registry
        self.graph = graph
        if tool_registry is not None:
            # Give this agent's model its tool registry (native tool loop).
            self.llm.tool_registry = tool_registry

    # ---- Non-streaming turn ------------------------------------------------
    async def generate_llm_response(
        self,
        *,
        text: str,
        system_prompt: str | None = None,
        message_history: list[dict[str, Any]] | None = None,
        enable_tools: bool = True,
        model_id: str | None = None,
        reasoning: bool = True,
        max_attempts: int = DEFAULT_LLM_MAX_ATTEMPTS,
    ) -> AgentResult:
        """Run one turn, retrying on empty output. Returns an AgentResult."""
        last_response: dict[str, Any] | None = None
        for attempt in range(1, max_attempts + 1):
            response = None
            async for chunk in self.llm.prompt(
                text=text,
                system_prompt=system_prompt or self.system_prompt,
                message_history=message_history or [],
                enable_tools=enable_tools,
                model_id=model_id,
                reasoning=reasoning,
            ):
                response = chunk
            if not response:
                logger.warning("Empty LLM response", extra={"event": "agent.empty", "attempt": attempt})
                continue
            last_response = response
            response_text, tokens = self.llm.extract_text_from_llm_response(response, True, "bedrock")
            if response_text.strip():
                return AgentResult(
                    text=response_text,
                    total_tokens=tokens.get("total_tokens", 0),
                    tool_tokens=tokens.get("tool_tokens", 0),
                    tool_count=tokens.get("tool_count", 0),
                    served_by=response.get("servedByModel"),
                )
            logger.warning("Empty LLM text", extra={"event": "agent.empty_text", "attempt": attempt})
        # Exhausted — return whatever we have (possibly empty) rather than raise,
        # so the caller can decide (the mediator escalates on an empty decision).
        text_out, tokens = self.llm.extract_text_from_llm_response(last_response or {}, True, "bedrock")
        return AgentResult(text=text_out, total_tokens=tokens.get("total_tokens", 0))

    # ---- Streaming turn ----------------------------------------------------
    async def stream_turn(
        self,
        *,
        text: str,
        system_prompt: str | None = None,
        message_history: list[dict[str, Any]] | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a tool-using turn. Yields the raw model events
        (token / tool_call / tool_result / done). Subclasses translate
        these into their own domain events."""
        system = self.llm.render_template(system_prompt or self.system_prompt, {})
        messages = list(message_history or []) + [{"role": "user", "content": [{"text": text}]}]
        async for event in self.llm.stream_agentic(messages=messages, system=system, tool_registry=self.tool_registry):
            yield event

    # ---- Contract ----------------------------------------------------------
    @abstractmethod
    async def process_message(self, *args: Any, **kwargs: Any) -> AgentResult:
        ...
