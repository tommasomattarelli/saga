import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, describe, expect, it, vi } from "vitest";
import SettingsCampaignLanguage from "../components/settings-campaign-language";
import { useGameStore } from "../../../shared/stores/game-store";
import { updateCampaignLanguage } from "../../../shared/api/client";
import type { Campaign } from "../../../shared/types";

vi.mock("../../../shared/api/client", () => ({
  getCampaignLanguages: vi.fn(async () => ({
    data: [
      { code: "en", display_name: "English", is_default: true },
      { code: "it", display_name: "Italian", is_default: false },
    ],
  })),
  updateCampaignLanguage: vi.fn(),
}));

describe("campaign language settings", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useGameStore.getState().reset();
    useGameStore
      .getState()
      .setCampaign({ id: "c1", language: "it", world_state: { weather: "rain" } } as Campaign);
  });

  function open() {
    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { mutations: { retry: false } } })}
      >
        <SettingsCampaignLanguage />
      </QueryClientProvider>,
    );
  }

  it("persists the setting and keeps the current in-turn state", async () => {
    vi.mocked(updateCampaignLanguage).mockResolvedValue({
      data: { id: "c1", language: "en" },
    } as Awaited<ReturnType<typeof updateCampaignLanguage>>);
    open();
    const select = await screen.findByRole("combobox", { name: "Campaign language" });
    await screen.findByRole("option", { name: "English (en)" });
    fireEvent.change(select, { target: { value: "en" } });
    await waitFor(() => expect(useGameStore.getState().campaign?.language).toBe("en"));
    expect(updateCampaignLanguage).toHaveBeenCalledWith("c1", "en");
    expect(useGameStore.getState().campaign?.world_state.weather).toBe("rain");
  });

  it("keeps the old selection and reports a failed update", async () => {
    vi.mocked(updateCampaignLanguage).mockRejectedValue(new Error("Offline"));
    open();
    await screen.findByRole("option", { name: "English (en)" });
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "en" } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Couldn't save");
    expect(useGameStore.getState().campaign?.language).toBe("it");
  });
});
