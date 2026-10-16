import { fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_NPC_FIELDS, NpcFieldsSection } from "../components/forms-npc-fields";
import en from "../../../shared/i18n/en.json";
import { createWorldPayload, renderWorldForm } from "./world-form-fixture";

const labels = en.worlds;
afterEach(() => vi.restoreAllMocks());

function renderFields(world = createWorldPayload()) {
  return renderWorldForm(
    (payload, onChange) => <NpcFieldsSection payload={payload} onChange={onChange} />,
    world,
  );
}

function worldWithTwoFields() {
  const world = createWorldPayload();
  world.taxonomy.npc_fields!.push({ name: "appearance" });
  return world;
}

describe("World-defined NPC fields", () => {
  it("materializes independent defaults", () => {
    const world = createWorldPayload();
    world.taxonomy.npc_fields = null;
    const view = renderFields(world);
    fireEvent.click(screen.getByRole("button", { name: `+ ${labels.npc_fields_customize}` }));
    expect(view.getPayload().taxonomy.npc_fields).toEqual(DEFAULT_NPC_FIELDS);
    expect(view.getPayload().taxonomy.npc_fields).not.toBe(DEFAULT_NPC_FIELDS);
  });

  it("edits defaults and scene flags while preserving other declarations", () => {
    const view = renderFields(worldWithTwoFields());
    fireEvent.change(screen.getAllByLabelText(labels.field_default)[0], {
      target: { value: "" },
    });
    expect(view.getPayload().taxonomy.npc_fields?.[0].default).toBeUndefined();
    fireEvent.change(screen.getAllByLabelText(labels.field_default)[0], {
      target: { value: "Villager" },
    });
    fireEvent.click(screen.getAllByLabelText(labels.field_scene)[0]);
    expect(view.getPayload().taxonomy.npc_fields?.[0].scene).toBeUndefined();
    fireEvent.click(screen.getAllByLabelText(labels.field_scene)[0]);
    expect(view.getPayload().taxonomy.npc_fields).toEqual([
      { name: "role", default: "Villager", scene: true },
      { name: "appearance" },
    ]);
  });

  it("renames a field and carries authored values without touching other NPCs", () => {
    const view = renderFields(worldWithTwoFields());
    fireEvent.change(screen.getAllByLabelText(labels.field_name)[0], {
      target: { value: "profession" },
    });
    expect(view.getPayload().npcs[0]).toMatchObject({ slug: "guide", profession: "guide" });
    expect(view.getPayload().npcs[0]).not.toHaveProperty("role");
    expect(view.getPayload().npcs[1]).toEqual({ slug: "other" });
    expect(view.getPayload().taxonomy.npc_fields?.[1]).toEqual({ name: "appearance" });
  });

  it("allows cancellation before deleting authored values", () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const view = renderFields(worldWithTwoFields());
    fireEvent.click(screen.getAllByRole("button", { name: "✕" })[0]);
    expect(view.getPayload().npcs[0]).toHaveProperty("role", "guide");
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getAllByRole("button", { name: "✕" })[0]);
    expect(view.getPayload().npcs[0]).not.toHaveProperty("role");
    expect(view.getPayload().taxonomy.npc_fields).toEqual([{ name: "appearance" }]);
  });

  it("removes unreferenced declarations without confirmation and adds blank fields", () => {
    const confirm = vi.spyOn(window, "confirm");
    const view = renderFields(worldWithTwoFields());
    fireEvent.click(screen.getAllByRole("button", { name: "✕" })[1]);
    expect(confirm).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "✕" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: `+ ${labels.add_npc_field}` }));
    expect(view.getPayload().taxonomy.npc_fields?.slice(-1)[0]).toEqual({ name: "" });
  });
});
