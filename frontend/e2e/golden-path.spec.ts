import { test, expect } from "@playwright/test";

// All /api calls are mocked in the browser, so this runs without a backend.
const campaign = {
  id: "c1",
  name: "The Dragon Raid",
  template_id: "t1",
  status: "active",
  death_mode: "destino",
  turn_number: 1,
  character_data: {
    name: "Grog",
    level: 1,
    xp: 0,
    hp: { current: 10, max: 10 },
    ac: 12,
    abilities: { strength: 14 },
    skills: {},
    inventory: [],
    equipped: {},
    gold: 0,
    background: "",
    notes: "",
    reputation: {},
    active_quests: [],
  },
  world_state: {},
  quests: {},
  created_at: "now",
  updated_at: "now",
};

test("golden path: login → campaigns → open game", async ({ page }) => {
  await page.route("**/api/auth/login", (r) =>
    r.fulfill({ json: { access_token: "a", refresh_token: "r", token_type: "bearer" } }),
  );
  await page.route("**/api/auth/me", (r) =>
    r.fulfill({ json: { id: "u1", username: "hero", email: "h@x.io" } }),
  );
  await page.route("**/api/campaigns", (r) => r.fulfill({ json: [campaign] }));
  await page.route("**/api/campaigns/c1", (r) => r.fulfill({ json: campaign }));
  await page.route("**/api/journal/c1**", (r) => r.fulfill({ json: [] }));

  await page.goto("/");
  await expect(page).toHaveURL(/\/login/);

  await page.getByLabel("Username").fill("hero");
  await page.getByLabel("Password").fill("secret");
  await page.getByRole("button", { name: /sign in/i }).click();

  await expect(page).toHaveURL(/\/campaigns/);
  await expect(page.getByText("The Dragon Raid")).toBeVisible();

  await page.getByLabel("Open The Dragon Raid").click();
  await expect(page).toHaveURL(/\/game\/c1/);
  await expect(page.getByLabel("Narrative")).toBeVisible();
});
