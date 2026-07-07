"""ADR 0005 — world-defined NPC psychology vocabulary (axes, bands, tuning)."""

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AxisBand(BaseModel):
    model_config = ConfigDict(extra="forbid")

    min: int
    label: str


class AxisDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    range: tuple[int, int] = (-100, 100)
    default: int = 0
    bands: list[AxisBand] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_bounds(self) -> "AxisDef":
        lo, hi = self.range
        if lo >= hi:
            raise ValueError("range min must be below max")
        if not lo <= self.default <= hi:
            raise ValueError(f"default {self.default} outside range [{lo}, {hi}]")
        mins = [b.min for b in self.bands]
        if mins != sorted(set(mins)):
            raise ValueError("band mins must be strictly increasing")
        if mins[0] < lo or mins[-1] > hi:
            raise ValueError(f"band min outside range [{lo}, {hi}]")
        return self


class PsychologyDef(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_impression_multiplier: float = Field(default=3.0, gt=0)
    max_delta_per_turn: int = Field(default=10, gt=0)
    axes: dict[str, AxisDef] = Field(min_length=1)
