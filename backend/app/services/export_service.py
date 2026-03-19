"""Export service - data portability."""


def format_campaign_export(campaign_data: dict, turns_data: list[dict]) -> dict:
    """Format campaign data for export."""
    return {
        "version": "1.0",
        "format": "saga-export",
        "campaign": campaign_data,
        "turns": turns_data,
    }
