"""WebSocket event vocabulary and close codes — one source of truth for
both the server and the frontend (see UI_INTEGRATION.md)."""
from enum import IntEnum, StrEnum


class OutboundEvent(StrEnum):
    # Connection lifecycle
    CONNECTED = "connection.ready"
    ERROR = "connection.error"
    # Mediation case lifecycle (streamed live per case)
    CASE_DETECTED = "case.detected"
    CASE_GATHERING = "case.gathering"
    CASE_REASONING_STEP = "case.reasoning_step"   # stage: classify|weigh|policy|choose|gate
    CASE_TOKEN = "case.token"                      # rationale text deltas
    CASE_TOOL_CALL = "case.tool_call"
    CASE_TOOL_RESULT = "case.tool_result"
    CASE_DECISION = "case.decision"
    CASE_ESCALATED = "case.escalated"
    CASE_EXECUTED = "case.executed"
    CASE_EXPLAINED = "case.explained"
    CASE_ERROR = "case.error"
    # Chat lane
    AGENT_MESSAGE = "agent.message"
    AGENT_TYPING = "agent.typing"


class InboundEvent(StrEnum):
    MEDIATE = "seller.mediate"          # trigger mediation for a dispute_id
    APPROVE = "seller.approve"          # approve an escalated recommendation
    REJECT = "seller.reject"            # reject an escalated recommendation
    MESSAGE = "seller.message"          # chat: answer a mediator question
    SET_POLICY = "seller.set_policy"    # update fairness policy inline
    PING = "ping"


class CloseCode(IntEnum):
    NORMAL = 1000
    INTERNAL_ERROR = 1011
    NOT_AUTHENTICATED = 4401
    INVALID_TOKEN = 4402
