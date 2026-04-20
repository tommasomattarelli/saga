import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { OrnateFrame } from "../ornate-frame";

describe("OrnateFrame", () => {
  it("renders children", () => {
    render(<OrnateFrame>Hello</OrnateFrame>);
    expect(screen.getByText("Hello")).toBeInTheDocument();
  });

  it("renders all 4 corner SVGs", () => {
    const { container } = render(<OrnateFrame>Content</OrnateFrame>);
    const svgs = container.querySelectorAll("svg[aria-hidden='true']");
    expect(svgs.length).toBe(4);
  });

  it("applies custom className", () => {
    const { container } = render(<OrnateFrame className="custom-class">X</OrnateFrame>);
    expect(container.firstChild).toHaveClass("custom-class");
  });
});
