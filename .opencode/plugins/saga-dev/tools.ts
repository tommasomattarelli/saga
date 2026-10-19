import { open, readdir, stat } from "node:fs/promises";
import path from "node:path";

import { runChecks } from "./checks";
import { probeGit, probeServices } from "./probe";
import { readState, updateState } from "./state";
import {
  formatAge,
  projectPaths,
  sanitizeError,
  stripAnsi,
  type CheckResult,
  type ProjectPaths,
  type Snapshot,
} from "./types";

type ToolExecContext = {
  signal?: AbortSignal;
  progress?: (update: { status: string }) => Promise<void> | void;
};

type ToolDefinition = {
  name: string;
  description: string;
  input: Record<string, unknown>;
  execute(input: unknown, context: ToolExecContext): Promise<{ content: string }>;
};

type ToolEditor = {
  add(tool: ToolDefinition): void;
};

export type PluginContext = {
  tool: {
    transform(callback: (editor: ToolEditor) => void): Promise<unknown>;
  };
};

export async function registerTools(ctx: PluginContext, root: string): Promise<void> {
  await ctx.tool.transform((editor) => {
    editor.add({
      name: "saga_status",
      description:
        "Compact SAGA project health: backend/frontend/postgres, last local CI result, git branch and diff. No arguments.",
      input: { type: "object", properties: {}, required: [], additionalProperties: false },
      execute: async () => {
        try {
          return { content: await status(root) };
        } catch (error) {
          return { content: `ERROR: ${sanitizeError(error)}` };
        }
      },
    });

    editor.add({
      name: "saga_check",
      description:
        "Run SAGA local checks. scope=affected|fast|full. Full logs are written under .opencode/state/logs; only a concise summary is returned.",
      input: {
        type: "object",
        properties: {
          scope: { type: "string", enum: ["affected", "fast", "full"], default: "affected" },
          force: { type: "boolean", default: false },
        },
        required: [],
        additionalProperties: false,
      },
      execute: async (input, context) => {
        try {
          return { content: await runCheck(root, input, context) };
        } catch (error) {
          return { content: `ERROR: ${sanitizeError(error)}` };
        }
      },
    });

    editor.add({
      name: "saga_logs",
      description:
        "Return recent filtered SAGA logs. service=backend|frontend|check, level=error|warning|all, limit 1-50.",
      input: {
        type: "object",
        properties: {
          service: { type: "string", enum: ["backend", "frontend", "check"], default: "backend" },
          level: { type: "string", enum: ["error", "warning", "all"], default: "error" },
          limit: { type: "integer", minimum: 1, maximum: 50, default: 10 },
        },
        required: ["service"],
        additionalProperties: false,
      },
      execute: async (input) => {
        try {
          return { content: await logs(root, input) };
        } catch (error) {
          return { content: `ERROR: ${sanitizeError(error)}` };
        }
      },
    });
  });
}

async function status(root: string): Promise<string> {
  const paths = projectPaths(root);
  let snapshot = await readState(paths);
  const stale = !snapshot || Date.now() - Date.parse(snapshot.updatedAt) > 15_000;

  if (stale) {
    const [services, git] = await Promise.all([probeServices(), probeGit(root)]);
    snapshot = await updateState(paths, (current) => {
      const ci = { ...current.ci };
      if (ci.gitSignature) ci.stale = ci.gitSignature !== git.signature;
      return {
        ...current,
        services,
        git: {
          branch: git.branch,
          dirty: git.dirty,
          added: git.added,
          removed: git.removed,
          signature: git.signature,
        },
        ci,
      };
    });
  }

  if (!snapshot) return "SAGA UNKNOWN\nmonitor not ready";
  return formatStatus(snapshot);
}

function formatStatus(snapshot: Snapshot): string {
  const services = snapshot.services;
  const degraded = Object.values(services).some((service) => service.status !== "up");
  const lines = [degraded ? "SAGA DEGRADED" : "SAGA HEALTHY"];
  lines.push(
    `backend=${services.backend.status} frontend=${services.frontend.status} postgres=${services.database.status}`,
  );

  const ci = snapshot.ci;
  const parts: string[] = [];
  if (ci.status === "not-run") {
    parts.push("ci=unknown (run saga_check)");
  } else {
    parts.push(`ci=${ci.status}(${ci.scope ?? "-"},${formatAge(ci.finishedAt)})${ci.stale ? " stale" : ""}`);
    for (const id of ["lint", "format", "types"]) {
      const check = ci.checks[id];
      if (check) parts.push(`${id}=${check.status}`);
    }
    const tests = [ci.checks.backendTests, ci.checks.frontendTests].filter(
      (check): check is CheckResult => check != null,
    );
    if (tests.length > 0) {
      const passed = tests.reduce((total, check) => total + (check.passed ?? 0), 0);
      const failed = tests.reduce((total, check) => total + (check.failed ?? 0), 0);
      parts.push(`tests=${passed}/${passed + failed}`);
    }
  }
  lines.push(parts.join(" "));
  lines.push(`git=${snapshot.git.branch || "-"} dirty=${snapshot.git.dirty} +${snapshot.git.added}/-${snapshot.git.removed}`);
  return lines.join("\n");
}

async function runCheck(root: string, input: unknown, context: ToolExecContext): Promise<string> {
  const args = (input ?? {}) as { scope?: unknown; force?: unknown };
  const scope = args.scope ?? "affected";
  if (scope !== "affected" && scope !== "fast" && scope !== "full") {
    return "ERROR: scope must be affected, fast, or full";
  }
  const result = await runChecks({
    root,
    scope,
    force: args.force === true,
    signal: context.signal,
    progress: context.progress,
  });
  return result.summary;
}

async function logs(root: string, input: unknown): Promise<string> {
  const args = (input ?? {}) as { service?: unknown; level?: unknown; limit?: unknown };
  const service =
    args.service === "frontend" || args.service === "check" || args.service === "backend" ? args.service : "backend";
  const level = args.level === "warning" || args.level === "all" || args.level === "error" ? args.level : "error";
  const requested = typeof args.limit === "number" && Number.isFinite(args.limit) ? Math.floor(args.limit) : 10;
  const limit = Math.min(50, Math.max(1, requested));
  const paths = projectPaths(root);

  if (service === "backend") {
    return backendLogs(paths, level, limit);
  }
  return checkLogs(paths, root, service, level, limit);
}

async function backendLogs(paths: ProjectPaths, level: "error" | "warning" | "all", limit: number): Promise<string> {
  const text = await tailFile(paths.backendLog, 1_000_000);
  if (!text) return `no backend log at ${path.relative(paths.root, paths.backendLog)}`;
  const matching: string[] = [];
  for (const line of text.split("\n")) {
    const entry = parseJsonObject(line);
    if (!entry) continue;
    const entryLevel = String(entry.level ?? "").toLowerCase();
    if (level !== "all" && entryLevel !== level) continue;
    const timestamp = String(entry.timestamp ?? "").slice(11, 19);
    const rawEvent = entry.event ?? entry.msg ?? entry.message ?? "";
    const event = typeof rawEvent === "string" ? rawEvent : JSON.stringify(rawEvent);
    matching.push(`${timestamp} ${entryLevel} ${event}`.trim().slice(0, 220));
  }
  if (matching.length === 0) return `no ${level} logs in the recent backend log`;
  return matching.slice(-limit).join("\n");
}

async function checkLogs(
  paths: ProjectPaths,
  root: string,
  service: "frontend" | "check",
  level: "error" | "warning" | "all",
  limit: number,
): Promise<string> {
  const latest = await latestCheckLog(paths.logsDir);
  if (!latest) return "no check logs yet; run saga_check";
  const text = stripAnsi(await tailFile(latest, 2_000_000));
  const sections = splitSections(text);
  const selected =
    service === "frontend"
      ? sections.filter((section) => section.header.replaceAll("\\", "/").includes("/frontend"))
      : sections;
  if (selected.length === 0) {
    return service === "frontend"
      ? "no frontend section in the latest check log; run saga_check (fast or full)"
      : "no command sections in the latest check log";
  }

  const body = selected.map((section) => `${section.header}\n${section.body}`).join("\n");
  const lines = filterLines(body, level).slice(-limit);
  if (lines.length === 0) return `no ${level} lines in ${path.relative(root, latest)}`;
  return [`log: ${path.relative(root, latest)}`, ...lines].join("\n");
}

async function latestCheckLog(logsDir: string): Promise<string | null> {
  const entries = await readdir(logsDir).catch(() => [] as string[]);
  const files = entries.filter((name) => name.startsWith("check-") && name.endsWith(".log"));
  const stats = await Promise.all(
    files.map(async (name) => ({
      name,
      mtimeMs: (await stat(path.join(logsDir, name)).catch(() => ({ mtimeMs: 0 }))).mtimeMs,
    })),
  );
  stats.sort((left, right) => right.mtimeMs - left.mtimeMs);
  return stats[0] ? path.join(logsDir, stats[0].name) : null;
}

type Section = { header: string; body: string };

function splitSections(text: string): Section[] {
  const sections: Section[] = [];
  let current: Section | null = null;
  for (const line of text.split("\n")) {
    if (line.startsWith("$ ")) {
      if (current) sections.push(current);
      current = { header: line, body: "" };
    } else if (current) {
      current.body += `${line}\n`;
    }
  }
  if (current) sections.push(current);
  return sections;
}

function filterLines(text: string, level: "error" | "warning" | "all"): string[] {
  const lines = text
    .split("\n")
    .map((line) => line.trimEnd())
    .filter((line) => line.trim().length > 0);
  if (level === "all") return lines.map((line) => line.slice(0, 220));
  const pattern = level === "error" ? /(^|\s)(error|failed|✗|×)(\s|:|$)/i : /(^|\s)warn(ing)?(\s|:|$)/i;
  return lines.filter((line) => pattern.test(line)).map((line) => line.slice(0, 220));
}

function parseJsonObject(line: string): Record<string, unknown> | null {
  try {
    const parsed: unknown = JSON.parse(line);
    if (typeof parsed === "object" && parsed !== null && !Array.isArray(parsed)) {
      return parsed as Record<string, unknown>;
    }
    return null;
  } catch {
    return null;
  }
}

async function tailFile(file: string, maxBytes: number): Promise<string> {
  const info = await stat(file).catch(() => null);
  if (!info || info.size === 0) return "";
  const start = Math.max(0, info.size - maxBytes);
  const handle = await open(file, "r");
  try {
    const buffer = Buffer.alloc(info.size - start);
    await handle.read(buffer, 0, buffer.length, start);
    const text = buffer.toString("utf8");
    if (start === 0) return text;
    const firstNewline = text.indexOf("\n");
    return firstNewline === -1 ? "" : text.slice(firstNewline + 1);
  } finally {
    await handle.close();
  }
}
