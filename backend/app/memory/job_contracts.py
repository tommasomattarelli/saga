import uuid

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator


class MemoryJobManifest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    instruction_text: StrictStr = Field(min_length=1)
    instruction_version: StrictStr = Field(min_length=1)
    source_turn_ids: tuple[uuid.UUID, ...] = Field(min_length=1)
    source_hash: StrictStr = Field(pattern=r"^[0-9a-f]{64}$")
    language: StrictStr = Field(min_length=1)

    @field_validator("source_turn_ids", mode="before")
    @classmethod
    def parse_json_source_ids(cls, value: object) -> object:
        if not isinstance(value, (list, tuple)):
            return value
        return tuple(uuid.UUID(item) if isinstance(item, str) else item for item in value)
