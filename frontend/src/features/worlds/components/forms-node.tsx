import { useTranslation } from "react-i18next";
import type { EditableNode, EditableWorld, ParamDef } from "../../../shared/api/client";
import type { Selection } from "./editor-nav";
import { Area, Field, GhostButton, Picker } from "./editor-inputs";

interface Props {
  payload: EditableWorld;
  slug: string;
  onChange: (p: EditableWorld) => void;
  onSelect: (s: Selection) => void;
}

/* Node form — fields driven by the world's own taxonomy (ADR 0008 P0/I7). */
export function NodeForm({ payload, slug, onChange, onSelect }: Props) {
  const { t } = useTranslation();
  const node = payload.nodes.find((n) => n.slug === slug);
  if (!node) return null;

  const kindDef = payload.taxonomy.kinds.find((k) => k.name === node.kind);
  const outdoor = kindDef?.scale === "outdoor";

  const patch = (patchNode: Partial<EditableNode>) =>
    onChange({
      ...payload,
      nodes: payload.nodes.map((n) => (n.slug === slug ? { ...n, ...patchNode } : n)),
    });

  const remove = () => {
    const doomed = new Set([slug]);
    let grew = true;
    while (grew) {
      grew = false;
      for (const n of payload.nodes) {
        if (n.parent && doomed.has(n.parent) && !doomed.has(n.slug)) {
          doomed.add(n.slug);
          grew = true;
        }
      }
    }
    onChange({ ...payload, nodes: payload.nodes.filter((n) => !doomed.has(n.slug)) });
    onSelect({ type: "meta" });
  };

  const parentOptions = [
    { value: "", label: t("worlds.parent_root") },
    ...payload.nodes.filter((n) => n.slug !== slug).map((n) => ({ value: n.slug, label: n.name })),
  ];
  const terrainOptions = payload.taxonomy.terrains.map((tr) => ({
    value: tr.name,
    label: tr.name,
  }));
  const interiorSiblings = payload.nodes
    .filter((n) => n.slug !== slug)
    .map((n) => ({ value: n.slug, label: n.name }));

  const setParam = (def: ParamDef, raw: string | boolean) => {
    const params = { ...(node.params ?? {}) };
    if (raw === "" || raw === undefined) {
      delete params[def.name];
    } else if (def.type === "int") params[def.name] = parseInt(raw as string, 10);
    else if (def.type === "float") params[def.name] = Number(raw);
    else if (def.type === "bool") params[def.name] = raw as boolean;
    else params[def.name] = raw as string;
    patch({ params });
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-sm font-semibold" style={{ color: "var(--ink-primary)" }}>
          {node.name}
        </h2>
        <GhostButton onClick={remove}>{t("worlds.delete_entity")}</GhostButton>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field
          id="node-slug"
          label={t("worlds.slug")}
          value={node.slug}
          onChange={(e) => {
            const next = e.target.value;
            onChange({
              ...payload,
              nodes: payload.nodes.map((n) =>
                n.slug === slug
                  ? { ...n, slug: next }
                  : n.parent === slug
                    ? { ...n, parent: next }
                    : n,
              ),
            });
            onSelect({ type: "node", slug: next });
          }}
        />
        <Field
          id="node-name"
          label={t("worlds.name")}
          value={node.name}
          onChange={(e) => patch({ name: e.target.value })}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Picker
          id="node-kind"
          label={t("worlds.kind")}
          value={node.kind}
          options={payload.taxonomy.kinds.map((k) => ({
            value: k.name,
            label: `${k.name} (${k.scale})`,
          }))}
          onChange={(e) => {
            const nextKind = payload.taxonomy.kinds.find((k) => k.name === e.target.value);
            patch({
              kind: e.target.value,
              position:
                nextKind?.scale === "outdoor" ? (node.position ?? { x: 0, y: 0 }) : undefined,
            });
          }}
        />
        <Picker
          id="node-parent"
          label={t("worlds.parent")}
          value={node.parent ?? ""}
          options={parentOptions}
          onChange={(e) => patch({ parent: e.target.value || null })}
        />
      </div>

      <Area
        id="node-description"
        label={t("worlds.description")}
        value={node.description ?? ""}
        onChange={(e) => patch({ description: e.target.value })}
      />

      {outdoor && (
        <div className="grid grid-cols-4 gap-3">
          <Field
            id="node-x"
            label="x"
            type="number"
            value={node.position?.x ?? 0}
            onChange={(e) =>
              patch({ position: { x: Number(e.target.value), y: node.position?.y ?? 0 } })
            }
          />
          <Field
            id="node-y"
            label="y"
            type="number"
            value={node.position?.y ?? 0}
            onChange={(e) =>
              patch({ position: { x: node.position?.x ?? 0, y: Number(e.target.value) } })
            }
          />
          <Field
            id="node-elevation"
            label={t("worlds.elevation")}
            type="number"
            value={node.elevation_m ?? ""}
            onChange={(e) =>
              patch({ elevation_m: e.target.value === "" ? undefined : Number(e.target.value) })
            }
          />
          <Field
            id="node-km"
            label={t("worlds.km_per_unit")}
            type="number"
            step="0.01"
            value={node.km_per_unit ?? ""}
            onChange={(e) =>
              patch({ km_per_unit: e.target.value === "" ? undefined : Number(e.target.value) })
            }
          />
        </div>
      )}

      {outdoor && (
        <Picker
          id="node-terrain"
          label={t("worlds.terrain")}
          value={node.terrain ?? ""}
          options={terrainOptions}
          allowEmpty
          onChange={(e) => patch({ terrain: e.target.value || undefined })}
        />
      )}

      {!outdoor && (
        <section className="space-y-2">
          <h3
            className="font-display text-xs font-semibold"
            style={{ color: "var(--ink-secondary)" }}
          >
            {t("worlds.exits")}
          </h3>
          {(node.exits ?? []).map((exit, i) => (
            <div key={i} className="flex items-end gap-2">
              <Picker
                id={`exit-${i}`}
                label={t("worlds.exit_to")}
                value={exit.to}
                options={[
                  { value: "outside", label: t("worlds.exit_outside") },
                  ...interiorSiblings,
                ]}
                onChange={(e) => {
                  const exits = [...(node.exits ?? [])];
                  exits[i] = { ...exit, to: e.target.value };
                  patch({ exits });
                }}
              />
              <label
                className="mb-2 flex items-center gap-1 font-display text-xs"
                style={{ color: "var(--ink-secondary)" }}
              >
                <input
                  type="checkbox"
                  checked={exit.locked ?? false}
                  onChange={(e) => {
                    const exits = [...(node.exits ?? [])];
                    exits[i] = { ...exit, locked: e.target.checked || undefined };
                    patch({ exits });
                  }}
                />
                {t("worlds.locked")}
              </label>
              <GhostButton
                onClick={() => patch({ exits: (node.exits ?? []).filter((_, j) => j !== i) })}
              >
                ✕
              </GhostButton>
            </div>
          ))}
          <GhostButton onClick={() => patch({ exits: [...(node.exits ?? []), { to: "outside" }] })}>
            + {t("worlds.add")}
          </GhostButton>
        </section>
      )}

      {kindDef?.params && kindDef.params.length > 0 && (
        <section className="space-y-3">
          <h3
            className="font-display text-xs font-semibold"
            style={{ color: "var(--ink-secondary)" }}
          >
            {t("worlds.params")}
          </h3>
          {kindDef.params.map((def) =>
            def.type === "bool" ? (
              <label
                key={def.name}
                className="flex items-center gap-2 font-display text-xs"
                style={{ color: "var(--ink-secondary)" }}
              >
                <input
                  type="checkbox"
                  checked={Boolean(node.params?.[def.name])}
                  onChange={(e) => setParam(def, e.target.checked)}
                />
                {def.name}
                {def.required ? " *" : ""}
              </label>
            ) : (
              <Field
                key={def.name}
                id={`param-${def.name}`}
                label={`${def.name}${def.required ? " *" : ""}`}
                type={def.type === "str" || !def.type ? "text" : "number"}
                min={def.min}
                max={def.max}
                value={(node.params?.[def.name] as string | number) ?? ""}
                onChange={(e) => setParam(def, e.target.value)}
              />
            ),
          )}
        </section>
      )}
    </div>
  );
}
