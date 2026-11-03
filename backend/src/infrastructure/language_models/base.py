"""
Base LLM model: shared helpers every provider implementation inherits.

Concrete providers (BedrockModel) implement invoke()/prompt()/the stream
methods. This base holds the provider-neutral bits the agents rely on:
template rendering, message-history hygiene, and text/token extraction
from a Bedrock-shaped response dict.
"""
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Any

from src.shared.logging import get_logger

logger = get_logger(__name__)


class BaseLLMModel(ABC):
    def __init__(
        self,
        model_id: str,
        temperature: float = 0.7,
        max_tokens: int = 8192,
        timezone_str: str = "UTC",
        tool_registry: Any = None,
        **kwargs: Any,
    ) -> None:
        self.model_id = model_id
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timezone_str = timezone_str
        self.tool_registry = tool_registry

    # ---- Shared helpers ----------------------------------------------------
    def render_template(self, template: str, context: dict[str, Any] | None = None) -> str:
        """Render a system-prompt template. Agents usually pass a fully
        rendered prompt and an empty context, in which case the template is
        returned unchanged; a KeyError from a stray brace degrades to the
        raw template rather than raising."""
        if not context:
            return template
        try:
            return template.format(**context)
        except (KeyError, IndexError, ValueError):
            return template

    def clean_message_history(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Drop empty-content turns and collapse consecutive same-role turns
        so Bedrock's strict user/assistant alternation is never violated."""
        cleaned: list[dict[str, Any]] = []
        for msg in messages:
            content = msg.get("content")
            if not content:
                continue
            if cleaned and cleaned[-1]["role"] == msg["role"]:
                cleaned[-1]["content"].extend(content if isinstance(content, list) else [{"text": str(content)}])
                continue
            cleaned.append({"role": msg["role"], "content": content if isinstance(content, list) else [{"text": str(content)}]})
        return cleaned

    def extract_text_from_llm_response(
        self, response: dict[str, Any], with_tokens: bool = True, llm_type: str = "bedrock"
    ) -> tuple[str, dict[str, int]]:
        """Pull assistant text + token usage out of a Bedrock-shaped response."""
        text = ""
        try:
            blocks = response.get("output", {}).get("message", {}).get("content", [])
            text = "\n".join(b["text"] for b in blocks if "text" in b).strip()
        except (KeyError, TypeError):
            text = ""
        tokens = {
            "total_tokens": response.get("totalTokens", response.get("usage", {}).get("totalTokens", 0)),
            "tool_tokens": response.get("toolTokens", 0),
            "tool_count": response.get("toolCallCount", 0),
        }
        return (text, tokens) if with_tokens else (text, {})

    # ---- Provider contract -------------------------------------------------
    @abstractmethod
    async def prompt(self, *args: Any, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        """High-level: render system prompt, run tool loop, yield the final response dict."""
        ...
