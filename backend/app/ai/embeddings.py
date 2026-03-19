"""Embedding generation for pgvector semantic search."""

import httpx
import structlog

from app.config import settings

logger = structlog.get_logger()


async def generate_embedding(text: str) -> list[float] | None:
    """Generate a 384-dimensional embedding for text.

    Uses OpenAI embeddings API as default, falls back to None
    if no API key is configured (semantic search disabled).
    """
    if not settings.openai_api_key:
        logger.debug("embedding_skipped", reason="no_api_key")
        return None

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {settings.openai_api_key}"},
                json={
                    "input": text[:8000],  # Token limit safety
                    "model": "text-embedding-3-small",
                    "dimensions": 384,
                },
                timeout=10.0,
            )
            response.raise_for_status()
            data = response.json()
            return data["data"][0]["embedding"]
    except Exception:
        logger.exception("embedding_generation_failed")
        return None
