from collections.abc import Mapping
from types import MappingProxyType
from typing import Literal

from pydantic import BaseModel, ConfigDict


# Stored sources must remain readable after the runtime tools change or disappear.
class _ArgumentsV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class _Named(_ArgumentsV1):
    name: str


class _AddItem(_Named):
    description: str = ""
    quantity: int = 1


class _Move(_ArgumentsV1):
    location: str


class _Quest(_ArgumentsV1):
    quest_id: str
    status: Literal["active", "completed", "failed", "abandoned"]
    name: str = ""
    description: str | None = None


class _Psychology(_ArgumentsV1):
    npc: str
    changes: dict[str, int]
    reason: str = ""


class _Event(_ArgumentsV1):
    description: str


class _Mood(_ArgumentsV1):
    mood: str


class _Time(_ArgumentsV1):
    minutes: int


class _InvokeNPC(_Named):
    context: str = ""


class _UpdateNPC(_Named):
    updates: dict[str, str]
    create: bool = False


class _KillNPC(_Named):
    cause: str


class _RemoveNPC(_Named):
    reason: str


class _RestoreNPC(_Named):
    location: str | None = None


class _Dice(_ArgumentsV1):
    check: str
    stat: str
    difficulty: Literal["trivial", "easy", "normal", "hard", "very_hard", "near_impossible"]
    advantage: bool = False
    disadvantage: bool = False
    hazard_class: Literal["minor", "serious", "deadly"] | None = None
    reason: str = ""


class _Attack(_ArgumentsV1):
    attacker: str
    target: str
    weapon_class: Literal["unarmed", "light", "medium", "heavy"] | None = None
    advantage: bool = False
    disadvantage: bool = False
    reason: str = ""


class _Heal(_ArgumentsV1):
    healer: str
    target: str
    heal_class: Literal["minor", "strong", "full"]
    reason: str = ""


V1_ARGUMENTS: Mapping[str, type[BaseModel]] = MappingProxyType(
    {
        "add_item": _AddItem,
        "remove_item": _Named,
        "move_to": _Move,
        "update_quest": _Quest,
        "change_npc_psychology": _Psychology,
        "log_event": _Event,
        "set_scene_mood": _Mood,
        "advance_time": _Time,
        "invoke_npc": _InvokeNPC,
        "update_npc": _UpdateNPC,
        "kill_npc": _KillNPC,
        "remove_npc": _RemoveNPC,
        "restore_npc": _RestoreNPC,
        "request_dice": _Dice,
        "attack": _Attack,
        "heal": _Heal,
    }
)
