import net from "node:net";
import { stat } from "node:fs/promises";
import path from "node:path";

import { exec } from "./exec";
import { readState, updateState } from "./state";
import {
  emptySnapshot,
  projectPaths,
  sanitizeError,
  sha1,
  type GitSnapshot,
  type ServiceInfo,
  type ServicesSnapshot,
  type Snapshot,
} from "./types";

const PROBE_TIMEOUT_MS = 800;
const MONITOR_INTERVAL_MS = 10_000;

export type GitProbe = GitSnapshot & { changedPaths: string[] };

export async function probeServices(): Promise<ServicesSnapshot> {
  const [backend, frontend, database] = await Promise.all([
    probeBackend(),
    probeFrontend(),
    probeTcp(5432, ["127.0.0.1", "localhost"]),
  ]);
  return { backend, frontend, database };
}

export async function probeBackend(): Promise<ServiceInfo> {
  return probeHttp(8000, ["http://127.0.0.1:8000/openapi.json", "http://localhost:8000/openapi.json"], (_response, body) =>
    body.includes("\"openapi\""),
  );
}

export async function probeFrontend(): Promise<ServiceInfo> {
  return probeHttp(3000, ["http://localhost:3000/", "http://127.0.0.1:3000/"], (response) =>
    (response.headers.get("content-type") ?? "").includes("text/html"),
  );
}

async function probeHttp(
  port: number,
  urls: string[],
  validate: (response: Response, body: string) => boolean,
): Promise<ServiceInfo> {
  let detail: string | null = null;
  for (const url of urls) {
    const started = Date.now();
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);
    try {
      const response = await fetch(url, { signal: controller.signal, redirect: "manual" });
      const body = await response.text();
      if (response.ok && validate(response, body)) {
        return { status: "up", port, latencyMs: Date.now() - started, detail: null };
      }
      detail = `HTTP ${response.status}`;
    } catch (error) {
      detail = sanitizeError(error);
    } finally {
      clearTimeout(timer);
    }
  }
  return { status: "down", port, latencyMs: null, detail: detail ?? "unreachable" };
}

async function probeTcp(port: number, hosts: string[]): Promise<ServiceInfo> {
  let detail: string | null = null;
  for (const host of hosts) {
    const started = Date.now();
    try {
      await new Promise<void>((resolve, reject) => {
        const socket = net.createConnection({ host, port });
        const timer = setTimeout(() => {
          socket.destroy();
          reject(new Error("timeout"));
        }, PROBE_TIMEOUT_MS);
        socket.once("connect", () => {
          clearTimeout(timer);
          socket.end();
          resolve();
        });
        socket.once("error", (error) => {
          clearTimeout(timer);
          socket.destroy();
          reject(error);
        });
      });
      return { status: "up", port, latencyMs: Date.now() - started, detail: null };
    } catch (error) {
      detail = sanitizeError(error);
    }
  }
  return { status: "down", port, latencyMs: null, detail: detail ?? "unreachable" };
}

export async function probeGit(root: string): Promise<GitProbe> {
  const [status, branch, numstat, diff] = await Promise.all([
    runGit(root, ["status", "--porcelain=v1", "-uall"]),
    runGit(root, ["branch", "--show-current"]),
    runGit(root, ["diff", "HEAD", "--numstat"]),
    runGit(root, ["diff", "HEAD"]),
  ]);

  const statusText = status.stdout;
  const changedPaths = parseStatusPaths(statusText);
  const dirty = statusText.split("\n").filter((line) => line.trim().length > 0).length;
  const { added, removed } = parseNumstat(numstat.stdout);
  const untrackedSignature = await hashUntracked(root, statusText);
  const signature = sha1([branch.stdout.trim(), statusText, diff.stdout, untrackedSignature].join("\0"));

  return {
    branch: branch.stdout.trim() || "(detached)",
    dirty,
    added,
    removed,
    signature,
    changedPaths,
  };
}

async function runGit(root: string, args: string[]): Promise<{ stdout: string; exitCode: number | null }> {
  try {
    const result = await exec("git", args, { cwd: root, timeoutMs: 10_000 });
    return { stdout: result.stdout, exitCode: result.exitCode };
  } catch {
    return { stdout: "", exitCode: null };
  }
}

function parseStatusPaths(output: string): string[] {
  const paths: string[] = [];
  for (const line of output.split("\n")) {
    if (!line.trim()) continue;
    const entry = line.slice(3);
    if (!entry) continue;
    const renamed = entry.includes(" -> ") ? entry.split(" -> ").pop() : entry;
    if (renamed) paths.push(renamed.replace(/^"|"$/g, ""));
  }
  return paths;
}

function parseNumstat(output: string): { added: number; removed: number } {
  let added = 0;
  let removed = 0;
  for (const line of output.split("\n")) {
    if (!line.trim()) continue;
    const [rawAdded, rawRemoved] = line.split("\t");
    if (rawAdded && rawAdded !== "-") added += Number(rawAdded) || 0;
    if (rawRemoved && rawRemoved !== "-") removed += Number(rawRemoved) || 0;
  }
  return { added, removed };
}

async function hashUntracked(root: string, status: string): Promise<string> {
  const entries = status
    .split("\n")
    .filter((line) => line.startsWith("?? "))
    .map((line) => line.slice(3).replace(/^"|"$/g, ""));
  if (entries.length === 0) return "";
  const stats = await Promise.all(
    entries.map(async (entry) => {
      try {
        const info = await stat(path.join(root, entry));
        return `${entry}:${info.mtimeMs}:${info.size}`;
      } catch {
        return `${entry}:missing`;
      }
    }),
  );
  return stats.join("\n");
}

export function startMonitor(root: string): () => void {
  const paths = projectPaths(root);
  let stopped = false;
  let running = false;

  const tick = async (): Promise<void> => {
    if (stopped || running) return;
    running = true;
    try {
      const [services, git] = await Promise.all([probeServices(), probeGit(root)]);
      await updateState(
        paths,
        (current: Snapshot) => {
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
        },
        { onlyIfChanged: true },
      );
    } catch (error) {
      console.error(`saga-dev monitor: ${sanitizeError(error)}`);
    } finally {
      running = false;
    }
  };

  void tick();
  const timer = setInterval(() => void tick(), MONITOR_INTERVAL_MS);
  timer.unref?.();

  return () => {
    stopped = true;
    clearInterval(timer);
  };
}

export async function ensureState(root: string): Promise<Snapshot> {
  const paths = projectPaths(root);
  const current = await readState(paths);
  return current ?? emptySnapshot();
}
