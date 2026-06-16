"""Unit tests for campaign_service template validation (B-M8)."""

import pytest
from fastapi import HTTPException

from app.models.template import Template
from app.services.campaign_service import _validate_template_content

_VALID = {
    "world": {
        "locations": [{"name": "Town"}],
        "npcs": [{"name": "Marta"}],
    },
    "opening": {"location": "Town"},
}


def _template(content: dict) -> Template:
    return Template(slug="t", content=content)


def test_valid_template_passes():
    _validate_template_content(_template(_VALID))  # should not raise


def test_missing_world_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_template_content(_template({"opening": {"location": "Town"}}))
    assert exc.value.status_code == 422
    assert "world" in exc.value.detail


def test_missing_opening_location_raises_422():
    with pytest.raises(HTTPException) as exc:
        _validate_template_content(_template({"world": {}, "opening": {}}))
    assert exc.value.status_code == 422
    assert "opening.location" in exc.value.detail


def test_world_entity_without_name_raises_422():
    bad = {"world": {"npcs": [{"role": "innkeeper"}]}, "opening": {"location": "Town"}}
    with pytest.raises(HTTPException) as exc:
        _validate_template_content(_template(bad))
    assert exc.value.status_code == 422
    assert "npcs" in exc.value.detail
