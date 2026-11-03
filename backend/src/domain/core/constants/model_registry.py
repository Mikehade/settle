"""
Shared Bedrock model fallback registry.

Single source of truth for model priority order, consumed by:
    - BedrockModel (src/infrastructure/language_models/bedrock.py)
    - LangGraphBedrockModel (src/infrastructure/langgraph_models/bedrock.py)

Pure data — no boto3/aioboto3 imports, no retry logic. Reorder, add, or
remove entries here; nothing downstream indexes into this list
positionally, so the list can be freely expanded or reduced (e.g. when
a model is deprecated) without touching any other file.

An explicitly-passed model_id that is NOT in this list is still tried
first by callers — it just won't appear as a fallback option for
other requests once removed here.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSpec:
    arn: str
    region: str
    label: str  # human-readable, for logging only


DEFAULT_BEDROCK_FALLBACK_CHAIN: list[ModelSpec] = [
    # ModelSpec(
    #     arn="arn:aws:bedrock:us-east-1:779056097161:inference-profile/global.anthropic.claude-opus-4-6-v1",  # TODO: OPUS_4_6_ARN — fill in before use
    #     region="us-east-1",
    #     label="opus-4.6",
    # ),
    ModelSpec(
        arn="global.amazon.nova-2-lite-v1:0",
        region="us-east-1",
        label="nova-2-lite (global)",
    ),
    ModelSpec(
        arn="arn:aws:bedrock:us-east-1:779056097161:inference-profile/global.amazon.nova-2-lite-v1:0",
        region="us-east-1",
        label="nova-2-lite (global)",
    ),
    ModelSpec(
        arn="arn:aws:bedrock:us-east-1:779056097161:inference-profile/global.anthropic.claude-opus-4-7",
        region="us-east-1",
        label="opus-4.7",
    ),
    ModelSpec(
        arn="arn:aws:bedrock:us-east-1:779056097161:inference-profile/global.anthropic.claude-opus-4-8",
        region="us-east-1",
        label="opus-4.8",
    ),
    ModelSpec(
        arn="arn:aws:bedrock:us-west-2:779056097161:inference-profile/us.amazon.nova-2-lite-v1:0",
        region="us-west-2",
        label="nova-2-lite (us)",
    ),
]


def build_attempt_order(
    explicit_model_id: str | None,
    chain: list[ModelSpec] = DEFAULT_BEDROCK_FALLBACK_CHAIN,
) -> list[ModelSpec]:
    """
    Build the effective attempt order for a single call.

    If explicit_model_id is provided, it goes first (even if not in the
    chain — e.g. a deprecated or one-off model). The chain then follows,
    with any entry matching explicit_model_id by exact ARN removed to
    avoid a wasted duplicate attempt.
    """
    remainder = [m for m in chain if m.arn != explicit_model_id]

    if explicit_model_id:
        # Preserve region if we recognise the ARN, else default to the
        # chain's first region as a best guess for client selection.
        matched = next((m for m in chain if m.arn == explicit_model_id), None)
        head = matched or ModelSpec(
            arn=explicit_model_id,
            region=chain[0].region if chain else "us-west-2",
            label="explicit",
        )
        return [head] + remainder

    return list(chain)
