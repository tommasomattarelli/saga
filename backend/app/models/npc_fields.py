"""ADR 0009 — world-defined NPC descriptive field vocabulary (G1/G2/G3)."""

from pydantic import BaseModel, ConfigDict


class NpcFieldDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    default: str = ""
    # G3: rendered in the DM <npcs_present> block too; False → npc_director only.
    scene: bool = False
