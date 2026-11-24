import base64
import json
from collections.abc import AsyncIterator

from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt
from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentResponse
from app.ai.providers.usage import UsageMetadata, usage_scope


def generation_request_evidence(request: GenerationRequest) -> dict:
    return {
        "identity": request.identity.digest,
        "identity_snapshot": json.loads(request.identity.snapshot_json),
        "request_snapshot": json.loads(request.snapshot_json),
        "tool_declarations": request.tool_declarations,
        "wire_schema": request.wire_schema,
        "canonical_schema": request.canonical_schema,
        "format_mode": request.format_mode.value,
        "output_limit": request.output_limit.effective,
        "session_affinity": request.session_affinity,
    }


def _receipt_evidence(receipt: RawGenerationReceipt) -> dict:
    return {
        "text": receipt.text,
        "tool_calls": [
            {
                "call_id": call.call_id,
                "name": call.name,
                "arguments": (
                    {"kind": "raw_text", "value": call.arguments.raw_text_value}
                    if call.arguments.kind == "raw_text"
                    else {"kind": "structured", "value": call.arguments.structured_value}
                ),
                "signature": (
                    base64.b64encode(call.signature).decode("ascii")
                    if call.signature is not None
                    else None
                ),
            }
            for call in receipt.tool_calls
        ],
        "finish_reason": receipt.finish_reason,
        "refusal": receipt.refusal,
        "blocked_reason": receipt.blocked_reason,
        "response_id": receipt.response_id,
        "model_id": receipt.model_id,
        "raw_candidate": receipt.raw_candidate,
        "text_signature": (
            base64.b64encode(receipt.text_signature).decode("ascii")
            if receipt.text_signature is not None
            else None
        ),
    }


class ProviderTrace(AIProvider):
    def __init__(self, provider: AIProvider, *, role: str = "actor") -> None:
        self.provider = provider
        self.role = role
        self.request: dict = {}
        self.response: dict = {}
        self.error: Exception | None = None
        self.usage: list[UsageMetadata] = []

    def _begin(self, request: dict) -> None:
        if self.request:
            raise ValueError("A single-call evaluation trial cannot make a second request.")
        self.request = request

    async def generate(
        self,
        system_prompt: str,
        messages: list[dict],
        model: str,
        max_tokens: int = 2000,
        json_mode: bool = False,
    ) -> str:
        self._begin(
            {
                "system_prompt": system_prompt,
                "messages": messages,
                "model": model,
                "max_tokens": max_tokens,
                "json_mode": json_mode,
            }
        )
        try:
            with usage_scope(role=self.role) as collector:
                try:
                    raw = await self.provider.generate(**self.request)
                finally:
                    self.usage = collector.items
            self.response = {"text": raw}
            return raw
        except Exception as exc:
            self.error = exc
            raise

    async def generate_with_tools(
        self,
        system_prompt: str,
        messages: list[dict],
        tools: list[dict],
        model: str,
        max_tokens: int = 2000,
    ) -> AgentResponse:
        self._begin(
            {
                "system_prompt": system_prompt,
                "messages": messages,
                "tools": tools,
                "model": model,
                "max_tokens": max_tokens,
            }
        )
        try:
            with usage_scope(role="dm") as collector:
                try:
                    result = await self.provider.generate_with_tools(**self.request)
                finally:
                    self.usage = collector.items
            self.response = {
                "text": result.text,
                "tool_calls": [
                    {"id": call.id, "name": call.name, "arguments": call.arguments}
                    for call in result.tool_calls
                ],
            }
            return result
        except Exception as exc:
            self.error = exc
            raise

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        self._begin(generation_request_evidence(request))
        try:
            with usage_scope(role=request.role) as collector:
                try:
                    result = await self.provider.send(request)
                finally:
                    self.usage = collector.items
            self.response = _receipt_evidence(result)
            return result
        except Exception as exc:
            self.error = exc
            raise

    def stream(
        self, system_prompt: str, messages: list[dict], model: str, max_tokens: int = 2000
    ) -> AsyncIterator[str]:
        raise NotImplementedError("Evaluation trials use non-streaming requests.")
