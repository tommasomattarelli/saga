import { useTranslation } from "react-i18next";
import type { EditableWorld } from "../../../shared/api/client";
import { Area, Field, GhostButton, Picker } from "./editor-inputs";
import { PsychologySection } from "./forms-psychology";
import { NpcFieldsSection } from "./forms-npc-fields";

interface FormProps {
  payload: EditableWorld;
  onChange: (p: EditableWorld) => void;
}

export function MetaForm({ payload, onChange }: FormProps) {
  const { t } = useTranslation();
  const patchMeta = (patch: Partial<EditableWorld["meta"]>) =>
    onChange({ ...payload, meta: { ...payload.meta, ...patch } });

  return (
    <div className="space-y-4">
      <h2 className="font-display text-sm font-semibold" style={{ color: "var(--ink-primary)" }}>
        {t("worlds.section_meta")}
      </h2>
      <Field
        id="meta-name"
        label={t("worlds.name")}
        value={payload.meta.name}
        onChange={(e) => patchMeta({ name: e.target.value })}
      />
      <Field
        id="meta-author"
        label={t("worlds.author")}
        value={payload.meta.author}
        onChange={(e) => patchMeta({ author: e.target.value })}
      />
      <Field
        id="meta-version"
        label={t("worlds.version")}
        value={payload.meta.version}
        onChange={(e) => patchMeta({ version: e.target.value })}
      />
      <Area
        id="meta-description"
        label={t("worlds.description")}
        value={payload.meta.description}
        onChange={(e) => patchMeta({ description: e.target.value })}
      />
      <Field
        id="meta-tags"
        label={t("worlds.tags")}
        value={payload.meta.tags.join(", ")}
        onChange={(e) =>
          patchMeta({
            tags: e.target.value
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
          })
        }
      />
      <Area
        id="root-description"
        label={t("worlds.root_description")}
        value={(payload.root.description as string) ?? ""}
        onChange={(e) =>
          onChange({ ...payload, root: { ...payload.root, description: e.target.value } })
        }
      />
    </div>
  );
}

export function TaxonomyForm({ payload, onChange }: FormProps) {
  const { t } = useTranslation();
  const tax = payload.taxonomy;
  const patch = (patchTax: Partial<EditableWorld["taxonomy"]>) =>
    onChange({ ...payload, taxonomy: { ...tax, ...patchTax } });

  return (
    <div className="space-y-6">
      <h2 className="font-display text-sm font-semibold" style={{ color: "var(--ink-primary)" }}>
        {t("worlds.section_taxonomy")}
      </h2>

      <section className="space-y-2">
        <h3
          className="font-display text-xs font-semibold"
          style={{ color: "var(--ink-secondary)" }}
        >
          {t("worlds.kinds")}
        </h3>
        {tax.kinds.map((kind, i) => (
          <div key={i} className="flex items-end gap-2">
            <Field
              id={`kind-name-${i}`}
              label={t("worlds.kind_name")}
              value={kind.name}
              onChange={(e) => {
                const kinds = [...tax.kinds];
                kinds[i] = { ...kind, name: e.target.value };
                patch({ kinds });
              }}
            />
            <Picker
              id={`kind-scale-${i}`}
              label={t("worlds.kind_scale")}
              value={kind.scale}
              options={[
                { value: "outdoor", label: t("worlds.scale_outdoor") },
                { value: "interior", label: t("worlds.scale_interior") },
              ]}
              onChange={(e) => {
                const kinds = [...tax.kinds];
                kinds[i] = { ...kind, scale: e.target.value as "outdoor" | "interior" };
                patch({ kinds });
              }}
            />
            <GhostButton
              disabled={tax.kinds.length <= 1}
              onClick={() => patch({ kinds: tax.kinds.filter((_, j) => j !== i) })}
            >
              ✕
            </GhostButton>
          </div>
        ))}
        <GhostButton
          onClick={() => patch({ kinds: [...tax.kinds, { name: "", scale: "outdoor" }] })}
        >
          + {t("worlds.add")}
        </GhostButton>
      </section>

      <section className="space-y-2">
        <h3
          className="font-display text-xs font-semibold"
          style={{ color: "var(--ink-secondary)" }}
        >
          {t("worlds.terrains")}
        </h3>
        {tax.terrains.map((terrain, i) => (
          <div key={i} className="flex items-end gap-2">
            <Field
              id={`terrain-name-${i}`}
              label={t("worlds.terrain_name")}
              value={terrain.name}
              onChange={(e) => {
                const terrains = [...tax.terrains];
                terrains[i] = { ...terrain, name: e.target.value };
                patch({ terrains });
              }}
            />
            <Field
              id={`terrain-mult-${i}`}
              label={t("worlds.terrain_multiplier")}
              type="number"
              step="0.05"
              value={terrain.travel_multiplier}
              onChange={(e) => {
                const terrains = [...tax.terrains];
                terrains[i] = { ...terrain, travel_multiplier: Number(e.target.value) };
                patch({ terrains });
              }}
            />
            <GhostButton
              onClick={() => patch({ terrains: tax.terrains.filter((_, j) => j !== i) })}
            >
              ✕
            </GhostButton>
          </div>
        ))}
        <GhostButton
          onClick={() => patch({ terrains: [...tax.terrains, { name: "", travel_multiplier: 1 }] })}
        >
          + {t("worlds.add")}
        </GhostButton>
      </section>

      <section className="space-y-2">
        <h3
          className="font-display text-xs font-semibold"
          style={{ color: "var(--ink-secondary)" }}
        >
          {t("worlds.travel_modes")}
        </h3>
        {tax.travel_modes.map((mode, i) => (
          <div key={i} className="flex items-end gap-2">
            <Field
              id={`mode-name-${i}`}
              label={t("worlds.mode_name")}
              value={mode.name}
              onChange={(e) => {
                const travel_modes = [...tax.travel_modes];
                travel_modes[i] = { ...mode, name: e.target.value };
                patch({ travel_modes });
              }}
            />
            <Field
              id={`mode-speed-${i}`}
              label={t("worlds.mode_speed")}
              type="number"
              step="0.5"
              value={mode.speed_kmh}
              onChange={(e) => {
                const travel_modes = [...tax.travel_modes];
                travel_modes[i] = { ...mode, speed_kmh: Number(e.target.value) };
                patch({ travel_modes });
              }}
            />
            <GhostButton
              onClick={() => patch({ travel_modes: tax.travel_modes.filter((_, j) => j !== i) })}
            >
              ✕
            </GhostButton>
          </div>
        ))}
        <GhostButton
          onClick={() => patch({ travel_modes: [...tax.travel_modes, { name: "", speed_kmh: 4 }] })}
        >
          + {t("worlds.add")}
        </GhostButton>
      </section>

      <PsychologySection payload={payload} onChange={onChange} />

      <NpcFieldsSection payload={payload} onChange={onChange} />
    </div>
  );
}

export function ScenarioForm({ payload, onChange }: FormProps) {
  const { t } = useTranslation();
  const scenario = (payload.scenario ?? {
    opening: { narration: "", start_location: "", time_of_day: "", weather: "" },
    initial_quests: [],
    story_arcs: [],
  }) as {
    opening: { narration: string; start_location: string; time_of_day: string; weather: string };
    initial_quests: { name: string; description?: string; objectives?: string[] }[];
    story_arcs: { name: string; trigger?: string; description?: string }[];
    dm_persona?: string;
  };

  const patch = (next: typeof scenario) => onChange({ ...payload, scenario: next });
  const nodeOptions = payload.nodes.map((n) => ({ value: n.slug, label: n.name }));

  return (
    <div className="space-y-4">
      <h2 className="font-display text-sm font-semibold" style={{ color: "var(--ink-primary)" }}>
        {t("worlds.section_scenario")}
      </h2>
      <Area
        id="scenario-narration"
        label={t("worlds.opening_narration")}
        rows={8}
        value={scenario.opening.narration}
        onChange={(e) =>
          patch({ ...scenario, opening: { ...scenario.opening, narration: e.target.value } })
        }
      />
      <Picker
        id="scenario-start"
        label={t("worlds.start_location")}
        value={scenario.opening.start_location}
        options={nodeOptions}
        allowEmpty
        onChange={(e) =>
          patch({ ...scenario, opening: { ...scenario.opening, start_location: e.target.value } })
        }
      />
      <div className="grid grid-cols-2 gap-3">
        <Field
          id="scenario-time"
          label={t("worlds.time_of_day")}
          value={scenario.opening.time_of_day}
          onChange={(e) =>
            patch({ ...scenario, opening: { ...scenario.opening, time_of_day: e.target.value } })
          }
        />
        <Field
          id="scenario-weather"
          label={t("worlds.weather")}
          value={scenario.opening.weather}
          onChange={(e) =>
            patch({ ...scenario, opening: { ...scenario.opening, weather: e.target.value } })
          }
        />
      </div>
      <Area
        id="scenario-persona"
        label={t("worlds.dm_persona")}
        value={scenario.dm_persona ?? ""}
        onChange={(e) => patch({ ...scenario, dm_persona: e.target.value })}
      />
    </div>
  );
}
