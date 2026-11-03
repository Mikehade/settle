"""
Read-only evidence tools.

Optional helpers the mediator can call to pull a hard fact out of the
assembled case file (tracking status, the original transaction). Because
the case file is pre-assembled, these never hit the network — they just
let the model fetch a specific signal on demand, which also reads well in
the demo ("checking tracking…"). They never mutate anything.

The current case file is injected per case via `begin_case()`.
"""
from typing import Any

from src.domain.core.tools.base import BaseTool
from src.shared.logging import get_logger

logger = get_logger(__name__)

EVIDENCE_TOOL_NAMES = ["lookup_tracking", "lookup_transaction"]


class EvidenceTools(BaseTool):
    def __init__(self, enabled_tools: list | None = None, **kwargs) -> None:
        super().__init__(enabled_tools=enabled_tools or EVIDENCE_TOOL_NAMES, **kwargs)

    def begin_case(self, case_file: dict[str, Any]) -> None:
        self.kwargs["case_file"] = case_file

    async def execute(self, tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        method = self.get_tool_method(tool_name)
        if not method:
            return {"success": False, "error": f"Tool '{tool_name}' not found"}
        try:
            merged = {**tool_input, **self.kwargs}
            return await method(**merged)
        except Exception as e:  # noqa: BLE001
            logger.error("Evidence tool error", extra={"event": "evidence.error", "tool": tool_name, "error": str(e)}, exc_info=True)
            return {"success": False, "error": str(e)}

    # fmt: off
    async def _lookup_tracking(self, **kwargs) -> dict[str, Any]:
        """Return the shipment tracking status for this dispute (delivered / in_transit / not_shipped / none)."""
        cf = kwargs.get("case_file", {})
        return {
            "success": True,
            "data": {
                "tracking_status": cf.get("tracking_status", "unknown"),
                "carrier": cf.get("tracking_carrier"),
                "tracking_number": cf.get("tracking_number"),
            },
        }

    async def _lookup_transaction(self, **kwargs) -> dict[str, Any]:
        """Return the original transaction facts: amount, currency, item value, and any prior refunds."""
        cf = kwargs.get("case_file", {})
        return {
            "success": True,
            "data": {
                "transaction_id": cf.get("transaction_id"),
                "capture_id": cf.get("capture_id"),
                "disputed_amount": cf.get("disputed_amount"),
                "currency": cf.get("currency"),
                "item_value": cf.get("item_value"),
                "prior_refunds": cf.get("prior_refunds", 0.0),
            },
        }
    # fmt: on
