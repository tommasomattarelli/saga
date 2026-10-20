import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, beforeEach, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import SettingsDrawer from "../components/settings-drawer";
import { useUIStore } from "../../../shared/stores/ui-store";
import { useAuthStore } from "../../../shared/stores/auth-store";
import type { User } from "../../../shared/types";

vi.mock("../api/settings-api", () => ({
  getSettings: vi.fn(() =>
    Promise.resolve({
      data: {
        preferred_language: "en",
        generation_provider: null,
        generation_model: null,
        generation_local_endpoint: null,
        embedding_provider: null,
        embedding_model: null,
        embedding_local_endpoint: null,
        server_key_consents: {},
        has_openai_key: false,
        has_openrouter_key: false,
        has_google_key: false,
        effective_provider: "google",
        credential_source: "missing",
        effective_embedding_provider: "openrouter",
        embedding_credential_source: "missing",
        policy: {
          allowed_providers: ["openai", "openrouter", "google", "local"],
          local_endpoints: ["ollama"],
          generation_default: {
            provider: "google",
            model: "gemini-3.5-flash",
            local_endpoint: null,
          },
          embedding_default: {
            provider: "openrouter",
            model: "openai/text-embedding-3-small",
            local_endpoint: null,
          },
          server_key_sharing: { openai: false, openrouter: false, google: false },
        },
      },
    }),
  ),
  patchSettings: vi.fn(),
  putApiKeys: vi.fn(),
  putServerKeyConsents: vi.fn(),
  getEmbeddingIndexStatus: vi.fn(),
  retryEmbeddingIndex: vi.fn(),
  cancelEmbeddingIndex: vi.fn(),
  classifySettingsError: vi.fn(() => "network"),
}));

const renderDrawer = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <SettingsDrawer />
      </QueryClientProvider>
    </MemoryRouter>,
  );
};

describe("SettingsDrawer", () => {
  beforeEach(() => {
    useUIStore.setState({
      sidePanel: "settings",
      soundEnabled: true,
      fontSize: 18,
    });
    useAuthStore.setState({ user: { id: "u1", username: "hero", email: "h@x.io" } as User });
    useAuthStore.getState().setTokens({
      access_token: "token",
      refresh_token: "refresh",
      token_type: "bearer",
    });
  });

  it("toggles dice sound", () => {
    renderDrawer();
    fireEvent.click(screen.getByRole("switch", { name: "Dice sound" }));
    expect(useUIStore.getState().soundEnabled).toBe(false);
  });

  it("keeps the audio, display and account controls", () => {
    renderDrawer();
    expect(screen.getByRole("slider")).toBeInTheDocument();
    expect(screen.getByText("h@x.io")).toBeInTheDocument();
  });

  it("shows the AI settings area", async () => {
    renderDrawer();
    expect(screen.getByText("AI")).toBeInTheDocument();
    expect(await screen.findByText("Generation model")).toBeInTheDocument();
  });

  it("updates the font size from the slider", () => {
    renderDrawer();
    fireEvent.change(screen.getByRole("slider"), { target: { value: "22" } });
    expect(useUIStore.getState().fontSize).toBe(22);
  });

  it("shows the signed-in user and logs out on Sign out", () => {
    renderDrawer();
    expect(screen.getByText("h@x.io")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useUIStore.getState().sidePanel).toBeNull();
  });
});
