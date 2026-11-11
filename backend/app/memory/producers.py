from dataclasses import dataclass

from app.ai.providers.base import logged_generate
from app.ai.router import get_generation
from app.memory.producer_contracts import FactsPayload, ResolvedFact, validate_facts
from app.memory.producer_prompts import MemoryPayload, PreparedMemoryRequest


@dataclass(frozen=True)
class MemoryGeneration:
    payload: MemoryPayload
    facts: tuple[ResolvedFact, ...]
    provider: str
    model: str
    raw: str


async def generate_memory(request: PreparedMemoryRequest) -> MemoryGeneration:
    provider, config = await get_generation()
    raw = await logged_generate(
        provider,
        caller=f"memory_{request.kind}",
        system_prompt=request.system_prompt,
        messages=[{"role": "user", "content": request.user_prompt}],
        model=config.model,
        max_tokens=config.max_tokens,
        json_mode=True,
    )
    payload = request.validate_output(raw)
    facts = (
        validate_facts(payload, request.source, request.facts_policy)
        if isinstance(payload, FactsPayload)
        else ()
    )
    return MemoryGeneration(
        payload=payload, facts=facts, provider=config.provider, model=config.model, raw=raw
    )
