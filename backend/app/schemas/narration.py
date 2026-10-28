from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class TextPart(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["text"] = "text"
    text: str


class NPCSpeechPart(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    type: Literal["npc_speech"] = "npc_speech"
    npc_id: str
    npc_name: str
    line_index: int
    dialogue: str


NarrationPart = Annotated[TextPart | NPCSpeechPart, Field(discriminator="type")]


class NarrationSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step: int
    dice: dict[str, dict[str, object]] | None = None
    parts: list[NarrationPart]
