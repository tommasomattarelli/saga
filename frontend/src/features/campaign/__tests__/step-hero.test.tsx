import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import StepHero from "../components/new-campaign/steps/step-hero";
import { CLASS_PRESETS } from "../data/class-presets";
import type { WorldOption } from "../../../shared/api/client";

const world: WorldOption = {
  slug: "classic",
  name: "Classic Fantasy",
  description: "Standard fantasy",
  tags: ["fantasy"],
  version: "1.0.0",
  author: "System",
};

describe("Hero class icons", () => {
  it("renders each class icon and preserves class selection", () => {
    const onChange = vi.fn();
    render(
      <StepHero
        form={{ heroName: "Aria", archetype: "warrior" }}
        selectedWorld={world}
        onChange={onChange}
        onBack={vi.fn()}
        onNext={vi.fn()}
      />,
    );

    for (const [archetype, preset] of Object.entries(CLASS_PRESETS)) {
      const button = screen.getByRole("button", { name: preset.label });
      expect(button.querySelector("svg")).toHaveAttribute("viewBox", "0 0 512 512");
      fireEvent.click(button);
      expect(onChange).toHaveBeenLastCalledWith({ archetype });
    }
  });
});
