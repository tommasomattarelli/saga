from collections.abc import AsyncIterator

from app.ai.providers.base import AIProvider
from app.ai.providers.schemas import AgentResponse


class ProviderTrace(AIProvider):
    def __init__(self, provider: AIProvider) -> None:
        self.provider = provider
        self.request: dict = {}
        self.response: dict = {}
        self.error: Exception | None = None

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
            raw = await self.provider.generate(**self.request)
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
            result = await self.provider.generate_with_tools(**self.request)
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

    def stream(
        self, system_prompt: str, messages: list[dict], model: str, max_tokens: int = 2000
    ) -> AsyncIterator[str]:
        raise NotImplementedError("Evaluation trials use non-streaming requests.")
