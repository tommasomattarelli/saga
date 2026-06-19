import { render, screen } from "@testing-library/react";
import { describe, it, expect, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import App from "../App";
import { useAuthStore } from "../shared/stores/auth-store";
import { useUIStore } from "../shared/stores/ui-store";

const renderAt = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );

describe("App routing & display settings", () => {
  beforeEach(() => {
    useAuthStore.setState({ isAuthenticated: false });
  });

  it("redirects unauthenticated users from a protected route to /login", async () => {
    renderAt("/campaigns");
    expect(await screen.findByLabelText("Word of Passage")).toBeInTheDocument();
  });

  it("applies the font-size display setting to the document root", () => {
    useUIStore.setState({ fontSize: 22 });
    renderAt("/login");
    expect(document.documentElement.style.getPropertyValue("--base-font-size")).toBe("22px");
  });
});
