import { useTranslation } from "react-i18next";
import type { EditableWorld, EditableNode } from "../../../shared/api/client";

export interface Selection {
  type: "meta" | "taxonomy" | "scenario" | "node" | "edge" | "faction" | "npc" | "encounter";
  slug?: string;
}

interface Props {
  payload: EditableWorld;
  selection: Selection;
  onSelect: (s: Selection) => void;
  onChange: (p: EditableWorld) => void;
}

function freshSlug(existing: string[], base: string): string {
  let i = 1;
  while (existing.includes(`${base}-${i}`)) i += 1;
  return `${base}-${i}`;
}

/* Left rail: node tree + collections. Adding an entity selects it immediately. */
export function EditorNav({ payload, selection, onSelect, onChange }: Props) {
  const { t } = useTranslation();

  const entryStyle = (active: boolean) => ({
    color: active ? "var(--accent)" : "var(--ink-secondary)",
  });

  const addNode = (parent: string | null) => {
    const slug = freshSlug(
      payload.nodes.map((n) => n.slug),
      "new-place",
    );
    const kind = payload.taxonomy.kinds[0];
    const node: EditableNode = {
      slug,
      parent,
      kind: kind.name,
      name: t("worlds.new_place"),
      ...(kind.scale === "outdoor" ? { position: { x: 0, y: 0 } } : {}),
    };
    onChange({ ...payload, nodes: [...payload.nodes, node] });
    onSelect({ type: "node", slug });
  };

  const addEntity = (kind: "edge" | "faction" | "npc" | "encounter") => {
    const key = `${kind}s` as "edges" | "factions" | "npcs" | "encounters";
    const slug = freshSlug(
      payload[key].map((e) => e.slug as string),
      `new-${kind}`,
    );
    const defaults: Record<string, Record<string, unknown>> = {
      edge: {
        slug,
        from: payload.nodes[0]?.slug ?? "",
        to: payload.nodes[1]?.slug ?? payload.nodes[0]?.slug ?? "",
        mode: payload.taxonomy.travel_modes[0]?.name ?? "",
      },
      faction: { slug, name: t("worlds.new_faction") },
      npc: { slug, name: t("worlds.new_npc") },
      encounter: {
        slug,
        dice: "1d6",
        entries: [{ roll: [1, 6], type: "event", description: "…" }],
      },
    };
    onChange({ ...payload, [key]: [...payload[key], defaults[kind]] });
    onSelect({ type: kind, slug });
  };

  const renderTree = (parent: string | null, depth: number) =>
    payload.nodes
      .filter(
        (n) => (n.parent ?? null) === parent || (parent === null && n.parent === payload.slug),
      )
      .map((n) => (
        <div key={n.slug} style={{ paddingLeft: depth * 12 }}>
          <button
            onClick={() => onSelect({ type: "node", slug: n.slug })}
            className="block w-full truncate text-left font-display text-xs py-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
            style={entryStyle(selection.type === "node" && selection.slug === n.slug)}
          >
            {n.name}
          </button>
          {renderTree(n.slug, depth + 1)}
        </div>
      ));

  const section = (label: string, onAdd?: () => void) => (
    <div className="mt-4 mb-1 flex items-center justify-between">
      <span
        className="font-display text-[11px] font-semibold uppercase tracking-wide"
        style={{ color: "var(--ink-faded)" }}
      >
        {label}
      </span>
      {onAdd && (
        <button
          onClick={onAdd}
          aria-label={`${t("worlds.add")} ${label}`}
          className="font-display text-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
          style={{ color: "var(--ink-faded)" }}
        >
          +
        </button>
      )}
    </div>
  );

  const collection = (
    kind: "edge" | "faction" | "npc" | "encounter",
    items: Record<string, unknown>[],
  ) =>
    items.map((item) => (
      <button
        key={item.slug as string}
        onClick={() => onSelect({ type: kind, slug: item.slug as string })}
        className="block w-full truncate text-left font-display text-xs py-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
        style={entryStyle(selection.type === kind && selection.slug === item.slug)}
      >
        {(item.name as string) ?? (item.slug as string)}
      </button>
    ));

  return (
    <aside
      className="w-60 shrink-0 overflow-y-auto px-4 py-4"
      style={{ background: "var(--parchment-aged)", borderRight: "1px solid var(--line)" }}
    >
      {(["meta", "taxonomy", "scenario"] as const).map((key) => (
        <button
          key={key}
          onClick={() => onSelect({ type: key })}
          className="block w-full text-left font-display text-xs py-1 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-accent"
          style={entryStyle(selection.type === key)}
        >
          {t(`worlds.section_${key}`)}
        </button>
      ))}

      {section(t("worlds.section_nodes"), () => addNode(null))}
      {renderTree(null, 0)}

      {section(t("worlds.section_edges"), () => addEntity("edge"))}
      {collection("edge", payload.edges)}

      {section(t("worlds.section_factions"), () => addEntity("faction"))}
      {collection("faction", payload.factions)}

      {section(t("worlds.section_npcs"), () => addEntity("npc"))}
      {collection("npc", payload.npcs)}

      {section(t("worlds.section_encounters"), () => addEntity("encounter"))}
      {collection("encounter", payload.encounters)}
    </aside>
  );
}
