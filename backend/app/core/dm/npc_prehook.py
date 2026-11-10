from dataclasses import dataclass
from uuid import uuid4

from pydantic import ValidationError

from app.ai.router import GameplayConfig
from app.ai.tools.tools_special import InvokeNpc
from app.core.dm.operation_recorder import OperationRecorder
from app.core.npc_fields import resolve_npc_fields
from app.core.npc_resolver import resolve_npc
from app.core.npc_scaffold import create_npc_record
from app.core.psychology import resolve_psychology
from app.memory.operation_delta import OperationState
from app.memory.operation_results import ErrorResult, NPCResult, OperationErrorReason


@dataclass(frozen=True)
class PreparedNPC:
    call_index: int
    call_id: str
    npc_id: str
    name: str
    context: str


def prepare_npc_calls(
    calls: list[dict],
    world_state: dict,
    config: GameplayConfig,
    baseline: dict,
    *,
    operations: OperationRecorder | None = None,
    step: int | None = None,
    beat: int | None = None,
) -> tuple[list[PreparedNPC], dict[int, str]]:
    selected: list[tuple[int, str, str | None, str, str]] = []
    seen: set[str] = set()
    notes: dict[int, str] = {}

    def reject(index: int, note: str, reason: OperationErrorReason = "domain_rejection") -> None:
        notes[index] = note
        if operations is not None:
            operations.append(
                origin="npc",
                name="invoke_npc",
                arguments=calls[index].get("args", {}),
                outcome="rejected",
                step=step,
                beat=beat,
                result=ErrorResult(description=note, reason=reason),
            )

    location = world_state.get("meta", {}).get("current_location")
    for index, call in enumerate(calls):
        call_id = call.get("id", "invoke_npc")
        try:
            args = InvokeNpc(**call.get("args", {}))
        except ValidationError:
            reject(
                index,
                "Invalid tool arguments. Check the tool's required fields.",
                "invalid_arguments",
            )
            continue
        name = args.name.strip()
        if not name:
            reject(index, "An NPC name is required.")
            continue
        resolution = resolve_npc(name, world_state)
        npc_id = resolution.npc_id
        if npc_id is None:
            if resolution.candidates or resolution.error != f"{name} is not a known NPC.":
                reject(index, resolution.error)
                continue
            if not config.auto_create_npcs:
                reject(index, resolution.error)
                continue
        elif location and world_state["npcs"][npc_id].get("location") != location:
            reject(index, f"{name} is elsewhere and is not present here.")
            continue
        identity = npc_id or f"new:{name.casefold()}"
        if identity in seen:
            reject(index, f"{name} is already selected in this beat.")
            continue
        seen.add(identity)
        if len(selected) >= config.max_npc_calls:
            reject(index, "The NPC call limit for this beat has been reached.")
            continue
        selected.append((index, call_id, npc_id, name, args.context))

    prepared = []
    taxonomy = baseline.get("taxonomy")
    for index, call_id, npc_id, name, context in selected:
        if npc_id is None:
            before = OperationState.capture(world_state, {}, {})
            npc_id = str(uuid4())
            world_state.setdefault("npcs", {})[npc_id] = create_npc_record(
                name,
                detail=config.npc_auto_create_detail,
                psychology=resolve_psychology(taxonomy),
                npc_fields=resolve_npc_fields(taxonomy),
                location=location,
                auto_created=True,
            )
            if operations is not None:
                operations.append(
                    origin="npc",
                    name="create_npc",
                    arguments={"name": name, "npc_id": npc_id},
                    outcome="succeeded",
                    step=step,
                    beat=beat,
                    before=before,
                    after=OperationState.capture(world_state, {}, {}),
                    result=NPCResult(
                        description="Created an NPC identity.", npc_id=npc_id, status="created"
                    ),
                )
        prepared.append(
            PreparedNPC(index, call_id, npc_id, world_state["npcs"][npc_id]["name"], context)
        )
    return prepared, notes
