import { createRequire } from "node:module";
import path from "node:path";

import { probeFrontend } from "./probe";
import { nowIso, sanitizeError, type BrowserSnapshot } from "./types";

type Locator = {
  fill(value: string): Promise<void>;
  click(): Promise<void>;
  waitFor(options: { state: "visible"; timeout: number }): Promise<void>;
};

type Route = {
  fulfill(options: { json: unknown }): Promise<void>;
};

type Page = {
  on(event: "console", listener: (message: { type(): string; text(): string }) => void): void;
  on(event: "requestfailed", listener: (request: { url(): string; failure(): { errorText?: string } | null }) => void): void;
  on(event: "response", listener: (response: { url(): string; status(): number }) => void): void;
  route(url: string, handler: (route: Route) => void): Promise<void>;
  goto(url: string, options: { waitUntil: "domcontentloaded"; timeout: number }): Promise<unknown>;
  getByLabel(text: string): Locator;
  getByRole(role: string, options: { name: RegExp }): Locator;
  getByText(text: string): Locator;
  waitForURL(url: RegExp, options: { timeout: number }): Promise<void>;
  waitForTimeout(ms: number): Promise<void>;
  url(): string;
};

type Browser = {
  newPage(): Promise<Page>;
  close(): Promise<void>;
};

type Chromium = {
  launch(options: { channel?: string; headless: boolean }): Promise<Browser>;
};

const PROBE_TIMEOUT_MS = 20_000;
const IGNORED_CONSOLE = [
  /\[vite\]/i,
  /WebSocket connection .* failed/i,
  /Download the React DevTools/i,
  /net::ERR_ABORTED/i,
];
const IGNORED_NETWORK = [/net::ERR_ABORTED/i, /NS_BINDING_ABORTED/i];

const CAMPAIGN = {
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

export async function runBrowserProbe(root: string): Promise<BrowserSnapshot> {
  const started = Date.now();
  const frontend = await probeFrontend();
  if (frontend.status !== "up") {
    return unavailable("frontend down", started);
  }

  let chromium: Chromium;
  try {
    const requireFromFrontend = createRequire(path.join(root, "frontend", "package.json"));
    chromium = (requireFromFrontend("playwright") as { chromium: Chromium }).chromium;
  } catch (error) {
    return unavailable(`playwright unavailable: ${sanitizeError(error)}`, started);
  }

  let browser: Browser | null = null;
  let page: Page | null = null;
  let raceTimer: ReturnType<typeof setTimeout> | null = null;
  const consoleErrors = new Set<string>();
  const networkFailures = new Set<string>();

  const probe = async (): Promise<BrowserSnapshot> => {
    browser = await chromium.launch({ channel: "chrome", headless: true });
    page = await browser.newPage();

    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const text = message.text();
      if (!IGNORED_CONSOLE.some((pattern) => pattern.test(text))) consoleErrors.add(text);
    });
    page.on("requestfailed", (request) => {
      const failure = request.failure()?.errorText ?? "request failed";
      if (!IGNORED_NETWORK.some((pattern) => pattern.test(failure))) {
        networkFailures.add(`${request.url()} ${failure}`);
      }
    });
    page.on("response", (response) => {
      if (response.status() >= 500) networkFailures.add(`${response.url()} HTTP ${response.status()}`);
    });

    await page.route("**/api/auth/login", (route) =>
      route.fulfill({ json: { access_token: "a", refresh_token: "r", token_type: "bearer" } }),
    );
    await page.route("**/api/auth/me", (route) =>
      route.fulfill({ json: { id: "u1", username: "hero", email: "h@x.io" } }),
    );
    await page.route("**/api/campaigns", (route) => route.fulfill({ json: [CAMPAIGN] }));
    await page.route("**/api/campaigns/c1", (route) => route.fulfill({ json: CAMPAIGN }));
    await page.route("**/api/journal/c1**", (route) => route.fulfill({ json: [] }));

    await page.goto("http://localhost:3000/login", { waitUntil: "domcontentloaded", timeout: 10_000 });
    await page.getByLabel("Username").fill("hero");
    await page.getByLabel("Password").fill("secret");
    await page.getByRole("button", { name: /sign in/i }).click();
    await page.waitForURL(/\/campaigns/, { timeout: 10_000 });
    await page.getByText("The Dragon Raid").waitFor({ state: "visible", timeout: 5_000 });
    await page.waitForTimeout(500);

    const failed = consoleErrors.size > 0 || networkFailures.size > 0;
    return {
      status: failed ? "fail" : "pass",
      reason: failed ? `${consoleErrors.size} console, ${networkFailures.size} network` : null,
      url: page.url(),
      consoleErrors: consoleErrors.size,
      networkFailures: networkFailures.size,
      checkedAt: nowIso(),
      durationMs: Date.now() - started,
    };
  };

  try {
    return await Promise.race([
      probe(),
      new Promise<BrowserSnapshot>((_, reject) => {
        raceTimer = setTimeout(() => reject(new Error("browser probe timed out")), PROBE_TIMEOUT_MS);
      }),
    ]);
  } catch (error) {
    const reason = sanitizeError(error);
    if (reason.includes("Chromium distribution") || reason.includes("Executable doesn't exist")) {
      return unavailable("chrome not found", started);
    }
    return {
      status: "fail",
      reason,
      url: page?.url() ?? null,
      consoleErrors: consoleErrors.size,
      networkFailures: networkFailures.size,
      checkedAt: nowIso(),
      durationMs: Date.now() - started,
    };
  } finally {
    if (raceTimer) clearTimeout(raceTimer);
    await browser?.close().catch(() => undefined);
  }
}

function unavailable(reason: string, started: number): BrowserSnapshot {
  return {
    status: "unavailable",
    reason,
    url: null,
    consoleErrors: null,
    networkFailures: null,
    checkedAt: nowIso(),
    durationMs: Date.now() - started,
  };
}
