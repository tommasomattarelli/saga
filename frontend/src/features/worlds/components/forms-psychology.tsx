import { useTranslation } from "react-i18next";
import type { EditableWorld, PsychologyAxis, PsychologyDef } from "../../../shared/api/client";
import { Field, GhostButton } from "./editor-inputs";

/* Mirror of the engine's bundled default (backend `core/psychology.py`) —
   materialized when a pre-0005 world starts customizing its axes. */
const DEFAULT_BANDS: Record<string, [number, string][]> = {
  trust: [
    [-100, "betrayed-wary"],
    [-30, "suspicious"],
    [-10, "neutral"],
    [30, "trusting"],
    [70, "confides fully"],
  ],
  respect: [
    [-100, "contemptuous"],
    [-30, "dismissive"],
    [-10, "neutral"],
    [30, "respectful"],
    [70, "in awe"],
  ],
  affection: [
    [-100, "loathing"],
    [-30, "cold"],
    [-10, "neutral"],
    [30, "fond"],
    [70, "devoted"],
  ],
  fear: [
    [-100, "fearless of you"],
    [-30, "at ease"],
    [-10, "neutral"],
    [30, "uneasy"],
    [70, "terrified"],
  ],
};

export const DEFAULT_PSYCHOLOGY: PsychologyDef = {
  first_impression_multiplier: 3.0,
  max_delta_per_turn: 10,
  axes: Object.fromEntries(
    Object.entries(DEFAULT_BANDS).map(([name, bands]) => [
      name,
      {
        range: [-100, 100] as [number, number],
        default: 0,
        bands: bands.map(([min, label]) => ({ min, label })),
      },
    ]),
  ),
};

interface Props {
  payload: EditableWorld;
  onChange: (p: EditableWorld) => void;
}

export function PsychologySection({ payload, onChange }: Props) {
  const { t } = useTranslation();
  const psychology = payload.taxonomy.psychology;
  const patch = (next: PsychologyDef, npcs = payload.npcs) =>
    onChange({ ...payload, npcs, taxonomy: { ...payload.taxonomy, psychology: next } });

  if (!psychology) {
    return (
      <section className="space-y-2">
        <h3
          className="font-display text-xs font-semibold"
          style={{ color: "var(--ink-secondary)" }}
        >
          {t("worlds.psychology")}
        </h3>
        <p className="text-xs" style={{ color: "var(--ink-secondary)" }}>
          {t("worlds.psychology_hint")}
        </p>
        <GhostButton onClick={() => patch(structuredClone(DEFAULT_PSYCHOLOGY))}>
          + {t("worlds.psychology_customize")}
        </GhostButton>
      </section>
    );
  }

  const patchAxis = (name: string, axis: PsychologyAxis) =>
    patch({ ...psychology, axes: { ...psychology.axes, [name]: axis } });

  const seedsOf = (npc: Record<string, unknown>) =>
    (npc.psychology as Record<string, number> | undefined) ?? {};

  const renameAxis = (from: string, to: string) => {
    // ADR 0009 G5: carry authored seeds over so no orphan value is left behind.
    const npcs = payload.npcs.map((npc) => {
      const seeds = seedsOf(npc);
      if (!(from in seeds)) return npc;
      const { [from]: value, ...rest } = seeds;
      return { ...npc, psychology: { ...rest, [to]: value } };
    });
    patch(
      {
        ...psychology,
        axes: Object.fromEntries(
          Object.entries(psychology.axes).map(([k, v]) => [k === from ? to : k, v]),
        ),
      },
      npcs,
    );
  };

  const removeAxis = (name: string) => {
    // ADR 0009 G5: prune authored seeds (a stale seed makes tier-3 reject the world).
    const affected = payload.npcs.filter((npc) => name in seedsOf(npc)).length;
    if (affected > 0 && !window.confirm(t("worlds.axis_remove_confirm", { count: affected })))
      return;
    const npcs = payload.npcs.map((npc) => {
      const rest = { ...seedsOf(npc) };
      delete rest[name];
      return { ...npc, psychology: Object.keys(rest).length ? rest : undefined };
    });
    const axes = { ...psychology.axes };
    delete axes[name];
    patch({ ...psychology, axes }, npcs);
  };

  return (
    <section className="space-y-3">
      <h3 className="font-display text-xs font-semibold" style={{ color: "var(--ink-secondary)" }}>
        {t("worlds.psychology")}
      </h3>
      <div className="grid grid-cols-2 gap-3">
        <Field
          id="psy-multiplier"
          label={t("worlds.first_impression")}
          type="number"
          step="0.5"
          value={psychology.first_impression_multiplier}
          onChange={(e) =>
            patch({ ...psychology, first_impression_multiplier: Number(e.target.value) })
          }
        />
        <Field
          id="psy-cap"
          label={t("worlds.max_delta")}
          type="number"
          value={psychology.max_delta_per_turn}
          onChange={(e) => patch({ ...psychology, max_delta_per_turn: Number(e.target.value) })}
        />
      </div>

      {Object.entries(psychology.axes).map(([name, axis], i) => (
        <div
          key={i}
          className="space-y-2 rounded border p-2"
          style={{ borderColor: "var(--line)" }}
        >
          <div className="flex items-end gap-2">
            <Field
              id={`axis-name-${i}`}
              label={t("worlds.axis_name")}
              value={name}
              onChange={(e) => renameAxis(name, e.target.value)}
            />
            <Field
              id={`axis-min-${i}`}
              label={t("worlds.range_min")}
              type="number"
              value={axis.range[0]}
              onChange={(e) =>
                patchAxis(name, { ...axis, range: [Number(e.target.value), axis.range[1]] })
              }
            />
            <Field
              id={`axis-max-${i}`}
              label={t("worlds.range_max")}
              type="number"
              value={axis.range[1]}
              onChange={(e) =>
                patchAxis(name, { ...axis, range: [axis.range[0], Number(e.target.value)] })
              }
            />
            <Field
              id={`axis-default-${i}`}
              label={t("worlds.axis_default")}
              type="number"
              value={axis.default}
              onChange={(e) => patchAxis(name, { ...axis, default: Number(e.target.value) })}
            />
            <GhostButton
              disabled={Object.keys(psychology.axes).length <= 1}
              onClick={() => removeAxis(name)}
            >
              ✕
            </GhostButton>
          </div>
          {axis.bands.map((band, j) => (
            <div key={j} className="flex items-end gap-2 pl-4">
              <Field
                id={`axis-${i}-band-min-${j}`}
                label={t("worlds.band_min")}
                type="number"
                value={band.min}
                onChange={(e) => {
                  const bands = [...axis.bands];
                  bands[j] = { ...band, min: Number(e.target.value) };
                  patchAxis(name, { ...axis, bands });
                }}
              />
              <Field
                id={`axis-${i}-band-label-${j}`}
                label={t("worlds.band_label")}
                value={band.label}
                onChange={(e) => {
                  const bands = [...axis.bands];
                  bands[j] = { ...band, label: e.target.value };
                  patchAxis(name, { ...axis, bands });
                }}
              />
              <GhostButton
                disabled={axis.bands.length <= 1}
                onClick={() =>
                  patchAxis(name, { ...axis, bands: axis.bands.filter((_, k) => k !== j) })
                }
              >
                ✕
              </GhostButton>
            </div>
          ))}
          <GhostButton
            onClick={() =>
              patchAxis(name, {
                ...axis,
                bands: [
                  ...axis.bands,
                  { min: axis.bands[axis.bands.length - 1].min + 10, label: "" },
                ],
              })
            }
          >
            + {t("worlds.add")}
          </GhostButton>
        </div>
      ))}
      <GhostButton
        onClick={() =>
          patch({
            ...psychology,
            axes: {
              ...psychology.axes,
              "": { range: [-100, 100], default: 0, bands: [{ min: -100, label: "neutral" }] },
            },
          })
        }
      >
        + {t("worlds.add_axis")}
      </GhostButton>
    </section>
  );
}
