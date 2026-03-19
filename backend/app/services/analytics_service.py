"""Analytics service - opt-in telemetry."""

import structlog

from app.config import settings

logger = structlog.get_logger()


async def track_event(event_name: str, properties: dict | None = None) -> None:
    """Track an analytics event (opt-in only)."""
    if not settings.telemetry_enabled:
        return

    logger.info("analytics_event", event=event_name, properties=properties or {})
