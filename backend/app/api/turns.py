from __future__ import annotations

import asyncio
import uuid
from typing import cast

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.generation_context import generation_context
from app.ai.prompts.dm import DMPromptContext
from app.ai.router import get_gameplay_config, validate_user_generation
from app.ai.session_affinity import campaign_session
from app.api.rate_limit import limiter, turns_limit
from app.core.action_policy import get_action_policy
from app.core.dm.dm_graph import dm_graph
from app.core.dm.game_state import GameState
from app.core.dm.loop_policy import recursion_limit
from app.dependencies import get_db
from app.exceptions import AIProviderError, ValidationError
from app.models.user import User
from app.schemas.campaign import TurnResponse, TurnSubmit
from app.security.auth import get_current_user
from app.services.action_claims import ActionClaim, claim_action, interrupt_action
from app.services.action_errors import ActionError
from app.services.action_persistence import publish_action

logger = structlog.get_logger()
router = APIRouter()


@router.post("/{campaign_id}/action", response_model=TurnResponse)
@limiter.limit(turns_limit)
async def submit_action(
    request: Request,
    campaign_id: uuid.UUID,
    body: TurnSubmit,
    user: User = Depends(get_current_user),
    auth_db: AsyncSession = Depends(get_db),
) -> TurnResponse:
    await auth_db.close()
    request.state.rate_limit_user_id = str(user.id)
    with generation_context(user.id), campaign_session(campaign_id):
        try:
            claim = await claim_action(campaign_id, user.id, body)
            if isinstance(claim, TurnResponse):
                return claim
            return await _execute_action(claim, body, user)
        except ActionError as exc:
            raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc


def _initial_state(claim: ActionClaim, body: TurnSubmit, user: User) -> GameState:
    context = claim.context
    return {
        "player_action": body.action,
        "campaign_id": str(claim.campaign_id),
        "user_id": str(user.id),
        "messages": [],
        "turn_context": context,
        "world_state": context.scene.world_state,
        "char_data": context.scene.character_data,
        "quests": context.scene.quests,
        "world_baseline": context.scene.world_baseline,
        "difficulty": context.difficulty,
        "narration": "",
        "narration_segments": [],
        "scene_mood": "neutral",
        "tool_events": [],
        "operations": [],
        "dice_results": [],
        "npc_beats": [],
        "npc_lines": [],
        "narrative_observations": [],
        "time_passed_minutes": 0,
        "model_used": "",
        "importance_score": 5,
        "step_count": 0,
        "max_agent_steps": get_gameplay_config().max_agent_steps,
        "consecutive_empty_steps": 0,
        "progress_fingerprints": [],
        "allowed_tools": [],
        "closing_step": False,
        "followup_required": False,
        "death_event": None,
        "system_prompt": "",
        "prompt_context": DMPromptContext(),
        "model_config": {},
    }


async def _execute_action(claim: ActionClaim, body: TurnSubmit, user: User) -> TurnResponse:
    try:
        validate_user_generation(user)
        initial = _initial_state(claim, body, user)
        async with asyncio.timeout(get_action_policy().timeout_seconds):
            state = cast(
                GameState,
                await dm_graph.ainvoke(
                    initial,
                    config={"recursion_limit": recursion_limit(initial["max_agent_steps"])},
                ),
            )
        return await publish_action(claim, body, state)
    except asyncio.CancelledError:
        await interrupt_action(
            claim, "The action was interrupted; submit a new action to continue."
        )
        raise
    except ActionError:
        await interrupt_action(claim, "The action context changed; refresh before continuing.")
        raise
    except TimeoutError as exc:
        await interrupt_action(claim, "The action exceeded its execution deadline.")
        raise HTTPException(
            status_code=504,
            detail={
                "code": "action_timeout",
                "message": "The action timed out without completing a turn.",
            },
        ) from exc
    except ValidationError as exc:
        await interrupt_action(claim, exc.message)
        raise HTTPException(status_code=422, detail=exc.message) from exc
    except AIProviderError as exc:
        await interrupt_action(claim, exc.message)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=exc.message) from exc
    except Exception as exc:
        await interrupt_action(claim, "DM processing failed")
        logger.exception("dm_graph_error", campaign_id=str(claim.campaign_id))
        raise HTTPException(status_code=500, detail="DM processing failed") from exc
