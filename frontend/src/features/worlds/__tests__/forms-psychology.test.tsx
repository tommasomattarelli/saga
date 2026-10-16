import { fireEvent, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_PSYCHOLOGY, PsychologySection } from "../components/forms-psychology";
import en from "../../../shared/i18n/en.json";
import { createWorldPayload, renderWorldForm } from "./world-form-fixture";

const labels = en.worlds;
afterEach(() => vi.restoreAllMocks());

function renderPsychology(world = createWorldPayload()) {
  return renderWorldForm(
    (payload, onChange) => <PsychologySection payload={payload} onChange={onChange} />,
    world,
  );
}

function worldWithTwoAxes() {
  const world = createWorldPayload();
  const psychology = world.taxonomy.psychology!;
  psychology.axes.honor = structuredClone(psychology.axes.trust);
  return world;
}

describe("Authored psychology", () => {
  it("materializes independent bundled defaults before customization", () => {
    const world = createWorldPayload();
    world.taxonomy.psychology = null;
    const view = renderPsychology(world);
    fireEvent.click(screen.getByRole("button", { name: `+ ${labels.psychology_customize}` }));
    expect(view.getPayload().taxonomy.psychology).toEqual(DEFAULT_PSYCHOLOGY);
    expect(view.getPayload().taxonomy.psychology).not.toBe(DEFAULT_PSYCHOLOGY);
    fireEvent.change(screen.getByLabelText(labels.first_impression), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText(labels.max_delta), { target: { value: "12" } });
    expect(view.getPayload().taxonomy.psychology).toMatchObject({
      first_impression_multiplier: 4,
      max_delta_per_turn: 12,
    });
    expect(DEFAULT_PSYCHOLOGY.first_impression_multiplier).toBe(3);
  });

  it("edits ranges, defaults and bands and keeps at least one band", () => {
    const view = renderPsychology();
    for (const [label, value] of [
      [labels.range_min, "-50"],
      [labels.range_max, "50"],
      [labels.axis_default, "5"],
    ]) {
      fireEvent.change(screen.getByLabelText(label), { target: { value } });
    }
    fireEvent.change(screen.getAllByLabelText(labels.band_min)[0], { target: { value: "-50" } });
    fireEvent.change(screen.getAllByLabelText(labels.band_label)[0], {
      target: { value: "guarded" },
    });
    expect(view.getPayload().taxonomy.psychology?.axes.trust).toMatchObject({
      range: [-50, 50],
      default: 5,
      bands: [
        { min: -50, label: "guarded" },
        { min: 0, label: "neutral" },
      ],
    });
    fireEvent.click(screen.getByRole("button", { name: `+ ${labels.add}` }));
    expect(view.getPayload().taxonomy.psychology?.axes.trust.bands.slice(-1)[0]).toEqual({
      min: 10,
      label: "",
    });
    for (let index = 0; index < 2; index++) {
      const row = screen.getAllByLabelText(labels.band_label)[0].parentElement!.parentElement!;
      fireEvent.click(within(row).getByRole("button", { name: "✕" }));
    }
    const row = screen.getByLabelText(labels.band_label).parentElement!.parentElement!;
    expect(within(row).getByRole("button", { name: "✕" })).toBeDisabled();
    expect(view.getPayload().taxonomy.psychology?.axes.trust.bands).toHaveLength(1);
  });

  it("carries authored seeds when renaming an axis without altering unrelated axes", () => {
    const world = worldWithTwoAxes();
    world.npcs[0].psychology = { trust: 42, honor: 5 };
    const view = renderPsychology(world);
    fireEvent.change(screen.getAllByLabelText(labels.axis_name)[0], {
      target: { value: "affinity" },
    });

    expect(Object.keys(view.getPayload().taxonomy.psychology!.axes)).toEqual(["affinity", "honor"]);
    expect(view.getPayload().npcs[0].psychology).toEqual({ affinity: 42, honor: 5 });
    expect(view.getPayload().npcs[1]).toBe(world.npcs[1]);
  });

  it("requires confirmation before removing an axis with authored seeds", () => {
    const world = worldWithTwoAxes();
    world.npcs[0].psychology = { trust: 42, honor: 5 };
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const view = renderPsychology(world);
    fireEvent.click(screen.getAllByRole("button", { name: "✕" })[0]);
    expect(view.getPayload().taxonomy.psychology?.axes).toHaveProperty("trust");
    expect(confirm).toHaveBeenCalledOnce();
    confirm.mockReturnValue(true);
    fireEvent.click(screen.getAllByRole("button", { name: "✕" })[0]);

    expect(view.getPayload().taxonomy.psychology?.axes).not.toHaveProperty("trust");
    expect(view.getPayload().npcs[0].psychology).toEqual({ honor: 5 });
    expect(view.getPayload().npcs[1].psychology).toBeUndefined();
  });

  it("clears empty seed maps when removing the last authored value", () => {
    const world = worldWithTwoAxes();
    world.npcs[0].psychology = { trust: 10 };
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const view = renderPsychology(world);
    fireEvent.click(screen.getAllByRole("button", { name: "✕" })[0]);
    expect(view.getPayload().npcs[0].psychology).toBeUndefined();
    expect(screen.getAllByRole("button", { name: "✕" })[0]).toBeDisabled();
  });

  it("removes an unseeded axis without confirmation and adds a new axis", () => {
    const confirm = vi.spyOn(window, "confirm");
    const view = renderPsychology(worldWithTwoAxes());
    fireEvent.click(screen.getAllByRole("button", { name: "✕" })[0]);
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: `+ ${labels.add_axis}` }));
    expect(view.getPayload().taxonomy.psychology?.axes[""]).toEqual({
      range: [-100, 100],
      default: 0,
      bands: [{ min: -100, label: "neutral" }],
    });
  });
});
