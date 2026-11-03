"""
LangGraph-side model base.

Settle's LangGraph engine (MediatorAgent with graph=True) drives the same
`BedrockModel` its nodes call through the injected LLMModelInterface — it
does NOT introduce a second LLM SDK. This module exists so the model
registry's "consumed by LangGraphBedrockModel" contract has a home and so
a project that wants a true LangChain chat-model binding has one obvious
place to add it (e.g. wrapping `langchain_aws.ChatBedrockConverse`),
reusing DEFAULT_BEDROCK_FALLBACK_CHAIN for parity.
"""
from typing import Any, Protocol


class LangGraphModelInterface(Protocol):
    async def ainvoke(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]: ...
