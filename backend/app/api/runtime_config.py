from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from app.core.action_policy import get_action_policy
from app.models.user import User
from app.security.auth import get_current_user

router = APIRouter()
PositiveFiniteSeconds = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class RuntimeConfigResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    action_client_timeout_seconds: PositiveFiniteSeconds


@router.get("/runtime-config", response_model=RuntimeConfigResponse)
async def get_runtime_config(user: User = Depends(get_current_user)) -> RuntimeConfigResponse:
    del user
    policy = get_action_policy()
    return RuntimeConfigResponse(action_client_timeout_seconds=policy.client_timeout_seconds)
