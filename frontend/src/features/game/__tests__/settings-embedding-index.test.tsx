import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import type { AxiosInstance } from "axios";
import api from "../../../shared/api/client";
import { SettingsEmbeddingIndex } from "../components/settings-embedding-index";
import { embeddingIndexQueryKey } from "../hooks/use-embedding-index";
import { useAuthStore } from "../../../shared/stores/auth-store";
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

const summary = (overrides: Record<string, unknown> = {}) => ({
  id: "11111111-1111-1111-1111-111111111111",
  provider: "openai",
  model: "text-embedding-3-small",
  endpoint_name: null,
  pipeline_version: "embed-v1",
  dimension: 384,
  state: "completed",
  last_error: null,
  ...overrides,
});

const status = (overrides: Record<string, unknown> = {}) => ({
  active: null,
  target: null,
  latest: null,
  progress: null,
  suspended_reason: null,
  needs_retry: false,
  ...overrides,
});

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

describe("SettingsEmbeddingIndex", () => {
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
    mockApi.get.mockImplementation(
      ((url: string) =>
        Promise.resolve({
          data: url === "/campaigns/c1/embedding-index" ? status() : null,
        }) as never) as never,
    );
  });

  it("shows the active index and its dimension", async () => {
    mockApi.get.mockResolvedValue({
      data: status({ active: summary() }),
    } as never);
    const { Wrapper } = setup();
    render(<SettingsEmbeddingIndex campaignId="c1" enabled />, { wrapper: Wrapper });

    expect(
      await screen.findByText("Active index: openai / text-embedding-3-small"),
    ).toBeInTheDocument();
    expect(screen.getByText("Dimensions: 384")).toBeInTheDocument();
  });

  it("never claims a known dimension when there is none", async () => {
    mockApi.get.mockResolvedValue({
      data: status({ active: summary({ dimension: null }) }),
    } as never);
    const { Wrapper } = setup();
    render(<SettingsEmbeddingIndex campaignId="c1" enabled />, { wrapper: Wrapper });

    expect(await screen.findByText("Dimensions: not known yet.")).toBeInTheDocument();
  });

  it("shows the running rebuild with the real counters", async () => {
    mockApi.get.mockResolvedValue({
      data: status({
        target: summary({ provider: "openrouter", model: "emb", state: "running" }),
        progress: {
          total: 10,
          embedded: 4,
          pending: 5,
          failed: 1,
          turn_total: 6,
          fact_total: 4,
        },
      }),
    } as never);
    const { Wrapper } = setup();
    render(<SettingsEmbeddingIndex campaignId="c1" enabled />, { wrapper: Wrapper });

    expect(await screen.findByText("Rebuild: openrouter / emb (running)")).toBeInTheDocument();
    expect(screen.getByText("Embedded 4 of 10 (pending 5, failed 1)")).toBeInTheDocument();
    expect(screen.getByText("Turns 6, facts 4")).toBeInTheDocument();
  });

  it("shows the empty state", async () => {
    const { Wrapper } = setup();
    render(<SettingsEmbeddingIndex campaignId="c1" enabled />, { wrapper: Wrapper });

    expect(await screen.findByText("No memory index for this campaign yet.")).toBeInTheDocument();
  });

  it("shows the suspended reason of the last rebuild", async () => {
    mockApi.get.mockResolvedValue({
      data: status({
        needs_retry: true,
        suspended_reason: "The last rebuild was cancelled; use retry to run it again.",
      }),
    } as never);
    const { Wrapper } = setup();
    render(<SettingsEmbeddingIndex campaignId="c1" enabled />, { wrapper: Wrapper });

    expect(
      await screen.findByText("The last rebuild was cancelled; use retry to run it again."),
    ).toBeInTheDocument();
  });

  it("retries a failed rebuild", async () => {
    mockApi.get.mockResolvedValue({ data: status({ needs_retry: true }) } as never);
    mockApi.post.mockResolvedValue({ data: status() } as never);
    const { Wrapper } = setup();
    render(<SettingsEmbeddingIndex campaignId="c1" enabled />, { wrapper: Wrapper });

    const retry = await screen.findByRole("button", { name: "Retry rebuild" });
    await waitFor(() => expect(retry).not.toBeDisabled());
    fireEvent.click(retry);

    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith("/campaigns/c1/embedding-index/retry"),
    );
  });

  it("cancels a running rebuild only when confirmed", async () => {
    mockApi.get.mockResolvedValue({
      data: status({ target: summary({ state: "running" }) }),
    } as never);
    mockApi.post.mockResolvedValue({ data: status() } as never);
    const { Wrapper } = setup();
    render(<SettingsEmbeddingIndex campaignId="c1" enabled />, { wrapper: Wrapper });

    const cancel = await screen.findByRole("button", { name: "Cancel rebuild" });
    await waitFor(() => expect(cancel).not.toBeDisabled());
    fireEvent.click(cancel);
    expect(mockApi.post).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));
    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith("/campaigns/c1/embedding-index/cancel"),
    );
  });

  it("reports a failed action", async () => {
    mockApi.get.mockResolvedValue({ data: status({ needs_retry: true }) } as never);
    mockApi.post.mockRejectedValue({ response: { status: 500 } });
    const { Wrapper } = setup();
    render(<SettingsEmbeddingIndex campaignId="c1" enabled />, { wrapper: Wrapper });

    const retry = await screen.findByRole("button", { name: "Retry rebuild" });
    await waitFor(() => expect(retry).not.toBeDisabled());
    fireEvent.click(retry);

    expect(
      await screen.findByText("The server couldn't save your changes. Try again."),
    ).toBeInTheDocument();
  });

  it("asks for a fresh confirmation when the campaign changes", async () => {
    mockApi.get.mockImplementation(
      (() =>
        Promise.resolve({
          data: status({ target: summary({ state: "running" }) }),
        }) as never) as never,
    );
    mockApi.post.mockResolvedValue({ data: status() } as never);
    const { Wrapper } = setup();
    const { rerender } = render(<SettingsEmbeddingIndex campaignId="c1" enabled />, {
      wrapper: Wrapper,
    });

    const cancel = await screen.findByRole("button", { name: "Cancel rebuild" });
    await waitFor(() => expect(cancel).not.toBeDisabled());
    fireEvent.click(cancel);
    expect(screen.getByRole("button", { name: "Confirm cancel" })).toBeInTheDocument();

    rerender(<SettingsEmbeddingIndex campaignId="c2" enabled />);
    expect(screen.queryByRole("button", { name: "Confirm cancel" })).toBeNull();
    expect(mockApi.post).not.toHaveBeenCalled();

    const cancelForNewCampaign = await screen.findByRole("button", { name: "Cancel rebuild" });
    await waitFor(() => expect(cancelForNewCampaign).not.toBeDisabled());
    fireEvent.click(cancelForNewCampaign);
    fireEvent.click(screen.getByRole("button", { name: "Confirm cancel" }));

    await waitFor(() =>
      expect(mockApi.post).toHaveBeenCalledWith("/campaigns/c2/embedding-index/cancel"),
    );
  });

  it("never writes a late rebuild answer into the other campaign's cache", async () => {
    let resolveRetry: (value: unknown) => void = () => {};
    mockApi.get.mockImplementation(
      (() =>
        Promise.resolve({
          data: status({ needs_retry: true, target: summary({ state: "failed" }) }),
        }) as never) as never,
    );
    mockApi.post.mockImplementation(
      (() =>
        new Promise((resolve) => {
          resolveRetry = resolve;
        })) as never,
    );
    const { queryClient, Wrapper } = setup();
    const { rerender } = render(<SettingsEmbeddingIndex campaignId="c1" enabled />, {
      wrapper: Wrapper,
    });

    const retry = await screen.findByRole("button", { name: "Retry rebuild" });
    await waitFor(() => expect(retry).not.toBeDisabled());
    fireEvent.click(retry);

    rerender(<SettingsEmbeddingIndex campaignId="c2" enabled />);
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Retry rebuild" })).toBeInTheDocument(),
    );

    resolveRetry({ data: status({ active: summary({ model: "late-a" }) }) });

    await waitFor(() => {
      const userId = useAuthStore.getState().user?.id ?? null;
      const late = queryClient.getQueryData(embeddingIndexQueryKey(userId, "c1")) as
        | { active?: { model?: string } }
        | undefined;
      expect(late?.active?.model).toBe("late-a");
    });
    const userId = useAuthStore.getState().user?.id ?? null;
    const other = queryClient.getQueryData(embeddingIndexQueryKey(userId, "c2")) as
      | { active?: { model?: string } }
      | undefined;
    expect(other?.active?.model).not.toBe("late-a");
  });

  it("asks for no request when no campaign is selected", () => {
    const { Wrapper } = setup();
    render(<SettingsEmbeddingIndex campaignId={null} enabled />, { wrapper: Wrapper });

    expect(screen.getByText("Open a campaign to see the memory index status.")).toBeInTheDocument();
    expect(mockApi.get).not.toHaveBeenCalled();
  });

  it("asks for no request while the drawer is closed", () => {
    const { Wrapper } = setup();
    render(<SettingsEmbeddingIndex campaignId="c1" enabled={false} />, { wrapper: Wrapper });

    expect(mockApi.get).not.toHaveBeenCalled();
  });
});
