"""Campaign template endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.models.template import Template

router = APIRouter()


@router.get("")
async def list_templates(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """List available campaign templates."""
    result = await db.execute(select(Template).order_by(Template.name))
    templates = result.scalars().all()
    return [
        {
            "id": str(t.id),
            "slug": t.slug,
            "name": t.name,
            "description": t.description,
            "author": t.author,
            "difficulty": t.difficulty,
            "tags": t.tags,
        }
        for t in templates
    ]


@router.get("/{slug}")
async def get_template(slug: str, db: AsyncSession = Depends(get_db)) -> dict:
    """Get a template by slug."""
    result = await db.execute(select(Template).where(Template.slug == slug))
    template = result.scalar_one_or_none()
    if not template:
        from fastapi import HTTPException, status

        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    return {
        "id": str(template.id),
        "slug": template.slug,
        "name": template.name,
        "description": template.description,
        "author": template.author,
        "difficulty": template.difficulty,
        "tags": template.tags,
        "content": template.content,
    }
