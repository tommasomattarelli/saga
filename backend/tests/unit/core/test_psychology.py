"""ADR 0005 S1 — psychology vocabulary models, band resolver, bundled default."""

import pytest
import yaml
from pydantic import ValidationError

from app.core.psychology import (
    DEFAULT_PSYCHOLOGY,
    band_label,
    default_values,
    is_salient,
    resolve_psychology,
)
from app.models.psychology import AxisDef, PsychologyDef

AXIS = {
    "range": [-100, 100],
    "default": 0,
    "bands": [
        {"min": -100, "label": "hostile"},
        {"min": -10, "label": "neutral"},
        {"min": 30, "label": "warm"},
    ],
}


class TestModels:
    def test_axis_parses(self):
        axis = AxisDef(**AXIS)
        assert axis.range == (-100, 100)
        assert [b.label for b in axis.bands] == ["hostile", "neutral", "warm"]

    def test_default_outside_range_rejected(self):
        with pytest.raises(ValidationError):
            AxisDef(**{**AXIS, "default": 500})

    def test_band_mins_must_increase(self):
        bad = {**AXIS, "bands": [{"min": 30, "label": "a"}, {"min": -10, "label": "b"}]}
        with pytest.raises(ValidationError):
            AxisDef(**bad)

    def test_band_min_outside_range_rejected(self):
        bad = {**AXIS, "bands": [{"min": -300, "label": "a"}]}
        with pytest.raises(ValidationError):
            AxisDef(**bad)

    def test_psychology_requires_axes(self):
        with pytest.raises(ValidationError):
            PsychologyDef(axes={})

    def test_tuning_defaults(self):
        pdef = PsychologyDef(axes={"trust": AXIS})
        assert pdef.first_impression_multiplier == 3.0
        assert pdef.max_delta_per_turn == 10


class TestBandResolver:
    def test_label_picks_band(self):
        axis = AxisDef(**AXIS)
        assert band_label(axis, -50) == "hostile"
        assert band_label(axis, 0) == "neutral"
        assert band_label(axis, 30) == "warm"
        assert band_label(axis, 100) == "warm"

    def test_value_below_first_band_uses_first(self):
        axis = AxisDef(**{**AXIS, "bands": [{"min": 0, "label": "only"}]})
        assert band_label(axis, -100) == "only"

    def test_salient_is_outside_default_band(self):
        axis = AxisDef(**AXIS)
        assert not is_salient(axis, 0)
        assert not is_salient(axis, 20)  # still in the default band
        assert is_salient(axis, 30)
        assert is_salient(axis, -50)


class TestDefaults:
    def test_bundled_default_axes(self):
        assert set(DEFAULT_PSYCHOLOGY.axes) == {"trust", "respect", "affection", "fear"}

    def test_default_values_all_zero(self):
        assert default_values(DEFAULT_PSYCHOLOGY) == {
            "trust": 0,
            "respect": 0,
            "affection": 0,
            "fear": 0,
        }

    def test_resolve_falls_back_without_block(self):
        assert resolve_psychology(None) is DEFAULT_PSYCHOLOGY
        assert resolve_psychology({"kinds": []}) is DEFAULT_PSYCHOLOGY

    def test_resolve_reads_taxonomy_block(self):
        pdef = resolve_psychology({"psychology": {"axes": {"honor": AXIS}}})
        assert set(pdef.axes) == {"honor"}

    def test_example_world_ships_the_default(self, example_taxonomy_path):
        data = yaml.safe_load(example_taxonomy_path.read_text())
        assert PsychologyDef(**data["psychology"]) == DEFAULT_PSYCHOLOGY


@pytest.fixture
def example_taxonomy_path(request):
    path = request.config.rootpath.parent / "worlds" / "the-awakening" / "taxonomy.yaml"
    assert path.exists()
    return path
