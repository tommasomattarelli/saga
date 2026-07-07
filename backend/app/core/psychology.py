"""ADR 0005 — band resolution + the bundled default psychology.

The default mirrors `worlds/the-awakening/taxonomy.yaml` (the copyable source
for new worlds) and is the fallback for taxonomies/baselines predating the
psychology block.
"""

from app.models.psychology import AxisBand, AxisDef, PsychologyDef


def _axis(*bands: tuple[int, str]) -> AxisDef:
    return AxisDef(bands=[AxisBand(min=m, label=label) for m, label in bands])


DEFAULT_PSYCHOLOGY = PsychologyDef(
    axes={
        "trust": _axis(
            (-100, "betrayed-wary"),
            (-30, "suspicious"),
            (-10, "neutral"),
            (30, "trusting"),
            (70, "confides fully"),
        ),
        "respect": _axis(
            (-100, "contemptuous"),
            (-30, "dismissive"),
            (-10, "neutral"),
            (30, "respectful"),
            (70, "in awe"),
        ),
        "affection": _axis(
            (-100, "loathing"),
            (-30, "cold"),
            (-10, "neutral"),
            (30, "fond"),
            (70, "devoted"),
        ),
        "fear": _axis(
            (-100, "fearless of you"),
            (-30, "at ease"),
            (-10, "neutral"),
            (30, "uneasy"),
            (70, "terrified"),
        ),
    }
)


def resolve_psychology(taxonomy: dict | None) -> PsychologyDef:
    block = (taxonomy or {}).get("psychology")
    return PsychologyDef(**block) if block else DEFAULT_PSYCHOLOGY


def _band(axis: AxisDef, value: int) -> AxisBand:
    current = axis.bands[0]
    for band in axis.bands:
        if value >= band.min:
            current = band
    return current


def band_label(axis: AxisDef, value: int) -> str:
    return _band(axis, value).label


def is_salient(axis: AxisDef, value: int) -> bool:
    return _band(axis, value) is not _band(axis, axis.default)


def default_values(pdef: PsychologyDef) -> dict[str, int]:
    return {name: axis.default for name, axis in pdef.axes.items()}
