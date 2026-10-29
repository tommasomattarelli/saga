from dataclasses import dataclass

from app.core.dialogue_markers import strip_markers


@dataclass(frozen=True)
class NarrativeObservation:
    step: int
    text: str
    observers: frozenset[str]
    location: str


@dataclass(frozen=True)
class PublicNPCResult:
    npc_id: str
    npc_name: str
    lines: tuple[str, ...]
    action: str | None


@dataclass(frozen=True)
class NPCBeat:
    step: int
    observers: frozenset[str]
    location: str
    results: tuple[PublicNPCResult, ...]


def visible_actor_context(
    npc_id: str,
    observations: list[NarrativeObservation],
    beats: list[NPCBeat],
) -> tuple[str, str]:
    narration = "\n".join(
        strip_markers(obs.text) for obs in observations if npc_id in obs.observers
    )
    public: list[str] = []
    for beat in beats:
        if npc_id not in beat.observers:
            continue
        for result in beat.results:
            public.extend(f'{result.npc_name}: "{line}"' for line in result.lines)
            if result.action:
                public.append(f"{result.npc_name}: {result.action}")
    return narration, "\n".join(public)
