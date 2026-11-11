from __future__ import annotations

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config_loader import load_saga_config

PositiveFinite = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class ActionPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, allow_inf_nan=False)

    timeout_seconds: PositiveFinite
    completion_margin_seconds: PositiveFinite
    proxy_margin_seconds: PositiveFinite
    admission_wait_seconds: PositiveFinite

    @model_validator(mode="after")
    def validate_margins(self) -> Self:
        if self.completion_margin_seconds <= self.admission_wait_seconds:
            raise ValueError("action completion margin must exceed memory admission wait")
        if self.proxy_margin_seconds <= self.completion_margin_seconds:
            raise ValueError("action proxy margin must exceed action completion margin")
        return self

    @property
    def execution_lease_seconds(self) -> float:
        return self.timeout_seconds + self.completion_margin_seconds

    @property
    def client_timeout_seconds(self) -> float:
        return self.execution_lease_seconds

    @property
    def proxy_timeout_seconds(self) -> float:
        return self.timeout_seconds + self.proxy_margin_seconds


def get_action_policy() -> ActionPolicy:
    config = load_saga_config()
    gameplay = config["gameplay"]
    admission_wait = config["memory"]["production"]["admission"]["wait_timeout_seconds"]
    return ActionPolicy.model_validate(
        {
            "timeout_seconds": gameplay["action_timeout_seconds"],
            "completion_margin_seconds": gameplay["action_completion_margin_seconds"],
            "proxy_margin_seconds": gameplay["action_proxy_margin_seconds"],
            "admission_wait_seconds": admission_wait,
        }
    )
