from __future__ import annotations

from uuid import uuid4

from eval.memory.plan import prepare_plan


def memory_plan(
    *,
    models: list[str],
    batches: int = 1,
    repetitions: int = 1,
    language: str = "en",
    scope: str = "test-memory-scope",
):
    sources: list[dict[str, object]] = []
    for _ in range(batches):
        turns: list[dict[str, object]] = [
            {
                "reference": f"t{index + 1}",
                "turn_id": str(uuid4()),
                "player_action": "Ask",
                "narration": "A door opens.",
                "operations": None,
            }
            for index in range(2)
        ]
        source: dict[str, object] = {"turns": turns}
        sources.append(source)
    return prepare_plan(
        sources=sources,
        facts_policy={
            "max_per_batch": 2,
            "importance_levels": [{"name": "high", "criteria": "Major", "examples": "Secret"}],
        },
        global_policy={"target_words": 100},
        language=language,
        models=models,
        repetitions=repetitions,
        global_count=1,
        session_scope=scope,
    )
