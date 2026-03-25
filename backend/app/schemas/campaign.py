import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.campaign import CampaignStatus, DeathMode


class CampaignCreate(BaseModel):
    template_id: str
    name: str
    death_mode: DeathMode
    character_data: dict = {}


class CampaignResponse(BaseModel):
    id: uuid.UUID
    name: str
    template_id: str
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
    narration: str
    dice_rolls: dict | None = None
    companion_actions: dict | None = None
    world_updates: dict | None = None
    scene_mood: str | None = None
    suggested_actions: list[str] | None = None
    model_used: str
    invoke_npcs: list[str] = []
    time_passed_minutes: int = 5
    ambient_detail: str | None = None
    requires_player_action: bool = True

    model_config = {"from_attributes": True}
