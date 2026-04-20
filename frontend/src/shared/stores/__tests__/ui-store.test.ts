import { describe, it, expect, beforeEach } from "vitest";
import { useUIStore } from "../ui-store";

describe("UI Store", () => {
  beforeEach(() => {
    useUIStore.setState({
      sidePanel: null,
      showCompanionBar: true,
      soundEnabled: true,
    });
  });

  it("should toggle side panel", () => {
    const { toggleSidePanel } = useUIStore.getState();

    toggleSidePanel("character");
    expect(useUIStore.getState().sidePanel).toBe("character");

    toggleSidePanel("character");
    expect(useUIStore.getState().sidePanel).toBe(null);
  });

  it("should set side panel", () => {
    const { setSidePanel } = useUIStore.getState();
    setSidePanel("inventory");
    expect(useUIStore.getState().sidePanel).toBe("inventory");
  });
});
