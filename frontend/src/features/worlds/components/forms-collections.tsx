import { useTranslation } from "react-i18next";
import type { EditableWorld } from "../../../shared/api/client";
import type { Selection } from "./editor-nav";
import { Area, Field, GhostButton, Picker } from "./editor-inputs";
import { DEFAULT_PSYCHOLOGY } from "./forms-psychology";

interface Props {
  payload: EditableWorld;
  kind: "edge" | "faction" | "npc" | "encounter";
  slug: string;
  onChange: (p: EditableWorld) => void;
  onSelect: (s: Selection) => void;
}

/* Forms for the flat collections; references always go through pickers (I4). */
export function CollectionForm({ payload, kind, slug, onChange, onSelect }: Props) {
  const { t } = useTranslation();
  const key = `${kind}s` as "edges" | "factions" | "npcs" | "encounters";
  const entity = payload[key].find((e) => e.slug === slug);
  if (!entity) return null;

  const patch = (patchEntity: Record<string, unknown>) =>
    onChange({
      ...payload,
      [key]: payload[key].map((e) => (e.slug === slug ? { ...e, ...patchEntity } : e)),
    });

  const remove = () => {
    onChange({ ...payload, [key]: payload[key].filter((e) => e.slug !== slug) });
    onSelect({ type: "meta" });
  };

  const nodeOptions = payload.nodes.map((n) => ({ value: n.slug, label: n.name }));
  const value = (field: string) => (entity[field] as string) ?? "";

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-sm font-semibold" style={{ color: "var(--ink-primary)" }}>
          {(entity.name as string) ?? slug}
        </h2>
        <GhostButton onClick={remove}>{t("worlds.delete_entity")}</GhostButton>
      </div>

      <Field
        id="entity-slug"
        label={t("worlds.slug")}
        value={slug}
        onChange={(e) => {
          patch({ slug: e.target.value });
          onSelect({ type: kind, slug: e.target.value });
        }}
      />

      {kind === "edge" && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Picker
              id="edge-from"
              label={t("worlds.edge_from")}
              value={value("from")}
              options={nodeOptions}
              onChange={(e) => patch({ from: e.target.value })}
            />
            <Picker
              id="edge-to"
              label={t("worlds.edge_to")}
              value={value("to")}
              options={nodeOptions}
              onChange={(e) => patch({ to: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-3 gap-3">
            <Picker
              id="edge-mode"
              label={t("worlds.mode")}
              value={value("mode")}
              options={payload.taxonomy.travel_modes.map((m) => ({
                value: m.name,
                label: m.name,
              }))}
              onChange={(e) => patch({ mode: e.target.value })}
            />
            <Picker
              id="edge-terrain"
              label={t("worlds.terrain")}
              value={value("terrain")}
              options={payload.taxonomy.terrains.map((tr) => ({ value: tr.name, label: tr.name }))}
              allowEmpty
              onChange={(e) => patch({ terrain: e.target.value || undefined })}
            />
            <Field
              id="edge-time"
              label={t("worlds.travel_time")}
              type="number"
              step="0.25"
              value={(entity.travel_time as number) ?? ""}
              onChange={(e) =>
                patch({ travel_time: e.target.value === "" ? undefined : Number(e.target.value) })
              }
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Picker
              id="edge-table"
              label={t("worlds.encounter_table")}
              value={value("encounter_table")}
              options={payload.encounters.map((en) => ({
                value: en.slug as string,
                label: en.slug as string,
              }))}
              allowEmpty
              onChange={(e) => patch({ encounter_table: e.target.value || undefined })}
            />
            <Field
              id="edge-chance"
              label={t("worlds.encounter_chance")}
              type="number"
              step="0.05"
              min={0}
              max={1}
              value={(entity.encounter_chance as number) ?? ""}
              onChange={(e) =>
                patch({
                  encounter_chance: e.target.value === "" ? undefined : Number(e.target.value),
                })
              }
            />
          </div>
        </>
      )}

      {kind === "faction" && (
        <>
          <Field
            id="faction-name"
            label={t("worlds.name")}
            value={value("name")}
            onChange={(e) => patch({ name: e.target.value })}
          />
          <Area
            id="faction-description"
            label={t("worlds.description")}
            value={value("description")}
            onChange={(e) => patch({ description: e.target.value })}
          />
          <Area
            id="faction-goals"
            label={t("worlds.goals")}
            rows={3}
            value={((entity.goals as string[]) ?? []).join("\n")}
            onChange={(e) => patch({ goals: e.target.value.split("\n").filter(Boolean) })}
          />
        </>
      )}

      {kind === "npc" && (
        <>
          <div className="grid grid-cols-2 gap-3">
            <Field
              id="npc-name"
              label={t("worlds.name")}
              value={value("name")}
              onChange={(e) => patch({ name: e.target.value })}
            />
            <Field
              id="npc-role"
              label={t("worlds.role")}
              value={value("role")}
              onChange={(e) => patch({ role: e.target.value })}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <Picker
              id="npc-location"
              label={t("worlds.location")}
              value={value("location")}
              options={nodeOptions}
              allowEmpty
              onChange={(e) => patch({ location: e.target.value || undefined })}
            />
            <Picker
              id="npc-faction"
              label={t("worlds.faction")}
              value={value("faction")}
              options={payload.factions.map((f) => ({
                value: f.slug as string,
                label: (f.name as string) ?? (f.slug as string),
              }))}
              allowEmpty
              onChange={(e) => patch({ faction: e.target.value || undefined })}
            />
          </div>
          <Area
            id="npc-personality"
            label={t("worlds.personality")}
            rows={2}
            value={value("personality")}
            onChange={(e) => patch({ personality: e.target.value })}
          />
          <Area
            id="npc-motivation"
            label={t("worlds.motivation")}
            rows={2}
            value={value("motivation")}
            onChange={(e) => patch({ motivation: e.target.value })}
          />
          <Area
            id="npc-secret"
            label={t("worlds.secret")}
            rows={2}
            value={value("secret")}
            onChange={(e) => patch({ secret: e.target.value })}
          />
          <div className="space-y-1">
            <span className="text-xs" style={{ color: "var(--ink-secondary)" }}>
              {t("worlds.npc_psychology")}
            </span>
            <div className="grid grid-cols-4 gap-2">
              {Object.keys((payload.taxonomy.psychology ?? DEFAULT_PSYCHOLOGY).axes).map((axis) => {
                const seeds = (entity.psychology as Record<string, number>) ?? {};
                return (
                  <Field
                    key={axis}
                    id={`npc-psy-${axis}`}
                    label={axis}
                    type="number"
                    value={seeds[axis] ?? ""}
                    onChange={(e) => {
                      const next = { ...seeds };
                      if (e.target.value === "") delete next[axis];
                      else next[axis] = Number(e.target.value);
                      patch({ psychology: Object.keys(next).length ? next : undefined });
                    }}
                  />
                );
              })}
            </div>
          </div>
        </>
      )}

      {kind === "encounter" && (
        <>
          <Field
            id="encounter-dice"
            label={t("worlds.dice")}
            value={value("dice")}
            onChange={(e) => patch({ dice: e.target.value })}
          />
          {((entity.entries as Record<string, unknown>[]) ?? []).map((entry, i) => {
            const entries = [...((entity.entries as Record<string, unknown>[]) ?? [])];
            const roll = (entry.roll as [number, number]) ?? [1, 1];
            return (
              <div key={i} className="flex items-end gap-2">
                <Field
                  id={`entry-low-${i}`}
                  label={t("worlds.roll_min")}
                  type="number"
                  value={roll[0]}
                  onChange={(e) => {
                    entries[i] = { ...entry, roll: [Number(e.target.value), roll[1]] };
                    patch({ entries });
                  }}
                />
                <Field
                  id={`entry-high-${i}`}
                  label={t("worlds.roll_max")}
                  type="number"
                  value={roll[1]}
                  onChange={(e) => {
                    entries[i] = { ...entry, roll: [roll[0], Number(e.target.value)] };
                    patch({ entries });
                  }}
                />
                <Picker
                  id={`entry-type-${i}`}
                  label={t("worlds.entry_type")}
                  value={(entry.type as string) ?? "event"}
                  options={[
                    { value: "event", label: t("worlds.type_event") },
                    { value: "combat", label: t("worlds.type_combat") },
                  ]}
                  onChange={(e) => {
                    entries[i] = { ...entry, type: e.target.value };
                    patch({ entries });
                  }}
                />
                <Field
                  id={`entry-desc-${i}`}
                  label={t("worlds.description")}
                  value={(entry.description as string) ?? ""}
                  onChange={(e) => {
                    entries[i] = { ...entry, description: e.target.value };
                    patch({ entries });
                  }}
                />
                <GhostButton onClick={() => patch({ entries: entries.filter((_, j) => j !== i) })}>
                  ✕
                </GhostButton>
              </div>
            );
          })}
          <GhostButton
            onClick={() =>
              patch({
                entries: [
                  ...((entity.entries as Record<string, unknown>[]) ?? []),
                  { roll: [1, 1], type: "event", description: "" },
                ],
              })
            }
          >
            + {t("worlds.add")}
          </GhostButton>
        </>
      )}
    </div>
  );
}
