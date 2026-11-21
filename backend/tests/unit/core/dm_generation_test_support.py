from __future__ import annotations

from app.ai.generation_contracts import GenerationRequest, RawGenerationReceipt


class SequenceProvider:
    def __init__(self, receipts: list[RawGenerationReceipt]) -> None:
        self.receipts = receipts
        self.requests: list[GenerationRequest] = []

    async def send(self, request: GenerationRequest) -> RawGenerationReceipt:
        self.requests.append(request)
        return self.receipts.pop(0)
