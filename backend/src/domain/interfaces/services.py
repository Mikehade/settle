"""Interfaces for infrastructure services that core depends on.

Add one only when core needs to call the thing; infra-to-infra calls do not need one.
"""
from collections.abc import AsyncGenerator
from typing import Any, Protocol

from src.domain.entities.case_file import CaseFile
from src.domain.entities.decision import Decision


class HealthCheck(Protocol):
    """Anything the readiness probe should check (database, cache, broker, ...)."""

    name: str

    async def ping(self) -> bool: ...


class PasswordHasherInterface(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, hashed: str) -> bool: ...


class TokenServiceInterface(Protocol):
    @property
    def access_ttl_seconds(self) -> int: ...

    def create_access_token(self, subject: str, claims: dict[str, Any] | None = None) -> str: ...

    def decode(self, token: str) -> dict[str, Any]:
        """Return the claims; raise AuthenticationError if expired or invalid."""
        ...


# ---- AI / mediation ------------------------------------------------------
class ToolRegistryInterface(Protocol):
    """What an agent needs from a tool registry (see domain/core/tools/base.py)."""

    def generate_tool_config(self) -> dict[str, Any]: ...

    async def execute_tool(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]: ...

    def get_available_tools(self) -> list[str]: ...


class LLMModelInterface(Protocol):
    """What an agent needs from a language model. The concrete BedrockModel
    (infrastructure) satisfies this; agents are typed against it so
    domain.core never imports infrastructure."""

    tool_registry: Any

    def render_template(self, template: str, context: dict[str, Any] | None = None) -> str: ...

    def extract_text_from_llm_response(
        self, response: dict[str, Any], with_tokens: bool = True, llm_type: str = "bedrock"
    ) -> tuple[str, dict[str, int]]: ...

    def prompt(self, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]: ...

    def stream_agentic(self, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]: ...

    def stream_text(self, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]: ...


# ---- PayPal --------------------------------------------------------------
class PayPalClientInterface(Protocol):
    """Read-side PayPal REST access the mediation flow needs."""

    async def get_dispute(self, dispute_id: str) -> dict[str, Any]: ...

    async def get_transaction(self, transaction_id: str) -> dict[str, Any]: ...

    async def get_tracking(self, transaction_id: str, tracking_number: str | None = None) -> dict[str, Any]: ...


class DisputeSourceInterface(Protocol):
    """Where a dispute case file comes from: the real Disputes API where the
    sandbox allows, a seeded fixture where it doesn't. One interface so the
    mediator logic and money movement stay identical regardless of source."""

    async def list_open(self) -> list[dict[str, Any]]: ...

    async def get_case_file(self, dispute_id: str) -> CaseFile: ...


class PayPalExecutorInterface(Protocol):
    """The ONLY thing that moves money / makes offers. It takes a proposed
    Decision, enforces the guardrails, and either performs the real PayPal
    call or returns an escalation — the AI never calls PayPal directly."""

    async def execute(self, case_file: CaseFile, decision: Decision, policy: dict[str, Any] | None = None, approved: bool = False) -> dict[str, Any]: ...
