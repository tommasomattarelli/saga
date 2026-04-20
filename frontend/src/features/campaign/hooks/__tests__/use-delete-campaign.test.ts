import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { useDeleteCampaign } from "../use-delete-campaign";
import { createWrapper } from "../../../../shared/utils/test-utils";
import * as client from "../../../../shared/api/client";

vi.mock("../../../../shared/api/client", () => ({
  deleteCampaign: vi.fn(),
}));

const mockDeleteCampaign = vi.mocked(client.deleteCampaign);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useDeleteCampaign", () => {
  it("calls deleteCampaign with the correct id", async () => {
    mockDeleteCampaign.mockResolvedValue({ data: null } as never);

    const { result } = renderHook(() => useDeleteCampaign(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync("campaign-42");
    });

    expect(mockDeleteCampaign).toHaveBeenCalledWith("campaign-42");
  });

  it("mutation is in success state after delete", async () => {
    mockDeleteCampaign.mockResolvedValue({ data: null } as never);

    const { result } = renderHook(() => useDeleteCampaign(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate("campaign-1");
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("mutation is in error state when delete fails", async () => {
    mockDeleteCampaign.mockRejectedValue(new Error("Not found"));

    const { result } = renderHook(() => useDeleteCampaign(), {
      wrapper: createWrapper(),
    });

    act(() => {
      result.current.mutate("campaign-x");
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
