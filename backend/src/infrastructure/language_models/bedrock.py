"""
AWS Bedrock LLM provider implementation with async support.

Uses aioboto3 for async AWS SDK operations. Walks the shared fallback
chain (domain/core/constants/model_registry) on retryable errors, and
offers three call shapes the agents use:

    prompt()          — non-streaming high-level call with the tool loop
    stream_text()     — token-by-token text stream (no tools)
    stream_agentic()  — streaming ReAct loop: emits token / tool_call /
                        tool_result / done events so the UI sees the
                        reasoning happen live (this is what the mediator
                        streams over the WebSocket).
"""
import json
from collections.abc import AsyncGenerator
from typing import Any

import aioboto3
from botocore.config import Config
from botocore.exceptions import ClientError

from src.domain.core.constants.model_registry import (
    DEFAULT_BEDROCK_FALLBACK_CHAIN,
    ModelSpec,
    build_attempt_order,
)
from src.infrastructure.language_models.base import BaseLLMModel
from src.shared.logging import get_logger

logger = get_logger(__name__)

# Errors that should trigger "try the next model" rather than a hard fail.
_RETRYABLE_ERROR_CODES = {
    "ThrottlingException",
    "ModelNotReadyException",
    "ServiceUnavailableException",
    "ModelTimeoutException",
    "InternalServerException",
}

_INVALID_MODEL_MARKERS = (
    "provided model identifier is invalid",
    "model identifier is invalid",
    "could not be found",
)

# Domain-neutral fallback used ONLY if a caller invokes prompt() without a
# system prompt. Agents always pass their own, so this should rarely apply.
_DEFAULT_SYSTEM_PROMPT = (
    "You are Settle, a careful, neutral payment-dispute mediator. "
    "Answer directly and justify any decision with the evidence given."
)


class BedrockModel(BaseLLMModel):
    """AWS Bedrock model implementation with tool calling + streaming support."""

    def __init__(
        self,
        aws_access_key: str,
        aws_secret_key: str,
        model_id: str = "arn:aws:bedrock:us-east-1:779056097161:inference-profile/global.anthropic.claude-opus-4-8",
        region_name: str = "us-east-1",
        temperature: float = 0.7,
        max_tokens: int = 8192,
        top_p: float = 0.6,
        stop_sequences: list[str] | None = None,
        tool_registry: Any = None,
        timezone_str: str = "UTC",
        fallback_chain: list[ModelSpec] = DEFAULT_BEDROCK_FALLBACK_CHAIN,
        **kwargs: Any,
    ) -> None:
        super().__init__(
            model_id=model_id,
            temperature=temperature,
            max_tokens=max_tokens,
            timezone_str=timezone_str,
            tool_registry=tool_registry,
            **kwargs,
        )
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.region_name = region_name
        self.top_p = top_p
        self.stop_sequences = stop_sequences or []
        self.reasoning = False
        self.current_tool_status: str | None = None
        self.tool_call_count = 0
        self.tool_tokens = 0
        self.total_tokens = 0
        self.fallback_chain = fallback_chain
        self.last_served_by: str | None = None

        self.boto_config = Config(
            signature_version="v4",
            retries={"max_attempts": 3, "mode": "adaptive"},
            connect_timeout=10,
            read_timeout=180,
        )

        # One aioboto3 session per region, built lazily as attempts cross regions.
        self._sessions_by_region: dict[str, aioboto3.Session] = {
            region_name: aioboto3.Session(
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name=region_name,
            )
        }
        self.session = self._sessions_by_region[region_name]

    # ---- Clients -----------------------------------------------------------
    def _get_session(self, region: str) -> aioboto3.Session:
        if region not in self._sessions_by_region:
            self._sessions_by_region[region] = aioboto3.Session(
                aws_access_key_id=self.aws_access_key,
                aws_secret_access_key=self.aws_secret_key,
                region_name=region,
            )
        return self._sessions_by_region[region]

    async def _get_client(self, region: str | None = None):
        session = self._get_session(region or self.region_name)
        return session.client("bedrock-runtime", config=self.boto_config)

    def _base_inference_config(self, temp: float, tokens: int, model_arn: str) -> dict[str, Any]:
        cfg: dict[str, Any] = {"temperature": temp, "maxTokens": tokens}
        if self.stop_sequences:
            cfg["stopSequences"] = self.stop_sequences
        # Anthropic models reject topP alongside temperature in some profiles.
        if "anthropic" not in model_arn:
            cfg["topP"] = self.top_p
        return cfg

    # ---- Internal streaming assembly (same shape as converse()) -----------
    async def _stream_and_assemble(self, payload: dict[str, Any], region: str | None = None) -> dict[str, Any]:
        """Call converse_stream and assemble chunks into a converse()-shaped dict."""
        blocks: dict[int, dict[str, Any]] = {}
        stop_reason: str | None = None
        usage: dict[str, int] = {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}

        try:
            async with await self._get_client(region=region) as client:
                streaming_response = await client.converse_stream(**payload)
                async for event in streaming_response["stream"]:
                    if "contentBlockStart" in event:
                        be = event["contentBlockStart"]
                        idx = be["contentBlockIndex"]
                        start = be.get("start", {})
                        if "toolUse" in start:
                            blocks[idx] = {
                                "type": "toolUse",
                                "toolUseId": start["toolUse"]["toolUseId"],
                                "name": start["toolUse"]["name"],
                                "input_raw": "",
                            }
                        else:
                            blocks[idx] = {"type": "text", "text": ""}
                    elif "contentBlockDelta" in event:
                        be = event["contentBlockDelta"]
                        idx = be["contentBlockIndex"]
                        delta = be.get("delta", {})
                        if idx not in blocks:
                            blocks[idx] = {"type": "toolUse", "toolUseId": "unknown", "name": "unknown", "input_raw": ""} if "toolUse" in delta else {"type": "text", "text": ""}
                        block = blocks[idx]
                        if "text" in delta and block["type"] == "text":
                            block["text"] += delta["text"]
                        elif "toolUse" in delta and block["type"] == "toolUse":
                            block["input_raw"] += delta["toolUse"].get("input", "")
                    elif "contentBlockStop" in event:
                        idx = event["contentBlockStop"]["contentBlockIndex"]
                        block = blocks.get(idx)
                        if block and block["type"] == "toolUse":
                            raw = block.get("input_raw", "")
                            try:
                                block["input"] = json.loads(raw) if raw else {}
                            except json.JSONDecodeError as e:
                                logger.error("Failed to parse tool input JSON", extra={"event": "bedrock.tool_json_error", "error": str(e)})
                                block["input"] = {}
                            block.pop("input_raw", None)
                    elif "messageStop" in event:
                        stop_reason = event["messageStop"].get("stopReason")
                    elif "metadata" in event:
                        raw_usage = event["metadata"].get("usage", {})
                        usage = {
                            "inputTokens": raw_usage.get("inputTokens", 0),
                            "outputTokens": raw_usage.get("outputTokens", 0),
                            "totalTokens": raw_usage.get("totalTokens", 0),
                        }
        except Exception as e:  # noqa: BLE001
            error_str = str(e)
            if "internalServerException" in error_str or "Internal Server Error" in error_str:
                logger.warning("converse_stream too large — falling back to converse()", extra={"event": "bedrock.stream_fallback"})
                async with await self._get_client(region=region) as client:
                    return await client.converse(**payload)
            raise

        content: list[dict[str, Any]] = []
        for idx in sorted(blocks.keys()):
            block = blocks[idx]
            if block["type"] == "text":
                if block["text"].strip():
                    content.append({"text": block["text"]})
            elif block["type"] == "toolUse":
                content.append({"toolUse": {"toolUseId": block["toolUseId"], "name": block["name"], "input": block.get("input", {})}})

        return {"output": {"message": {"role": "assistant", "content": content}}, "stopReason": stop_reason, "usage": usage}

    # ---- invoke ------------------------------------------------------------
    async def invoke(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        stream: bool = True,
        enable_tools: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_id: str | None = None,
        region: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens
        effective_model_id = model_id or self.model_id

        payload: dict[str, Any] = {
            "modelId": effective_model_id,
            "messages": messages,
            "inferenceConfig": self._base_inference_config(temp, tokens, effective_model_id),
        }
        if system:
            payload["system"] = [{"text": system}]
        if enable_tools and self.tool_registry:
            tool_config = self.tool_registry.generate_tool_config()
            if tool_config and tool_config.get("tools"):
                payload["toolConfig"] = tool_config
        elif not enable_tools and kwargs.get("toolConfig"):
            payload["toolConfig"] = kwargs["toolConfig"]

        if stream and "llama" not in effective_model_id:
            return await self._stream_and_assemble(payload, region=region)
        async with await self._get_client(region=region) as client:
            return await client.converse(**payload)

    async def invoke_with_fallback(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        stream: bool = True,
        enable_tools: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        attempt_order = build_attempt_order(model_id or self.model_id, self.fallback_chain)
        last_exception: Exception | None = None
        for i, spec in enumerate(attempt_order):
            try:
                response = await self.invoke(
                    messages=messages, system=system, stream=stream, enable_tools=enable_tools,
                    temperature=temperature, max_tokens=max_tokens, model_id=spec.arn, region=spec.region, **kwargs,
                )
                self.last_served_by = spec.arn
                if i > 0:
                    logger.warning("Bedrock fallback succeeded", extra={"event": "bedrock.fallback_ok", "model": spec.label})
                return response
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                msg = e.response.get("Error", {}).get("Message", "").lower()
                last_exception = e
                is_invalid_model = code == "ValidationException" and any(m in msg for m in _INVALID_MODEL_MARKERS)
                if code in _RETRYABLE_ERROR_CODES or is_invalid_model:
                    logger.warning("Bedrock attempt failed — next model", extra={"event": "bedrock.retry", "model": spec.label, "code": code})
                    continue
                raise
            except Exception as e:  # noqa: BLE001
                last_exception = e
                logger.warning("Bedrock unclassified error — next model", extra={"event": "bedrock.retry", "model": spec.label, "error": str(e)})
                continue
        logger.error("Bedrock fallback chain exhausted", extra={"event": "bedrock.exhausted"})
        raise last_exception if last_exception else RuntimeError("No models available in fallback chain")

    # ---- Streaming text (no tools) -----------------------------------------
    async def stream_text(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        model_id: str | None = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield {"type":"token","text":...} then {"type":"done","total_tokens":N}."""
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens
        open_retryable = _RETRYABLE_ERROR_CODES | {"ResourceNotFoundException", "AccessDeniedException"}
        attempt_order = build_attempt_order(model_id or self.model_id, self.fallback_chain)
        last_exception: Exception | None = None

        for spec in attempt_order:
            payload = {"modelId": spec.arn, "messages": messages, "inferenceConfig": self._base_inference_config(temp, tokens, spec.arn)}
            if system:
                payload["system"] = [{"text": system}]
            started = False
            total_tokens = 0
            try:
                async with await self._get_client(region=spec.region) as client:
                    streaming_response = await client.converse_stream(**payload)
                    self.last_served_by = spec.arn
                    async for event in streaming_response["stream"]:
                        if "contentBlockDelta" in event:
                            text = event["contentBlockDelta"].get("delta", {}).get("text")
                            if text:
                                started = True
                                yield {"type": "token", "text": text}
                        elif "metadata" in event:
                            total_tokens = event["metadata"].get("usage", {}).get("totalTokens", 0)
                self.total_tokens = total_tokens
                yield {"type": "done", "total_tokens": total_tokens}
                return
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "")
                msg = e.response.get("Error", {}).get("Message", "").lower()
                last_exception = e
                is_invalid = code == "ValidationException" and any(m in msg for m in _INVALID_MODEL_MARKERS)
                if not started and (code in open_retryable or is_invalid):
                    continue
                raise
            except Exception as e:  # noqa: BLE001
                last_exception = e
                if not started:
                    continue
                raise
        if last_exception:
            raise last_exception
        raise RuntimeError("stream_text: no models available in fallback chain")

    # ---- Streaming agentic ReAct loop (tools + live events) ----------------
    async def stream_agentic(
        self,
        messages: list[dict[str, Any]],
        system: str | None = None,
        tool_registry: Any = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_iterations: int = 8,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream a tool-using turn, emitting token / tool_call / tool_result / done."""
        temp = temperature if temperature is not None else self.temperature
        tokens = max_tokens if max_tokens is not None else self.max_tokens
        registry = tool_registry or self.tool_registry
        tool_config = registry.generate_tool_config() if registry else None

        convo: list[dict[str, Any]] = list(messages)
        total_tokens = 0
        chosen: ModelSpec | None = None
        attempt_order = build_attempt_order(self.model_id, self.fallback_chain)

        for _iteration in range(max_iterations):
            specs = [chosen] if chosen is not None else attempt_order
            blocks: dict[int, dict[str, Any]] = {}
            order: list[int] = []
            stop_reason: str | None = None
            opened = False
            last_exc: Exception | None = None

            for spec in specs:
                payload = {"modelId": spec.arn, "messages": convo, "inferenceConfig": self._base_inference_config(temp, tokens, spec.arn)}
                if system:
                    payload["system"] = [{"text": system}]
                if tool_config and tool_config.get("tools"):
                    payload["toolConfig"] = tool_config
                try:
                    async with await self._get_client(region=spec.region) as client:
                        streaming_response = await client.converse_stream(**payload)
                        chosen = spec
                        self.last_served_by = spec.arn
                        async for event in streaming_response["stream"]:
                            if "contentBlockStart" in event:
                                be = event["contentBlockStart"]
                                idx = be["contentBlockIndex"]
                                start = be.get("start", {})
                                if "toolUse" in start:
                                    blocks[idx] = {"type": "toolUse", "toolUseId": start["toolUse"]["toolUseId"], "name": start["toolUse"]["name"], "input_raw": ""}
                                else:
                                    blocks[idx] = {"type": "text", "text": ""}
                                order.append(idx)
                            elif "contentBlockDelta" in event:
                                be = event["contentBlockDelta"]
                                idx = be["contentBlockIndex"]
                                delta = be.get("delta", {})
                                if idx not in blocks:
                                    blocks[idx] = {"type": "text", "text": ""}
                                    order.append(idx)
                                blk = blocks[idx]
                                if "text" in delta and blk["type"] == "text":
                                    blk["text"] += delta["text"]
                                    yield {"type": "token", "text": delta["text"]}
                                elif "toolUse" in delta and blk["type"] == "toolUse":
                                    blk["input_raw"] += delta["toolUse"].get("input", "")
                            elif "contentBlockStop" in event:
                                idx = event["contentBlockStop"]["contentBlockIndex"]
                                blk = blocks.get(idx)
                                if blk and blk["type"] == "toolUse":
                                    raw = blk.get("input_raw", "")
                                    try:
                                        blk["input"] = json.loads(raw) if raw else {}
                                    except json.JSONDecodeError:
                                        blk["input"] = {}
                                    yield {"type": "tool_call", "name": blk["name"], "input": blk["input"]}
                            elif "messageStop" in event:
                                stop_reason = event["messageStop"].get("stopReason")
                            elif "metadata" in event:
                                total_tokens += event["metadata"].get("usage", {}).get("totalTokens", 0)
                    opened = True
                    break
                except ClientError as e:
                    last_exc = e
                    if chosen is None:
                        code = e.response.get("Error", {}).get("Code", "")
                        if code in (_RETRYABLE_ERROR_CODES | {"ResourceNotFoundException", "AccessDeniedException", "ValidationException"}):
                            continue
                    raise
                except Exception as e:  # noqa: BLE001
                    last_exc = e
                    if chosen is None:
                        continue
                    raise

            if not opened:
                if last_exc:
                    raise last_exc
                raise RuntimeError("stream_agentic: no models available")

            assistant_content: list[dict[str, Any]] = []
            tool_use_blocks: list[dict[str, Any]] = []
            for idx in order:
                blk = blocks[idx]
                if blk["type"] == "text" and blk["text"]:
                    assistant_content.append({"text": blk["text"]})
                elif blk["type"] == "toolUse":
                    assistant_content.append({"toolUse": {"toolUseId": blk["toolUseId"], "name": blk["name"], "input": blk.get("input", {})}})
                    tool_use_blocks.append(blk)
            if assistant_content:
                convo.append({"role": "assistant", "content": assistant_content})

            if stop_reason == "tool_use" and tool_use_blocks and registry:
                tool_results = []
                for blk in tool_use_blocks:
                    result = await registry.execute_tool(blk["name"], blk.get("input", {}))
                    ok = bool(result.get("success", True)) if isinstance(result, dict) else True
                    yield {"type": "tool_result", "name": blk["name"], "ok": ok, "result": result}
                    tool_results.append({
                        "toolResult": {
                            "toolUseId": blk["toolUseId"],
                            "content": [{"json": result if isinstance(result, dict) else {"data": result}}],
                            "status": "success" if ok else "error",
                        }
                    })
                convo.append({"role": "user", "content": tool_results})
                continue
            break

        self.total_tokens = total_tokens
        yield {"type": "done", "total_tokens": total_tokens}

    # ---- High-level prompt (non-streaming, with tool loop) -----------------
    async def prompt(
        self,
        text: str | None = None,
        system_prompt: str = _DEFAULT_SYSTEM_PROMPT,
        system_context: dict[str, Any] | None = None,
        message_history: list[dict[str, Any]] | None = None,
        grammar: dict[str, Any] | None = None,
        model_id: str | None = None,
        stream: bool = False,
        enable_tools: bool = False,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning: bool = False,
        **kwargs: Any,
    ) -> AsyncGenerator[dict[str, Any], None]:
        self.tool_call_count = 0
        self.tool_tokens = 0
        self.model_id = model_id or self.model_id
        self.reasoning = reasoning

        system = self.render_template(system_prompt, system_context or {}) if system_prompt else None
        messages = message_history.copy() if message_history else []
        if text:
            messages = self.clean_message_history(messages)
            messages.append({"role": "user", "content": [{"text": text}]})
        if not messages:
            raise ValueError("At least one message is required")

        if not enable_tools and grammar:
            kwargs["toolConfig"] = grammar

        response = await self.invoke_with_fallback(
            messages=messages, system=system, stream=True, enable_tools=enable_tools,
            temperature=temperature, max_tokens=max_tokens, **kwargs,
        )
        initial_tokens = response.get("usage", {}).get("totalTokens", 0)

        if enable_tools and self._has_tool_calls(response):
            response = await self.handle_tool_calls(response=response, messages=messages, system=system, initial_tokens=initial_tokens, **kwargs)

        response["toolCallCount"] = self.tool_call_count
        response["toolTokens"] = self.tool_tokens
        response["totalTokens"] = initial_tokens + self.tool_tokens
        response["servedByModel"] = self.last_served_by
        yield response

    async def handle_tool_calls(
        self,
        response: dict[str, Any],
        messages: list[dict[str, Any]],
        system: str | None = None,
        max_iterations: int = 20,
        initial_tokens: int = 0,
        **kwargs: Any,
    ) -> dict[str, Any]:
        iteration = 0
        current = response
        while self._has_tool_calls(current) and iteration < max_iterations:
            iteration += 1
            messages.append({"role": "assistant", "content": current["output"]["message"]["content"]})
            tool_results = []
            for block in current["output"]["message"]["content"]:
                if "toolUse" in block:
                    self.tool_call_count += 1
                    tool_results.append(await self._execute_tool(block["toolUse"]))
            messages.append({"role": "user", "content": tool_results})
            current = await self.invoke_with_fallback(messages=messages, system=system, enable_tools=True, **kwargs)
            self.tool_tokens += current.get("usage", {}).get("totalTokens", 0)
        if iteration >= max_iterations:
            logger.warning("Reached max tool iterations", extra={"event": "bedrock.max_tool_iters"})
        return current

    def _has_tool_calls(self, response: dict[str, Any]) -> bool:
        try:
            if response.get("stopReason") == "tool_use":
                return True
            content = response.get("output", {}).get("message", {}).get("content", [])
            return any("toolUse" in block for block in content)
        except (KeyError, TypeError):
            return False

    async def _execute_tool(self, tool_use: dict[str, Any]) -> dict[str, Any]:
        tool_use_id = tool_use["toolUseId"]
        tool_name = tool_use["name"]
        tool_input = tool_use["input"]
        try:
            output = await self.tool_registry.execute_tool(tool_name=tool_name, tool_input=tool_input) if self.tool_registry else {"error": "No tool registry configured"}
            return {"toolResult": {"toolUseId": tool_use_id, "content": [{"text": json.dumps(output)}]}}
        except Exception as e:  # noqa: BLE001
            logger.error("Tool execution error", extra={"event": "bedrock.tool_error", "tool": tool_name, "error": str(e)}, exc_info=True)
            return {"toolResult": {"toolUseId": tool_use_id, "content": [{"text": json.dumps({"error": str(e)})}], "status": "error"}}

    def extract_text_response(self, response: dict[str, Any]) -> str:
        try:
            return "\n".join(b["text"] for b in response["output"]["message"]["content"] if "text" in b)
        except (KeyError, TypeError):
            return ""
