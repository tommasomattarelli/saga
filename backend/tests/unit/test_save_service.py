"""Unit tests for app/services/save_service.py."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.save_service import get_campaign_saves


class TestGetCampaignSaves:
    @pytest.mark.asyncio
    async def test_returns_list_of_saves(self):
        save1 = MagicMock()
        save2 = MagicMock()

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [save1, save2]
        mock_db.execute.return_value = mock_result

        campaign_id = uuid.uuid4()
        result = await get_campaign_saves(campaign_id, mock_db)

        assert result == [save1, save2]
        mock_db.execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_saves(self):
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        campaign_id = uuid.uuid4()
        result = await get_campaign_saves(campaign_id, mock_db)

        assert result == []
