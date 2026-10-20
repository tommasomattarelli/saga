import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import type { AxiosInstance } from "axios";
import api from "../../../shared/api/client";
import SettingsAiPanel from "../components/settings-ai-panel";
import { settingsQueryKey } from "../hooks/use-ai-settings";
import { useAuthStore } from "../../../shared/stores/auth-store";
import { useGameStore } from "../../../shared/stores/game-store";
import type { User } from "../../../shared/types";

vi.mock("axios", async () => {
  const actual = await vi.importActual<typeof import("axios")>("axios");
  const mockInstance = {
    interceptors: {
      request: { use: vi.fn(), eject: vi.fn() },
      response: { use: vi.fn(), eject: vi.fn() },
    },
    get: vi.fn(),
    post: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
    patch: vi.fn(),
  };
  return {
    default: {
      ...actual.default,
      create: vi.fn(() => mockInstance),
    },
  };
});

const mockApi = vi.mocked(api as AxiosInstance);

const POLICY = {
  allowed_providers: ["openai", "openrouter", "google", "local"],
  local_endpoints: ["ollama"],
  generation_default: { provider: "google", model: "gemini-3.5-flash", local_endpoint: null },
  embedding_default: {
    provider: "openrouter",
    model: "openai/text-embedding-3-small",
    local_endpoint: null,
  },
  server_key_sharing: { openai: true, openrouter: false, google: false },
};

const settingsFor = (overrides: Record<string, unknown> = {}) => ({
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
  policy: POLICY,
  ...overrides,
});

const indexStatus = {
  active: null,
  target: null,
  latest: null,
  progress: null,
  suspended_reason: null,
  needs_retry: false,
};

function setup() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
  return { queryClient, Wrapper };
}

const inputValue = (id: string) =>
  (document.querySelector(`#${id}`) as HTMLInputElement | null)?.value;

describe("SettingsAiPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      user: { id: "u1", username: "hero", email: "h@x.io" } as User,
    });
    useAuthStore.getState().setTokens({
      access_token: "token",
      refresh_token: "refresh",
      token_type: "bearer",
    });
    useGameStore.setState({
      campaign: { id: "c1", name: "The Lost Realm" } as never,
    });
    mockApi.get.mockImplementation(((url: string) => {
      if (url === "/settings") return Promise.resolve({ data: settingsFor() } as never);
      if (url === "/campaigns/c1/embedding-index") {
        return Promise.resolve({ data: indexStatus } as never);
      }
      return Promise.resolve({ data: null } as never);
    }) as never);
  });

  it("shows the inherited defaults when no personal profile is set", async () => {
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    expect(await screen.findByText("In use: google / gemini-3.5-flash")).toBeInTheDocument();
    expect(inputValue("generation-provider")).toBe("");
    expect(inputValue("generation-model")).toBe("");
  });

  it("keeps the generation and embedding profiles independent", async () => {
    mockApi.get.mockImplementation(((url: string) => {
      if (url === "/settings") {
        return Promise.resolve({
          data: settingsFor({
            generation_provider: "openai",
            generation_model: "gpt-x",
            embedding_provider: "openrouter",
            embedding_model: "emb-y",
          }),
        } as never);
      }
      return Promise.resolve({ data: indexStatus } as never);
    }) as never);
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    await waitFor(() => expect(inputValue("generation-model")).toBe("gpt-x"));
    expect(inputValue("embedding-model")).toBe("emb-y");
  });

  it("saves a personal generation profile", async () => {
    mockApi.patch.mockResolvedValue({ data: settingsFor() } as never);
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    await screen.findByText("In use: google / gemini-3.5-flash");
    fireEvent.change(document.querySelector("#generation-provider")!, {
      target: { value: "openai" },
    });
    fireEvent.change(document.querySelector("#generation-model")!, {
      target: { value: "gpt-x" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);

    await waitFor(() =>
      expect(mockApi.patch).toHaveBeenCalledWith("/settings", {
        generation_provider: "openai",
        generation_model: "gpt-x",
        generation_local_endpoint: null,
      }),
    );
  });

  it("restores the instance default with a null profile", async () => {
    mockApi.patch.mockResolvedValue({ data: settingsFor() } as never);
    mockApi.get.mockImplementation(((url: string) => {
      if (url === "/settings") {
        return Promise.resolve({
          data: settingsFor({
            generation_provider: "openai",
            generation_model: "gpt-x",
          }),
        } as never);
      }
      return Promise.resolve({ data: indexStatus } as never);
    }) as never);
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    await waitFor(() => expect(inputValue("generation-model")).toBe("gpt-x"));
    fireEvent.click(screen.getAllByRole("button", { name: "Use the instance default" })[0]);

    await waitFor(() =>
      expect(mockApi.patch).toHaveBeenCalledWith("/settings", {
        generation_provider: null,
        generation_model: null,
        generation_local_endpoint: null,
      }),
    );
  });

  it("never shows a stored key and clears the typed one after saving", async () => {
    mockApi.get.mockImplementation(((url: string) => {
      if (url === "/settings") {
        return Promise.resolve({ data: settingsFor({ has_openai_key: true }) } as never);
      }
      return Promise.resolve({ data: indexStatus } as never);
    }) as never);
    mockApi.put.mockResolvedValue({ data: { message: "API keys updated" } } as never);
    const { queryClient, Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    expect(await screen.findByText("A key is saved for this provider.")).toBeInTheDocument();
    expect(inputValue("key-openai")).toBe("");

    fireEvent.change(document.querySelector("#key-openai")!, {
      target: { value: "sk-typed" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Save key" })[0]);

    await waitFor(() =>
      expect(mockApi.put).toHaveBeenCalledWith("/settings/api-keys", { openai: "sk-typed" }),
    );
    await waitFor(() => expect(inputValue("key-openai")).toBe(""));

    const cached = queryClient
      .getQueryCache()
      .getAll()
      .map((query) => JSON.stringify(query.state.data ?? null))
      .join("|");
    const mutations = queryClient
      .getMutationCache()
      .getAll()
      .map((mutation) => JSON.stringify(mutation.state.variables ?? null))
      .join("|");
    expect(cached).not.toContain("sk-typed");
    expect(mutations).not.toContain("sk-typed");
  });

  it("saves the consent for a provider", async () => {
    mockApi.get.mockImplementation(((url: string) => {
      if (url === "/settings") {
        return Promise.resolve({
          data: settingsFor({ server_key_consents: { openai: true } }),
        } as never);
      }
      return Promise.resolve({ data: indexStatus } as never);
    }) as never);
    mockApi.put.mockResolvedValue({
      data: { server_key_consents: { openai: false } },
    } as never);
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    const checkbox = (await screen.findByLabelText(
      "Allow the instance key for OpenAI",
    )) as HTMLInputElement;
    expect(checkbox.checked).toBe(true);
    fireEvent.click(checkbox);

    await waitFor(() =>
      expect(mockApi.put).toHaveBeenCalledWith("/settings/server-key-consents", {
        openai: false,
      }),
    );
  });

  it("reports a failed consent", async () => {
    mockApi.put.mockRejectedValue({ response: { status: 500 } });
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    const checkbox = await screen.findByLabelText("Allow the instance key for OpenAI");
    fireEvent.click(checkbox);

    expect(
      await screen.findByText("The server couldn't save your changes. Try again."),
    ).toBeInTheDocument();
  });

  it("reports a failed key save and keeps the typed key for a retry", async () => {
    mockApi.put.mockRejectedValue({ response: { status: 500 } });
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    const keyInput = await screen.findByLabelText("OpenAI");
    fireEvent.change(keyInput, { target: { value: "sk-typed" } });
    fireEvent.click(screen.getAllByRole("button", { name: "Save key" })[0]);

    expect(
      await screen.findByText("The server couldn't save your changes. Try again."),
    ).toBeInTheDocument();
    expect(inputValue("key-openai")).toBe("sk-typed");
  });

  it("keeps the other profile draft when one profile is saved", async () => {
    mockApi.patch.mockResolvedValue({ data: settingsFor() } as never);
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    await screen.findByText("In use: google / gemini-3.5-flash");
    fireEvent.change(document.querySelector("#embedding-provider")!, {
      target: { value: "openrouter" },
    });
    fireEvent.change(document.querySelector("#embedding-model")!, {
      target: { value: "emb-draft" },
    });
    fireEvent.change(document.querySelector("#generation-provider")!, {
      target: { value: "openai" },
    });
    fireEvent.change(document.querySelector("#generation-model")!, {
      target: { value: "gpt-new" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);

    await waitFor(() => expect(mockApi.patch).toHaveBeenCalled());
    expect(inputValue("embedding-model")).toBe("emb-draft");
    expect(inputValue("embedding-provider")).toBe("openrouter");
  });

  it("keeps every input when restoring the default fails with a conflict", async () => {
    mockApi.patch.mockRejectedValue({ response: { status: 409 } });
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    await screen.findByText("In use: google / gemini-3.5-flash");
    fireEvent.change(document.querySelector("#embedding-provider")!, {
      target: { value: "openrouter" },
    });
    fireEvent.change(document.querySelector("#embedding-model")!, {
      target: { value: "emb-draft" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Use the instance default" })[1]);

    await screen.findAllByText(
      "A rebuild is still running for one of your campaigns: cancel it before changing the embedding profile.",
    );
    expect(inputValue("embedding-model")).toBe("emb-draft");
    expect(inputValue("embedding-provider")).toBe("openrouter");
  });

  it("reloads the credential provenance after a consent change", async () => {
    let consentSaved = false;
    mockApi.get.mockImplementation(((url: string) => {
      if (url === "/settings") {
        return Promise.resolve({
          data: settingsFor({
            server_key_consents: consentSaved ? { openai: true } : {},
            credential_source: consentSaved ? "server" : "missing",
          }),
        } as never);
      }
      return Promise.resolve({ data: indexStatus } as never);
    }) as never);
    mockApi.put.mockImplementation((() => {
      consentSaved = true;
      return Promise.resolve({ data: { server_key_consents: { openai: true } } } as never);
    }) as never);
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    expect(await screen.findAllByText("No key available for this provider yet.")).not.toHaveLength(
      0,
    );
    fireEvent.click(screen.getByLabelText("Allow the instance key for OpenAI"));

    expect(
      await screen.findAllByText("Using the instance's shared key (you consented)."),
    ).not.toHaveLength(0);
  });

  it("allows revoking a consent when the operator no longer shares a key", async () => {
    mockApi.get.mockImplementation(((url: string) => {
      if (url === "/settings") {
        return Promise.resolve({
          data: settingsFor({
            server_key_consents: { openai: true },
            policy: {
              ...POLICY,
              server_key_sharing: { openai: false, openrouter: false, google: false },
            },
          }),
        } as never);
      }
      return Promise.resolve({ data: indexStatus } as never);
    }) as never);
    mockApi.put.mockResolvedValue({ data: { server_key_consents: { openai: false } } } as never);
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    const checkbox = (await screen.findByLabelText(
      "Allow the instance key for OpenAI",
    )) as HTMLInputElement;
    expect(checkbox.disabled).toBe(false);
    fireEvent.click(checkbox);

    await waitFor(() =>
      expect(mockApi.put).toHaveBeenCalledWith("/settings/server-key-consents", {
        openai: false,
      }),
    );
  });

  it("never lets a late profile answer from the previous user land in the new session", async () => {
    let resolvePatch: (value: unknown) => void = () => {};
    mockApi.patch.mockImplementation(
      (() =>
        new Promise((resolve) => {
          resolvePatch = resolve;
        })) as never,
    );
    mockApi.get.mockImplementation(((url: string) => {
      if (url === "/settings") {
        const current = useAuthStore.getState().user?.id;
        return Promise.resolve({
          data: settingsFor({
            generation_provider: current === "u2" ? "openrouter" : "openai",
            generation_model: current === "u2" ? "gpt-b" : "gpt-a",
          }),
        } as never);
      }
      return Promise.resolve({ data: indexStatus } as never);
    }) as never);
    const { queryClient, Wrapper } = setup();
    const { rerender } = render(<SettingsAiPanel open />, { wrapper: Wrapper });

    await waitFor(() => expect(inputValue("generation-model")).toBe("gpt-a"));
    fireEvent.change(document.querySelector("#generation-model")!, {
      target: { value: "gpt-late" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Save" })[0]);

    useAuthStore.setState({
      user: { id: "u2", username: "other", email: "o@x.io" } as User,
    });
    rerender(<SettingsAiPanel open />);
    await waitFor(() => expect(inputValue("generation-model")).toBe("gpt-b"));

    resolvePatch({
      data: settingsFor({ generation_provider: "openai", generation_model: "gpt-late" }),
    });

    await waitFor(() => {
      const late = queryClient.getQueryData(settingsQueryKey("u1")) as
        | { generation_model: string }
        | undefined;
      expect(late?.generation_model).toBe("gpt-late");
    });
    const cached = queryClient.getQueryData(settingsQueryKey("u2")) as {
      generation_model: string;
    };
    expect(cached.generation_model).toBe("gpt-b");
    expect(inputValue("generation-model")).toBe("gpt-b");
  });

  it("explains a conflicting rebuild and keeps the unsaved form", async () => {
    mockApi.patch.mockRejectedValue({ response: { status: 409 } });
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    await screen.findByText("In use: google / gemini-3.5-flash");
    fireEvent.change(document.querySelector("#embedding-provider")!, {
      target: { value: "openrouter" },
    });
    fireEvent.change(document.querySelector("#embedding-model")!, {
      target: { value: "emb-new" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Save" })[1]);

    expect(
      await screen.findAllByText(
        "A rebuild is still running for one of your campaigns: cancel it before changing the embedding profile.",
      ),
    ).not.toHaveLength(0);
    const editor = document.querySelector("#embedding-model")!.closest("div.mb-4") as HTMLElement;
    expect(within(editor).getByRole("alert")).toHaveTextContent(
      "A rebuild is still running for one of your campaigns",
    );
    expect(inputValue("embedding-model")).toBe("emb-new");
  });

  it("asks for no request while the drawer is closed", () => {
    const { Wrapper } = setup();
    render(<SettingsAiPanel open={false} />, { wrapper: Wrapper });

    expect(mockApi.get).not.toHaveBeenCalled();
  });

  it("asks for no request when nobody is signed in", () => {
    useAuthStore.getState().logout();
    const { Wrapper } = setup();
    render(<SettingsAiPanel open />, { wrapper: Wrapper });

    expect(mockApi.get).not.toHaveBeenCalled();
  });

  it("never shows the previous user's settings", async () => {
    mockApi.get.mockImplementation(((url: string) => {
      if (url === "/settings") {
        const current = useAuthStore.getState().user?.id;
        if (current === "u2") {
          return Promise.resolve({
            data: settingsFor({
              generation_provider: "openrouter",
              generation_model: "gpt-b",
            }),
          } as never);
        }
        return Promise.resolve({
          data: settingsFor({
            generation_provider: "openai",
            generation_model: "gpt-a",
          }),
        } as never);
      }
      return Promise.resolve({ data: indexStatus } as never);
    }) as never);
    const { Wrapper } = setup();
    const { rerender } = render(<SettingsAiPanel open />, { wrapper: Wrapper });

    await waitFor(() => expect(inputValue("generation-model")).toBe("gpt-a"));
    useAuthStore.setState({
      user: { id: "u2", username: "other", email: "o@x.io" } as User,
    });
    rerender(<SettingsAiPanel open />);

    await waitFor(() => expect(inputValue("generation-model")).toBe("gpt-b"));
    expect(screen.queryByText("In use: openai / gpt-a")).toBeNull();
  });
});
