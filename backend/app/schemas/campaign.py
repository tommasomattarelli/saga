import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.campaign import CampaignStatus, DeathMode


class CampaignCreate(BaseModel):
    world_id: str
    name: str
    death_mode: DeathMode
    character_data: dict = {}


class CampaignResponse(BaseModel):
    id: uuid.UUID
    name: str
    world_slug: str
    status: CampaignStatus
    death_mode: DeathMode
    turn_number: int
    character_data: dict
    world_state: dict
    quests: dict
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TurnSubmit(BaseModel):
    action: str


class TurnResponse(BaseModel):
    turn_number: int
    player_action: str = ""
    narration: str
    narration_segments: list[dict] | None = None
    # dice_results: pre-rolled by server, frontend animates as clickable UX
    dice_results: list[dict] | None = None
    # kept for backward-compat with journal endpoint
    dice_rolls: dict | None = None
    npc_dialogues: list[dict] | None = None
    world_state: dict = {}
    character_data: dict = {}
    scene_mood: str | None = None
    tool_events: list[dict] = []
    death_event: dict | None = None
    model_used: str
    importance_score: int = 5
    time_passed_minutes: int = 0
    requires_player_action: bool = True

    model_config = {"from_attributes": True}
