"""The real Settle backend for the end-to-end tests, on a throwaway database.

Runs the backend app as it is, with three differences that keep the tests offline and repeatable:

- a fresh SQLite database in a temporary folder, holding the test sellers;
- the demo disputes only (DISPUTE_SOURCE_MODE=fixture), so nothing calls PayPal;
- a scripted model in place of Bedrock, which reasons through each demo case the same way every
  time, so the tests know how a run will end.

It also adds `POST /__e2e__/reset`, which clears every dispute, decision and fairness policy so
each test starts from the same place. Nothing in ../backend changes: the model is swapped through
the container, as the backend's own tests do.

Playwright starts this (see playwright.config.ts). By hand, from the frontend folder:

    E2E_SELLERS='[{"email": "...", "password": "...", "full_name": "..."}]' \\
        ../backend/.venv/bin/python e2e/backend.py
"""
import asyncio
import atexit
import json
import os
import shutil
import signal
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(os.environ.get("E2E_BACKEND_DIR", Path(__file__).resolve().parents[2] / "backend"))
PORT = int(os.environ.get("E2E_BACKEND_PORT", "8100"))
# One folder per port, emptied on start, so a run that was killed outright leaves nothing behind
# for long. A normal stop deletes it on the way out.
DB_DIR = Path(tempfile.gettempdir()) / f"settle-e2e-{PORT}"
shutil.rmtree(DB_DIR, ignore_errors=True)
DB_DIR.mkdir()
DB_PATH = DB_DIR / "settle.db"
atexit.register(shutil.rmtree, DB_DIR, ignore_errors=True)

# The test settings ignore backend/.env, so no AWS or PayPal credentials are picked up.
os.environ.update(
    APP_ENV="test",
    DATABASE_URL=f"sqlite+aiosqlite:///{DB_PATH}",
    DISPUTE_SOURCE_MODE="fixture",
    LOG_LEVEL=os.environ.get("E2E_LOG_LEVEL", "WARNING"),
)
sys.path.insert(0, str(BACKEND_DIR))

import uvicorn  # noqa: E402
from dependency_injector import providers  # noqa: E402
from sqlalchemy import text  # noqa: E402

import src.infrastructure.db.models  # noqa: E402, F401  (registers every table)
from main import create_app  # noqa: E402
from src.domain.core.tools.propose_tools import ProposalTools  # noqa: E402
from src.infrastructure.db.base import Base  # noqa: E402

SERVED_BY = "scripted-e2e-model"


@dataclass(frozen=True)
class Script:
    """How the scripted model reasons through one demo case: what it says, then what it calls."""

    classify: str
    weigh: str
    policy: str
    choose: str
    proposal: tuple[str, dict[str, Any]]
    checks: tuple[str, ...] = field(default=("lookup_transaction",))


# Each case ends a different way under the default limits (80% confidence, 200 for a person):
# the earbuds refund falls short on confidence and comes to the seller, the shirt's replacement is
# carried out (as a dry run, being a demo case), and the 500 charge is escalated with no outcome.
SCRIPTS: dict[str, Script] = {
    "FIXTURE-NR-001": Script(
        classify="not_received",
        weigh="The label was created three weeks ago and tracking never updated, so the parcel "
        "most likely never shipped.",
        policy="The policy favours a full refund when an order never shipped.",
        choose="Refund the full 59.99, though the carrier could still turn up a scan.",
        checks=("lookup_tracking", "lookup_transaction"),
        proposal=(
            "propose_refund",
            {
                "amount": 59.99,
                "confidence": 0.74,
                "rationale": "Tracking shows the order **never shipped**, so the buyer should get "
                "their money back.",
                "dispute_type": "not_received",
                "evidence_summary": "No carrier scans since the label was created.",
                "policy_application": "Refund in full when an order never shipped.",
            },
        ),
    ),
    "FIXTURE-NAD-001": Script(
        classify="not_as_described",
        weigh="The shirt was delivered in the wrong size; the buyer is otherwise happy with it.",
        policy="A wrong size is best fixed with the right one.",
        choose="Send the correct size.",
        checks=("lookup_tracking",),
        proposal=(
            "propose_reship",
            {
                "confidence": 0.91,
                "rationale": "The buyer received a size M instead of an L. Sending the right size "
                "settles it fairly.",
                "dispute_type": "not_as_described",
                "evidence_summary": "Delivered by USPS; wrong size.",
                "policy_application": "Replace items sent in the wrong size.",
            },
        ),
    ),
    "FIXTURE-UNAUTH-001": Script(
        classify="unauthorized_or_other",
        weigh="The buyer says they never made the purchase, and there is nothing to confirm or "
        "rule that out.",
        policy="The policy leaves possible fraud to the seller.",
        choose="Escalate to the seller.",
        proposal=(
            "escalate_to_seller",
            {
                "recommendation": "Check the order against the buyer's account history before "
                "deciding.",
                "confidence": 0.55,
                "rationale": "A possible unauthorised charge of this size needs the seller's "
                "judgement.",
                "dispute_type": "unauthorized_or_other",
                "evidence_summary": "No evidence either way.",
                "policy_application": "Possible fraud goes to the seller.",
            },
        ),
    ),
}


class ScriptedModel:
    """Stands in for BedrockModel: streams a scripted narration, then calls the scripted tools.

    It speaks the same events as the real model (token, tool_call, tool_result, done), with the
    stage markers the mediator splits its narration on, so everything after the model is the
    backend's own code.
    """

    STEP_DELAY = float(os.environ.get("E2E_MODEL_STEP_DELAY", "0.02"))

    def __init__(self) -> None:
        self.tool_registry: Any = None
        self.last_served_by: str | None = SERVED_BY

    def render_template(self, template: str, context: dict | None = None) -> str:
        return template

    def extract_text_from_llm_response(self, response: dict, with_tokens: bool = True, llm_type: str = "bedrock"):
        return response.get("_text", ""), {"total_tokens": 1, "tool_tokens": 0, "tool_count": 0}

    @staticmethod
    def _script_for(registry: Any) -> Script:
        for tools in getattr(registry, "tool_classes", []):
            if isinstance(tools, ProposalTools):
                dispute_id = tools.kwargs.get("dispute_id", "")
                if dispute_id in SCRIPTS:
                    return SCRIPTS[dispute_id]
                raise RuntimeError(f"No script for {dispute_id!r}")
        raise RuntimeError("The mediator gave the model no proposal tools")

    async def prompt(self, *, enable_tools: bool = False, **kwargs: Any):
        script = self._script_for(self.tool_registry)
        if enable_tools:
            await self.tool_registry.execute_tool(*script.proposal)
        yield {"_text": script.choose, "servedByModel": SERVED_BY}

    async def stream_agentic(self, *, tool_registry: Any = None, **kwargs: Any):
        registry = tool_registry or self.tool_registry
        script = self._script_for(registry)
        for marker, said in (
            ("<<<CLASSIFY>>>", script.classify),
            ("<<<WEIGH>>>", script.weigh),
            ("<<<POLICY>>>", script.policy),
            ("<<<CHOOSE>>>", script.choose),
        ):
            for chunk in [marker, *(word + " " for word in said.split())]:
                await asyncio.sleep(self.STEP_DELAY)
                yield {"type": "token", "text": chunk}
        for name, tool_input in [*((check, {}) for check in script.checks), script.proposal]:
            await asyncio.sleep(self.STEP_DELAY)
            yield {"type": "tool_call", "name": name, "input": tool_input}
            result = await registry.execute_tool(name, tool_input)
            yield {"type": "tool_result", "name": name, "ok": bool(result.get("success", True))}
        yield {"type": "done", "total_tokens": 1}


def build_app():
    app = create_app()
    container = app.container
    container.bedrock_model.override(providers.Factory(ScriptedModel))

    @app.post("/__e2e__/reset", include_in_schema=False)
    async def reset() -> dict[str, bool]:
        """Forget every dispute, decision and policy. The sellers stay."""
        async with container.database().engine.begin() as conn:
            for table in ("audit_entries", "disputes", "fairness_policies"):
                await conn.execute(text(f"DELETE FROM {table}"))  # noqa: S608  (fixed names)
        return {"reset": True}

    return app


async def prepare(app) -> None:
    """Create the tables and the test sellers, through the backend's own user service."""
    container = app.container
    async with container.database().engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    for seller in json.loads(os.environ.get("E2E_SELLERS", "[]")):
        await container.user_service().create_user(
            email=seller["email"],
            password=seller["password"],
            full_name=seller.get("full_name"),
            is_superuser=True,
        )
    # Uvicorn runs its own event loop; drop the connections opened on this one.
    await container.database().dispose()


def main() -> None:
    # Uvicorn stops on SIGTERM, then raises it again with the handler that was there before it
    # started. Exiting through Python here, rather than the default, lets atexit clean up.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    app = build_app()
    asyncio.run(prepare(app))
    print(f"Settle e2e backend on http://localhost:{PORT} (database {DB_PATH})", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_config=None, access_log=False)


if __name__ == "__main__":
    main()
