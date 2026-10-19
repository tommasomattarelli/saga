import { createHash } from "node:crypto";
import path from "node:path";

export type CheckScope = "affected" | "fast" | "full";
export type ServiceStatus = "up" | "down" | "unknown";
export type RunStatus = "pass" | "fail" | "skipped" | "unavailable";
export type CiStatus = "pass" | "fail" | "not-run";

export type ServiceInfo = {
  status: ServiceStatus;
  port: number;
  latencyMs: number | null;
  detail: string | null;
};

export type ServicesSnapshot = {
  backend: ServiceInfo;
  frontend: ServiceInfo;
  database: ServiceInfo;
};

export type CheckResult = {
  status: RunStatus;
  durationMs?: number;
  passed?: number | null;
  failed?: number | null;
  detail?: string | null;
};

export type CiSnapshot = {
  scope: CheckScope | null;
  status: CiStatus;
  finishedAt: string | null;
  fingerprint: string | null;
  gitSignature: string | null;
  stale: boolean;
  checks: Record<string, CheckResult>;
  lastFailure: {
    check: string;
    summary: string;
    logPath: string;
  } | null;
};

export type GitSnapshot = {
  branch: string;
  dirty: number;
  added: number;
  removed: number;
  signature: string;
};

export type BrowserSnapshot = {
  status: "pass" | "fail" | "unavailable";
  reason: string | null;
  url: string | null;
  consoleErrors: number | null;
  networkFailures: number | null;
  checkedAt: string | null;
  durationMs: number | null;
};

export type Snapshot = {
  schema: 1;
  updatedAt: string;
  services: ServicesSnapshot;
  ci: CiSnapshot;
  git: GitSnapshot;
  browser: BrowserSnapshot;
};

export type ProjectPaths = {
  root: string;
  stateDir: string;
  stateFile: string;
  logsDir: string;
  cacheDir: string;
  lockFile: string;
  backendDir: string;
  frontendDir: string;
  backendLog: string;
};

export function projectPaths(root: string): ProjectPaths {
  const stateDir = path.join(root, ".opencode", "state");
  return {
    root,
    stateDir,
    stateFile: path.join(stateDir, "saga-dev.json"),
    logsDir: path.join(stateDir, "logs"),
    cacheDir: path.join(stateDir, "cache"),
    lockFile: path.join(stateDir, "saga-check.lock"),
    backendDir: path.join(root, "backend"),
    frontendDir: path.join(root, "frontend"),
    backendLog: path.join(root, "backend", "logs", "saga.log"),
  };
}

export function emptySnapshot(): Snapshot {
  return {
    schema: 1,
    updatedAt: new Date(0).toISOString(),
    services: {
      backend: { status: "unknown", port: 8000, latencyMs: null, detail: null },
      frontend: { status: "unknown", port: 3000, latencyMs: null, detail: null },
      database: { status: "unknown", port: 5432, latencyMs: null, detail: null },
    },
    ci: {
      scope: null,
      status: "not-run",
      finishedAt: null,
      fingerprint: null,
      gitSignature: null,
      stale: false,
      checks: {},
      lastFailure: null,
    },
    git: { branch: "", dirty: 0, added: 0, removed: 0, signature: "" },
    browser: {
      status: "unavailable",
      reason: "not run",
      url: null,
      consoleErrors: null,
      networkFailures: null,
      checkedAt: null,
      durationMs: null,
    },
  };
}

export function sha1(value: string): string {
  return createHash("sha1").update(value).digest("hex");
}

export function nowIso(): string {
  return new Date().toISOString();
}

export function formatAge(iso: string | null, now = Date.now()): string {
  if (!iso) return "never";
  const elapsed = now - Date.parse(iso);
  if (!Number.isFinite(elapsed) || elapsed < 0) return "now";
  const seconds = Math.floor(elapsed / 1000);
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

export function formatDuration(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  const minutes = Math.floor(ms / 60_000);
  const seconds = Math.round((ms % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

const ANSI = /\u001b\[[0-9;]*m/g;

export function stripAnsi(value: string): string {
  return value.replace(ANSI, "");
}

export function sanitizeError(error: unknown): string {
  const raw = errorMessage(error);
  const first = raw
    .split("\n")
    .map((line) => line.trim())
    .find(Boolean);
  return (first ?? "unexpected error").replace(/\/[^\s:]+/g, "<path>").slice(0, 240);
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (typeof error === "object" && error !== null) {
    const record = error as Record<string, unknown>;
    if (typeof record.message === "string") return record.message;
    if (typeof record.code === "string") return record.code;
    const text = String(error);
    if (text && text !== "[object Object]") return text;
    try {
      const json = JSON.stringify(error);
      if (json && json !== "{}") return json;
    } catch {
      // Fall through to the generic message.
    }
  }
  return "unexpected error";
}

export function snapshotKey(snapshot: Snapshot): string {
  return JSON.stringify({
    services: {
      backend: { status: snapshot.services.backend.status, port: snapshot.services.backend.port, detail: snapshot.services.backend.detail },
      frontend: { status: snapshot.services.frontend.status, port: snapshot.services.frontend.port, detail: snapshot.services.frontend.detail },
      database: { status: snapshot.services.database.status, port: snapshot.services.database.port, detail: snapshot.services.database.detail },
    },
    ci: snapshot.ci,
    git: snapshot.git,
    browser: snapshot.browser,
  });
}
