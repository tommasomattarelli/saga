from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import ValidationError

from app.models.user import User
from app.schemas.campaign_export import CampaignExport
from app.security.auth import get_current_user
from app.services.campaign_export import CampaignExportNotFoundError, build_campaign_export
from app.services.export_validation import ExportIntegrityError

router = APIRouter()


@router.get("/{campaign_id}", response_model=CampaignExport)
async def export_campaign(
    campaign_id: UUID,
    user: User = Depends(get_current_user),
) -> CampaignExport:
    try:
        return await build_campaign_export(campaign_id, user.id)
    except CampaignExportNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Campaign not found") from exc
    except (ExportIntegrityError, ValidationError) as exc:
        raise HTTPException(
            status_code=500,
            detail={
                "code": "campaign_export_inconsistent",
                "message": "Campaign export could not be validated.",
            },
        ) from exc
