"""Save schemas."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class SaveCreate(BaseModel):
    """Create a manual save."""

    name: str


class SaveResponse(BaseModel):
    """Save info."""

    id: uuid.UUID
    campaign_id: uuid.UUID
    name: str
    turn_number: int
    scene_summary: str
    is_auto: bool
    created_at: datetime

    model_config = {"from_attributes": True}
