import { render } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { NoiseOverlay } from "../noise-overlay";
import { VignetteLayer } from "../vignette-layer";

describe("atmospheric overlays", () => {
  it("NoiseOverlay renders its noise filter", () => {
    const { container } = render(<NoiseOverlay />);
    expect(container.querySelector("#saga-noise")).toBeInTheDocument();
  });

  it("VignetteLayer renders a fixed overlay", () => {
    const { container } = render(<VignetteLayer />);
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });
});
