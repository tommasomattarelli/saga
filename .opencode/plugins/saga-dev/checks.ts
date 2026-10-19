import { appendFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import net from "node:net";
import path from "node:path";

import { runBrowserProbe } from "./browser";
import { backendCommand, exec, formatCommand, frontendCommand } from "./exec";
import { probeGit } from "./probe";
import { updateState } from "./state";
import {
  formatDuration,
  nowIso,
  projectPaths,
  sanitizeError,
  sha1,
  stripAnsi,
  type BrowserSnapshot,
  type CheckResult,
  type CheckScope,
  type CiSnapshot,
  type ProjectPaths,
} from "./types";

const CHECK_VERSION = 1;
const MAX_LOG_BYTES = 5 * 1024 * 1024;
const MAX_LOCK_MS = 30 * 60 * 1000;
const TEST_DATABASE_URL = "postgresql+asyncpg://saga_test:saga_test@localhost:5433/saga_test";

export type CommandSpec = {
  id: string;
  label: string;
  cmd: string;
  args: string[];
  cwd: string;
  timeoutMs: number;
  env?: Record<string, string>;
};

type SkippedCheck = { id: string; label: string; detail: string };

type Plan = {
  commands: CommandSpec[];
  skipped: SkippedCheck[];
  empty: boolean;
};

export type RunOptions = {
  root: string;
  scope: CheckScope;
  force?: boolean;
  signal?: AbortSignal;
  progress?: (update: { status: string }) => Promise<void> | void;
};

export type RunResult =
  | {
      kind: "done";
      status: "pass" | "fail";
      summary: string;
      logPath: string;
      cached: boolean;
      checks: Record<string, CheckResult>;
      browser: BrowserSnapshot | null;
    }
  | { kind: "busy"; summary: string };

type CacheEntry = {
  version: number;
  scope: CheckScope;
  fingerprint: string;
  createdAt: string;
  status: "pass" | "fail";
  summary: string;
  logPath: string;
  checks: Record<string, CheckResult>;
  browser: BrowserSnapshot | null;
};

export async function runChecks(options: RunOptions): Promise<RunResult> {
  const { root, scope, force = false, signal, progress } = options;
  const paths = projectPaths(root);
  const startedAt = Date.now();
  const git = await probeGit(root);
  const plan = buildPlan(root, scope, git.changedPaths);

  if (plan.empty) {
    return {
      kind: "done",
      status: "pass",
      summary: `PASS ${scope} (no relevant changes)\nlog: -`,
      logPath: "",
      cached: false,
      checks: {},
      browser: null,
    };
  }

  const fingerprint = sha1(
    [scope, CHECK_VERSION, git.signature, plan.commands.map((command) => command.id).join(",")].join("\0"),
  );

  if (!force && scope !== "full") {
    const cached = await readCache(paths, scope, fingerprint);
    if (cached) {
      return {
        kind: "done",
        status: cached.status,
        summary: `${cached.summary}\n(cached — working tree unchanged)`,
        logPath: cached.logPath,
        cached: true,
        checks: cached.checks,
        browser: cached.browser,
      };
    }
  }

  const lock = await acquireLock(paths, scope);
  if (!lock.ok) return { kind: "busy", summary: `BUSY ${lock.info}` };

  await mkdir(paths.logsDir, { recursive: true });
  const logPath = path.join(paths.logsDir, `check-${timestamp()}-${scope}.log`);
  const header = `SAGA CHECK ${scope} ${nowIso()}\nroot: ${root}\ngit: ${git.branch} ${git.signature}\n`;
  await writeFile(logPath, header, "utf8");
  let logBytes = Buffer.byteLength(header);
  const writeLog = async (text: string): Promise<void> => {
    if (logBytes >= MAX_LOG_BYTES) return;
    const slice = text.slice(0, MAX_LOG_BYTES - logBytes);
    if (!slice) return;
    await appendFile(logPath, slice, "utf8");
    logBytes += Buffer.byteLength(slice);
  };

  const checks: Record<string, CheckResult> = {};
  const failures: { id: string; lines: string[] }[] = [];
  let browser: BrowserSnapshot | null = null;
  let startedTestDb = false;

  try {
    for (const skipped of plan.skipped) {
      checks[skipped.id] = { status: "skipped", detail: skipped.detail };
    }

    let commands = plan.commands;
    if (scope === "full") {
      await progress?.({ status: "test database" });
      const database = await ensureTestDb(root);
      startedTestDb = database.started;
      if (!database.ok) {
        const detail = database.detail ?? "test database unavailable";
        checks.backendTests = { status: "fail", detail };
        failures.push({ id: "backendTests", lines: [`test DB: ${detail}`] });
        commands = commands.filter((command) => command.id !== "backendTests");
        await writeLog(`\n[test database] ${detail}\n`);
      }
    }

    for (const spec of commands) {
      if (signal?.aborted) throw new Error("check aborted");
      await progress?.({ status: spec.label });
      await writeLog(`\n$ cd ${spec.cwd} && ${formatCommand(spec.cmd, spec.args)}\n`);
      const result = await exec(spec.cmd, spec.args, {
        cwd: spec.cwd,
        env: spec.env,
        timeoutMs: spec.timeoutMs,
        signal,
      });
      const output = stripAnsi([result.stdout, result.stderr].filter(Boolean).join("\n"));
      await writeLog(
        `exit=${result.exitCode} duration=${result.durationMs}ms${result.timedOut ? " (timeout)" : ""}\n${output}\n`,
      );
      const status = result.exitCode === 0 ? "pass" : "fail";
      const counts = parseCounts(spec.id, output);
      checks[spec.id] = {
        status,
        durationMs: result.durationMs,
        passed: counts.passed,
        failed: counts.failed,
      };
      if (status === "fail") failures.push({ id: spec.id, lines: summarizeFailure(output) });
    }

    if (scope === "full" && !signal?.aborted) {
      await progress?.({ status: "browser" });
      browser = await runBrowserProbe(root);
      checks.browser = {
        status: browser.status === "pass" ? "pass" : browser.status === "unavailable" ? "skipped" : "fail",
        durationMs: browser.durationMs ?? undefined,
        detail: browser.reason,
      };
      await writeLog(
        `\nbrowser: ${browser.status} console=${browser.consoleErrors ?? "-"} network=${browser.networkFailures ?? "-"}${
          browser.reason ? ` reason=${browser.reason}` : ""
        }\n`,
      );
      if (browser.status === "fail") {
        failures.push({ id: "browser", lines: [browser.reason ?? "browser probe failed"] });
      }
    }

    const status: "pass" | "fail" = failures.length > 0 ? "fail" : "pass";
    const finishedAt = nowIso();
    const lastFailure =
      failures.length > 0
        ? {
            check: failures[0].id,
            summary: failures[0].lines.join("\n") || "check failed",
            logPath,
          }
        : null;

    const ci: CiSnapshot = {
      scope,
      status,
      finishedAt,
      fingerprint,
      gitSignature: git.signature,
      stale: false,
      checks,
      lastFailure,
    };

    await updateState(paths, (current) => ({
      ...current,
      ci,
      browser: browser ?? current.browser,
    }));

    const summary = buildSummary(status, scope, startedAt, checks, failures, logPath, root);
    if (scope !== "full") {
      await writeCache(paths, {
        version: CHECK_VERSION,
        scope,
        fingerprint,
        createdAt: finishedAt,
        status,
        summary,
        logPath,
        checks,
        browser,
      }).catch(() => undefined);
    }

    return { kind: "done", status, summary, logPath, cached: false, checks, browser };
  } finally {
    if (startedTestDb) await dockerCompose(root, ["down"], 60_000).catch(() => undefined);
    await releaseLock(paths);
  }
}

function buildPlan(root: string, scope: CheckScope, changedPaths: string[]): Plan {
  const commands = new Map<string, CommandSpec>();
  const skipped = new Map<string, SkippedCheck>();

  if (scope === "fast") {
    add(commands, backendSpec(root, "lint", "backend lint", ["ruff", "check", "."], 60_000));
    add(commands, backendSpec(root, "format", "backend format", ["ruff", "format", "--check", "."], 60_000));
    add(commands, backendSpec(root, "types", "backend types", ["mypy"], 120_000));
    add(
      commands,
      backendSpec(root, "backendTests", "backend tests", ["python", "-m", "pytest", "tests/unit", "--noconftest", "-q"], 180_000),
    );
    add(commands, frontendSpec(root, "frontendLint", "frontend lint", ["npm", "run", "lint"], 60_000));
    add(
      commands,
      frontendSpec(root, "frontendFormat", "frontend format", ["npx", "prettier", "--check", "src/**/*.{ts,tsx,json,css}"], 60_000),
    );
    add(commands, frontendSpec(root, "frontendTypes", "frontend types", ["npx", "tsc", "--noEmit"], 120_000));
    add(commands, frontendSpec(root, "frontendTests", "frontend tests", ["npx", "vitest", "run"], 180_000));
    return { commands: [...commands.values()], skipped: [], empty: false };
  }

  if (scope === "full") {
    add(commands, backendSpec(root, "lint", "backend lint", ["ruff", "check", "."], 60_000));
    add(commands, backendSpec(root, "format", "backend format", ["ruff", "format", "--check", "."], 60_000));
    add(commands, backendSpec(root, "types", "backend types", ["mypy"], 120_000));
    add(commands, backendSpec(root, "vulture", "backend vulture", ["vulture", "app", "--min-confidence", "80"], 60_000));
    add(
      commands,
      backendSpec(
        root,
        "backendTests",
        "backend tests",
        ["python", "-m", "pytest", "tests/unit", "tests/integration", "tests/playtest", "-q"],
        600_000,
        { TEST_DATABASE_URL },
      ),
    );
    add(commands, frontendSpec(root, "frontendLint", "frontend lint", ["npm", "run", "lint"], 60_000));
    add(
      commands,
      frontendSpec(root, "frontendFormat", "frontend format", ["npx", "prettier", "--check", "src/**/*.{ts,tsx,json,css}"], 60_000),
    );
    add(commands, frontendSpec(root, "frontendTypes", "frontend types", ["npx", "tsc", "--noEmit"], 120_000));
    add(
      commands,
      frontendSpec(root, "frontendCoverage", "frontend tests", ["npm", "run", "test:coverage", "--", "--run"], 300_000),
    );
    add(commands, frontendSpec(root, "knip", "frontend knip", ["npm", "run", "knip"], 120_000));
    add(commands, frontendSpec(root, "build", "frontend build", ["npm", "run", "build"], 180_000));
    return { commands: [...commands.values()], skipped: [], empty: false };
  }

  const changed = changedPaths.map((value) => value.replaceAll("\\", "/"));
  const backendPython = changed.filter((value) => value.startsWith("backend/") && value.endsWith(".py"));
  const backendUnitTests = backendPython.filter(
    (value) => value.startsWith("backend/tests/unit/") && /(^|\/)test_[^/]*\.py$/.test(value),
  );
  const backendIntegrationTests = backendPython.filter(
    (value) => value.startsWith("backend/tests/integration/") || value.startsWith("backend/tests/playtest/"),
  );

  if (backendPython.length > 0) {
    add(commands, backendSpec(root, "lint", "backend lint", ["ruff", "check", "."], 60_000));
    add(commands, backendSpec(root, "types", "backend types", ["mypy"], 120_000));
  }
  if (backendUnitTests.length > 0) {
    add(
      commands,
      backendSpec(
        root,
        "backendTests",
        "backend tests",
        [
          "python",
          "-m",
          "pytest",
          ...backendUnitTests.map((value) => value.slice("backend/".length)),
          "--noconftest",
          "-q",
        ],
        180_000,
      ),
    );
  } else if (backendIntegrationTests.length > 0) {
    skipped.set("backendTests", {
      id: "backendTests",
      label: "backend integration",
      detail: "richiede il DB test; usa scope fast o full",
    });
  }

  const installPython = changed.filter((value) => value.startsWith("install/tests/") && value.endsWith(".py"));
  if (installPython.length > 0) {
    add(commands, backendSpec(root, "installLint", "install lint", ["ruff", "check", "../install/tests"], 60_000));
    add(
      commands,
      backendSpec(root, "installTests", "install tests", ["python", "-m", "pytest", "../install/tests", "--noconftest", "-q"], 180_000),
    );
  }

  const frontendTs = changed.filter((value) => value.startsWith("frontend/src/") && /\.(ts|tsx)$/.test(value));
  const frontendStyle = changed.filter((value) => value.startsWith("frontend/src/") && /\.(css|json)$/.test(value));
  const frontendConfig = changed.some((value) =>
    [
      "frontend/package.json",
      "frontend/vite.config.ts",
      "frontend/tsconfig.json",
      "frontend/tsconfig.app.json",
      "frontend/tsconfig.node.json",
      "frontend/.node-version",
    ].includes(value),
  );

  if (frontendTs.length > 0) {
    const files = frontendTs.map((value) => value.slice("frontend/".length));
    add(commands, frontendSpec(root, "frontendLint", "frontend lint", ["npx", "eslint", ...files], 60_000));
    add(commands, frontendSpec(root, "frontendFormat", "frontend format", ["npx", "prettier", "--check", ...files], 60_000));
    add(commands, frontendSpec(root, "frontendTests", "frontend tests", ["npx", "vitest", "related", "--run", ...files], 180_000));
    add(commands, frontendSpec(root, "frontendTypes", "frontend types", ["npx", "tsc", "--noEmit"], 120_000));
  } else if (frontendConfig) {
    add(commands, frontendSpec(root, "frontendLint", "frontend lint", ["npx", "eslint", "."], 60_000));
    add(
      commands,
      frontendSpec(root, "frontendFormat", "frontend format", ["npx", "prettier", "--check", "src/**/*.{ts,tsx,json,css}"], 60_000),
    );
    add(commands, frontendSpec(root, "frontendTypes", "frontend types", ["npx", "tsc", "--noEmit"], 120_000));
    add(commands, frontendSpec(root, "frontendTests", "frontend tests", ["npx", "vitest", "run"], 180_000));
  }
  if (frontendStyle.length > 0) {
    add(
      commands,
      frontendSpec(
        root,
        "frontendFormat",
        "frontend format",
        ["npx", "prettier", "--check", ...frontendStyle.map((value) => value.slice("frontend/".length))],
        60_000,
      ),
    );
  }

  const yaml = changed.filter((value) => /\.ya?ml$/.test(value));
  if (yaml.length > 0) {
    add(
      commands,
      backendSpec(
        root,
        "configTests",
        "config tests",
        ["python", "-m", "pytest", "tests/unit/test_config.py", "tests/unit/ai/test_gameplay_config.py", "--noconftest", "-q"],
        120_000,
      ),
    );
  }

  return {
    commands: [...commands.values()],
    skipped: [...skipped.values()],
    empty: commands.size === 0 && skipped.size === 0,
  };
}

function add(commands: Map<string, CommandSpec>, spec: CommandSpec): void {
  if (!commands.has(spec.id)) commands.set(spec.id, spec);
}

function backendSpec(
  root: string,
  id: string,
  label: string,
  args: string[],
  timeoutMs: number,
  env?: Record<string, string>,
): CommandSpec {
  const command = backendCommand(args);
  return { id, label, cmd: command.cmd, args: command.args, cwd: path.join(root, "backend"), timeoutMs, env };
}

function frontendSpec(root: string, id: string, label: string, args: string[], timeoutMs: number): CommandSpec {
  const command = frontendCommand(root, args);
  return { id, label, cmd: command.cmd, args: command.args, cwd: path.join(root, "frontend"), timeoutMs };
}

function buildSummary(
  status: "pass" | "fail",
  scope: CheckScope,
  startedAt: number,
  checks: Record<string, CheckResult>,
  failures: { id: string; lines: string[] }[],
  logPath: string,
  root: string,
): string {
  const lines = [`${status === "pass" ? "PASS" : "FAIL"} ${scope} (${formatDuration(Date.now() - startedAt)})`];
  const parts: string[] = [];
  for (const [id, check] of Object.entries(checks)) {
    if (check.status === "skipped") continue;
    if (check.passed != null) {
      parts.push(`${id}=${check.passed}/${check.passed + (check.failed ?? 0)}`);
    } else if (id === "browser") {
      parts.push(`browser=${check.status}`);
    } else {
      parts.push(`${id}=${check.status}`);
    }
  }
  if (parts.length > 0) lines.push(parts.join(" "));

  for (const failure of failures.slice(0, 3)) {
    const first = failure.lines[0] ?? "failed";
    lines.push(`${failure.id}: ${first.slice(0, 160)}`);
    for (const line of failure.lines.slice(1, 4)) lines.push(`  ${line.slice(0, 160)}`);
  }

  lines.push(`log: ${path.relative(root, logPath)}`);
  return lines.join("\n");
}

async function acquireLock(paths: ProjectPaths, scope: CheckScope): Promise<{ ok: true } | { ok: false; info: string }> {
  await mkdir(paths.stateDir, { recursive: true });
  try {
    await writeFile(
      paths.lockFile,
      JSON.stringify({ pid: process.pid, scope, startedAt: nowIso() }),
      { encoding: "utf8", flag: "wx" },
    );
    return { ok: true };
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
    const raw = await readFile(paths.lockFile, "utf8").catch(() => "");
    const info = parseLock(raw);
    const age = info ? Date.now() - Date.parse(info.startedAt) : Number.POSITIVE_INFINITY;
    const stale = !info || !pidAlive(info.pid) || age > MAX_LOCK_MS;
    if (stale) {
      await rm(paths.lockFile, { force: true });
      return acquireLock(paths, scope);
    }
    return {
      ok: false,
      info: `${info?.scope ?? "check"} running since ${info?.startedAt ?? "unknown"}`,
    };
  }
}

async function releaseLock(paths: ProjectPaths): Promise<void> {
  await rm(paths.lockFile, { force: true }).catch(() => undefined);
}

function parseLock(raw: string): { pid: number; scope: string; startedAt: string } | null {
  try {
    const parsed = JSON.parse(raw) as { pid?: unknown; scope?: unknown; startedAt?: unknown };
    if (typeof parsed.pid !== "number" || typeof parsed.scope !== "string" || typeof parsed.startedAt !== "string") {
      return null;
    }
    return { pid: parsed.pid, scope: parsed.scope, startedAt: parsed.startedAt };
  } catch {
    return null;
  }
}

function pidAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
}

async function readCache(
  paths: ProjectPaths,
  scope: CheckScope,
  fingerprint: string,
): Promise<CacheEntry | null> {
  try {
    const raw = await readFile(path.join(paths.cacheDir, `${scope}-${fingerprint}.json`), "utf8");
    const entry = JSON.parse(raw) as CacheEntry;
    if (entry.version !== CHECK_VERSION || entry.fingerprint !== fingerprint) return null;
    return entry;
  } catch {
    return null;
  }
}

async function writeCache(paths: ProjectPaths, entry: CacheEntry): Promise<void> {
  await mkdir(paths.cacheDir, { recursive: true });
  await writeFile(
    path.join(paths.cacheDir, `${entry.scope}-${entry.fingerprint}.json`),
    `${JSON.stringify(entry, null, 2)}\n`,
    "utf8",
  );
}

async function ensureTestDb(root: string): Promise<{ ok: boolean; started: boolean; detail: string | null }> {
  if (await portOpen(5433)) return { ok: true, started: false, detail: null };
  const up = await dockerCompose(root, ["up", "-d", "--wait"], 120_000);
  if (up.exitCode !== 0) {
    return {
      ok: false,
      started: false,
      detail: sanitizeError(up.stderr || up.stdout || "docker compose up failed"),
    };
  }
  return { ok: true, started: true, detail: null };
}

async function dockerCompose(root: string, args: string[], timeoutMs: number) {
  return exec("docker", ["compose", "-f", "docker-compose.test.yml", ...args], { cwd: root, timeoutMs });
}

function portOpen(port: number): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    const timer = setTimeout(() => {
      socket.destroy();
      resolve(false);
    }, 800);
    socket.once("connect", () => {
      clearTimeout(timer);
      socket.end();
      resolve(true);
    });
    socket.once("error", () => {
      clearTimeout(timer);
      socket.destroy();
      resolve(false);
    });
  });
}

function parseCounts(id: string, output: string): { passed: number | null; failed: number | null } {
  if (id === "backendTests" || id === "installTests") {
    const passed = numberMatch(output, /(\d+) passed/);
    const failed = numberMatch(output, /(\d+) failed/);
    return { passed, failed: failed ?? (passed == null ? null : 0) };
  }
  if (id === "frontendTests" || id === "frontendCoverage") {
    const passed = numberMatch(output, /Tests\s+(\d+) passed/);
    const failed = numberMatch(output, /Tests\s+(\d+) failed/);
    return { passed, failed: failed ?? (passed == null ? null : 0) };
  }
  return { passed: null, failed: null };
}

function numberMatch(output: string, pattern: RegExp): number | null {
  const match = pattern.exec(output);
  if (!match) return null;
  const value = Number(match[1]);
  return Number.isFinite(value) ? value : null;
}

function summarizeFailure(output: string): string[] {
  const lines = stripAnsi(output)
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const patterns = [
    /^FAILED\s+/,
    /^×\s+/,
    /^E\s{2,}/,
    /error TS\d+:/,
    /^Found \d+ error/,
    /^[^\s]+\.(py|ts|tsx|css):\d+:\d+:/,
    /^\d+\s+\|\s+/,
    /^.*:\d+:\d+: [A-Z]\d+ /,
  ];
  const matches = lines.filter((line) => patterns.some((pattern) => pattern.test(line))).slice(0, 8);
  const selected = matches.length > 0 ? matches : lines.slice(-3);
  return selected.map((line) => line.slice(0, 200));
}

function timestamp(): string {
  const date = new Date();
  const pad = (value: number): string => String(value).padStart(2, "0");
  return [
    `${date.getFullYear()}${pad(date.getMonth() + 1)}${pad(date.getDate())}`,
    `${pad(date.getHours())}${pad(date.getMinutes())}${pad(date.getSeconds())}`,
  ].join("-");
}
