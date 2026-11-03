"""
LangGraphBedrockModel — adapter the LangGraph engine shares.

It wraps the async `BedrockModel` so LangGraph nodes have an `ainvoke`
that returns assembled text, drawing on the SAME shared fallback chain
(domain/core/constants/model_registry) as the native engine. This keeps
model priority identical across both engines without a second SDK or a
second set of credentials.
"""
from typing import Any

from src.infrastructure.langgraph_models.base import LangGraphModelInterface
from src.infrastructure.language_models.bedrock import BedrockModel


class LangGraphBedrockModel(LangGraphModelInterface):
    def __init__(self, bedrock_model: BedrockModel) -> None:
        self._bedrock = bedrock_model

    async def ainvoke(self, messages: list[dict[str, Any]], system: str | None = None, **kwargs: Any) -> dict[str, Any]:
        response = await self._bedrock.invoke_with_fallback(messages=messages, system=system, enable_tools=False, **kwargs)
        text = self._bedrock.extract_text_response(response)
        return {"text": text, "raw": response, "served_by": self._bedrock.last_served_by}
