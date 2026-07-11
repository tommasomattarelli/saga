import { useTranslation } from "react-i18next";
import type { EditableWorld, NpcFieldDef } from "../../../shared/api/client";
import { Field, GhostButton } from "./editor-inputs";

/* Mirror of the engine's bundled default (backend `core/npc_fields.py`) —
   materialized when a pre-0009 world starts customizing its NPC fields. */
export const DEFAULT_NPC_FIELDS: NpcFieldDef[] = [
  { name: "role", default: "Commoner", scene: true },
  { name: "appearance", scene: true },
  { name: "personality" },
  { name: "motivation" },
  { name: "background" },
  { name: "ideal" },
  { name: "bond" },
  { name: "flaw" },
  { name: "mannerisms" },
  { name: "secret" },
  { name: "dreads" },
];

interface Props {
  payload: EditableWorld;
  onChange: (p: EditableWorld) => void;
}

/* ADR 0009 G5: removing a declared field prunes its value from every authored
   NPC (behind a confirm); renaming carries the values over. */
export function NpcFieldsSection({ payload, onChange }: Props) {
  const { t } = useTranslation();
  const npcFields = payload.taxonomy.npc_fields;
  const patch = (next: NpcFieldDef[], npcs = payload.npcs) =>
    onChange({ ...payload, npcs, taxonomy: { ...payload.taxonomy, npc_fields: next } });

  if (!npcFields) {
    return (
      <section className="space-y-2">
        <h3
          className="font-display text-xs font-semibold"
          style={{ color: "var(--ink-secondary)" }}
        >
          {t("worlds.npc_fields")}
        </h3>
        <p className="text-xs" style={{ color: "var(--ink-secondary)" }}>
          {t("worlds.npc_fields_hint")}
        </p>
        <GhostButton onClick={() => patch(structuredClone(DEFAULT_NPC_FIELDS))}>
          + {t("worlds.npc_fields_customize")}
        </GhostButton>
      </section>
    );
  }

  const patchField = (i: number, field: NpcFieldDef) =>
    patch(npcFields.map((f, j) => (j === i ? field : f)));

  const renameField = (i: number, to: string) => {
    const from = npcFields[i].name;
    const npcs = payload.npcs.map((npc) => {
      if (!(from in npc)) return npc;
      const { [from]: value, ...rest } = npc;
      return { ...rest, [to]: value };
    });
    patch(
      npcFields.map((f, j) => (j === i ? { ...f, name: to } : f)),
      npcs,
    );
  };

  const removeField = (i: number) => {
    const name = npcFields[i].name;
    const affected = payload.npcs.filter((npc) => name in npc).length;
    if (affected > 0 && !window.confirm(t("worlds.npc_field_remove_confirm", { count: affected })))
      return;
    const npcs = payload.npcs.map((npc) => {
      const rest = { ...npc };
      delete rest[name];
      return rest;
    });
    patch(
      npcFields.filter((_, j) => j !== i),
      npcs,
    );
  };

  return (
    <section className="space-y-3">
      <h3 className="font-display text-xs font-semibold" style={{ color: "var(--ink-secondary)" }}>
        {t("worlds.npc_fields")}
      </h3>
      {npcFields.map((field, i) => (
        <div key={i} className="flex items-end gap-2">
          <Field
            id={`npc-field-name-${i}`}
            label={t("worlds.field_name")}
            value={field.name}
            onChange={(e) => renameField(i, e.target.value)}
          />
          <Field
            id={`npc-field-default-${i}`}
            label={t("worlds.field_default")}
            value={field.default ?? ""}
            onChange={(e) => patchField(i, { ...field, default: e.target.value || undefined })}
          />
          <label
            className="flex items-center gap-1 pb-2 text-xs"
            style={{ color: "var(--ink-secondary)" }}
            htmlFor={`npc-field-scene-${i}`}
          >
            <input
              id={`npc-field-scene-${i}`}
              type="checkbox"
              checked={field.scene ?? false}
              onChange={(e) => patchField(i, { ...field, scene: e.target.checked || undefined })}
            />
            {t("worlds.field_scene")}
          </label>
          <GhostButton disabled={npcFields.length <= 1} onClick={() => removeField(i)}>
            ✕
          </GhostButton>
        </div>
      ))}
      <GhostButton onClick={() => patch([...npcFields, { name: "" }])}>
        + {t("worlds.add_npc_field")}
      </GhostButton>
    </section>
  );
}
