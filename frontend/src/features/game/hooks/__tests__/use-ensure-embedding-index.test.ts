import { createElement, StrictMode, type PropsWithChildren } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderHook } from "@testing-library/react";
import * as client from "../../../../shared/api/client";
import { useAuthStore } from "../../../../shared/stores/auth-store";
import { useEnsureEmbeddingIndex } from "../use-ensure-embedding-index";

vi.mock("../../../../shared/api/client", () => ({
  ensureCampaignEmbeddingIndex: vi.fn(),
}));

const ensure = vi.mocked(client.ensureCampaignEmbeddingIndex);

describe("useEnsureEmbeddingIndex", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    ensure.mockResolvedValue({} as never);
    useAuthStore
      .getState()
      .setTokens({ access_token: "access", refresh_token: "refresh", token_type: "bearer" });
    useAuthStore.getState().setUser({
      id: "user-a",
      username: "test",
      email: "test@example.com",
      preferred_language: "en",
    });
  });

  it("ensures each entered campaign without blocking on request failure", () => {
    ensure.mockRejectedValue(new Error("offline"));
    const { rerender } = renderHook(
      ({ id }: { id: string | undefined }) => useEnsureEmbeddingIndex(id),
      {
        initialProps: { id: "ensure-a" as string | undefined },
      },
    );
    rerender({ id: "ensure-b" });
    rerender({ id: undefined });
    expect(ensure).toHaveBeenCalledTimes(2);
    expect(ensure).toHaveBeenNthCalledWith(1, "ensure-a");
    expect(ensure).toHaveBeenNthCalledWith(2, "ensure-b");
  });

  it("ensures again when a campaign is entered a second time", async () => {
    const { rerender } = renderHook(
      ({ id }: { id: string | undefined }) => useEnsureEmbeddingIndex(id),
      {
        initialProps: { id: "ensure-a" as string | undefined },
      },
    );
    await vi.waitFor(() => expect(ensure).toHaveBeenCalledTimes(1));
    rerender({ id: "ensure-b" });
    await vi.waitFor(() => expect(ensure).toHaveBeenCalledTimes(2));
    rerender({ id: "ensure-a" });
    await vi.waitFor(() => expect(ensure).toHaveBeenCalledTimes(3));
    expect(ensure).toHaveBeenNthCalledWith(3, "ensure-a");
  });

  it("does not ensure without authentication, then ensures again after remount", async () => {
    useAuthStore.getState().logout();
    const { unmount } = renderHook(() => useEnsureEmbeddingIndex("ensure-logout"));
    unmount();
    expect(ensure).not.toHaveBeenCalled();
    useAuthStore
      .getState()
      .setTokens({ access_token: "access", refresh_token: "refresh", token_type: "bearer" });
    useAuthStore.getState().setUser({
      id: "user-a",
      username: "test",
      email: "test@example.com",
      preferred_language: "en",
    });
    const first = renderHook(() => useEnsureEmbeddingIndex("ensure-remount"));
    await vi.waitFor(() => expect(ensure).toHaveBeenCalledTimes(1));
    await new Promise((resolve) => setTimeout(resolve, 0));
    first.unmount();
    renderHook(() => useEnsureEmbeddingIndex("ensure-remount"));
    await vi.waitFor(() => expect(ensure).toHaveBeenCalledTimes(2));
  });

  it("deduplicates strict-mode effects while the same user request is in flight", () => {
    ensure.mockReturnValue(new Promise(() => {}) as never);
    const wrapper = ({ children }: PropsWithChildren) => createElement(StrictMode, null, children);
    renderHook(() => useEnsureEmbeddingIndex("ensure-strict"), { wrapper });
    expect(ensure).toHaveBeenCalledTimes(1);
  });

  it("does not share in-flight requests between authenticated users", () => {
    ensure.mockReturnValue(new Promise(() => {}) as never);
    const { rerender } = renderHook(() => useEnsureEmbeddingIndex("ensure-user-switch"));
    useAuthStore.getState().logout();
    useAuthStore.getState().setTokens({
      access_token: "other-access",
      refresh_token: "other-refresh",
      token_type: "bearer",
    });
    useAuthStore.getState().setUser({
      id: "user-b",
      username: "other",
      email: "other@example.com",
      preferred_language: "en",
    });
    rerender();
    expect(ensure).toHaveBeenCalledTimes(2);
  });
});
