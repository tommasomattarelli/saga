import { fireEvent, render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import LanguageSelect from "../components/language-select";

vi.mock("../../../shared/api/client", () => ({
  getCampaignLanguages: vi.fn(async () => ({
    data: [
      { code: "en", display_name: "English", is_default: false },
      { code: "it", display_name: "Italian", is_default: true },
      { code: "ja", display_name: "Japanese", is_default: false },
    ],
  })),
}));

describe("campaign language selector", () => {
  it("shows the backend default when no explicit language was selected", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <LanguageSelect value="" onChange={vi.fn()} />
      </QueryClientProvider>,
    );
    await screen.findByRole("option", { name: "Italian (it)" });
    expect(screen.getByRole("combobox", { name: "Campaign language" })).toHaveValue("it");
  });
  it("searches the backend catalog and submits a code, not a display name", async () => {
    const onChange = vi.fn();
    render(
      <QueryClientProvider client={new QueryClient()}>
        <LanguageSelect value="en" onChange={onChange} />
      </QueryClientProvider>,
    );
    await screen.findByRole("option", { name: "Japanese (ja)" });
    fireEvent.change(screen.getByRole("searchbox"), { target: { value: "ital" } });
    expect(screen.queryByRole("option", { name: "Japanese (ja)" })).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole("combobox", { name: "Campaign language" }), {
      target: { value: "it" },
    });
    expect(onChange).toHaveBeenCalledWith("it");
  });
});
