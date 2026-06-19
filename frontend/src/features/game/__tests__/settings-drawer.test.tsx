import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import SettingsDrawer from "../components/settings-drawer";
import { useUIStore } from "../../../shared/stores/ui-store";
import { useAuthStore } from "../../../shared/stores/auth-store";
import type { User } from "../../../shared/types";

const renderDrawer = () =>
  render(
    <MemoryRouter>
      <SettingsDrawer />
    </MemoryRouter>,
  );

describe("SettingsDrawer", () => {
  beforeEach(() => {
    useUIStore.setState({
      sidePanel: "settings",
      soundEnabled: true,
      themeOverride: "auto",
      fontSize: 18,
    });
    useAuthStore.setState({ user: { id: "u1", username: "hero", email: "h@x.io" } as User });
  });

  it("toggles dice sound", () => {
    renderDrawer();
    fireEvent.click(screen.getByRole("switch"));
    expect(useUIStore.getState().soundEnabled).toBe(false);
  });

  it("sets the theme override", () => {
    renderDrawer();
    fireEvent.click(screen.getByRole("button", { name: "dark" }));
    expect(useUIStore.getState().themeOverride).toBe("dark");
  });

  it("updates the font size from the slider", () => {
    renderDrawer();
    fireEvent.change(screen.getByRole("slider"), { target: { value: "22" } });
    expect(useUIStore.getState().fontSize).toBe(22);
  });

  it("shows the signed-in user and logs out on Depart", () => {
    renderDrawer();
    expect(screen.getByText("h@x.io")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Depart" }));
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useUIStore.getState().sidePanel).toBeNull();
  });
});
