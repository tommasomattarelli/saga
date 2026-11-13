import { execFileSync } from "node:child_process";
import { mkdirSync, openSync, closeSync, readFileSync, renameSync, rmSync, writeFileSync } from "node:fs";
import path from "node:path";

export type Verdict = "pass" | "fail";
export interface Block {
  id: string;
  paths: string[];
  checks: string[];
}
export interface Workflow {
  version: 1;
  root: string;
  gitDir: string;
  branch: string;
  session: string;
  paused?: boolean;
  adr?: { path: string; hash: string };
  base?: string;
  boundHead?: string;
  maxWriters: number;
  blocks: Record<string, {
    paths: string[];
    checks: string[];
    writer?: { session: string; state: "active" | "done" };
    receipts: Array<{ command: string; exitCode: number; fingerprint: string }>;
    review?: { session: string; correctness: Verdict; slop: Verdict; fingerprint: string };
  }>;
}

export function git(root: string, ...args: string[]): string {
  return execFileSync("git", args, { cwd: root, encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] }).trim();
}

export function paths(root: string): { root: string; gitDir: string; state: string } {
  const actualRoot = git(root, "rev-parse", "--show-toplevel");
  const gitDir = git(actualRoot, "rev-parse", "--absolute-git-dir");
  const stateDir = path.join(gitDir, "saga-workflow");
  return { root: actualRoot, gitDir, state: path.join(stateDir, "state.json") };
}

function withLock<T>(stateFile: string, action: () => T): T {
  const lock = `${stateFile}.lock`;
  mkdirSync(path.dirname(lock), { recursive: true });
  let fd: number | undefined;
  while (fd === undefined) {
    try {
      fd = openSync(lock, "wx", 0o600);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "EEXIST") throw error;
      let owner = 0;
      try {
        owner = Number(readFileSync(lock, "utf8"));
      } catch (readError) {
        if ((readError as NodeJS.ErrnoException).code !== "ENOENT") throw readError;
      }
      if (Number.isInteger(owner) && owner > 0) {
        try {
          process.kill(owner, 0);
        } catch (probeError) {
          if ((probeError as NodeJS.ErrnoException).code === "ESRCH") rmSync(lock, { force: true });
        }
      }
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 20);
    }
  }
  writeFileSync(fd, String(process.pid));
  try {
    return action();
  } finally {
    closeSync(fd);
    rmSync(lock, { force: true });
  }
}

export function readState(root: string): Workflow | undefined {
  const target = paths(root);
  try {
    return JSON.parse(readFileSync(target.state, "utf8")) as Workflow;
  } catch (error) {
    if ((error as NodeJS.ErrnoException).code === "ENOENT") return undefined;
    throw error;
  }
}

export function updateState<T>(root: string, action: (state: Workflow | undefined, actual: ReturnType<typeof paths>) => [Workflow, T]): T {
  const actual = paths(root);
  return withLock(actual.state, () => {
    const prior = readState(actual.root);
    const [state, result] = action(prior, actual);
    const temp = `${actual.state}.${process.pid}.tmp`;
    writeFileSync(temp, `${JSON.stringify(state, null, 2)}\n`, { mode: 0o600 });
    renameSync(temp, actual.state);
    return result;
  });
}

export function requireWorkflow(root: string, session: string): Workflow {
  const state = readState(root);
  if (!state) throw new Error("ADR workflow is not active in this checkout");
  if (state.root !== paths(root).root || state.gitDir !== paths(root).gitDir) throw new Error("Workflow registry belongs to a different checkout");
  if (state.session !== session) throw new Error(`Workflow is bound to session ${state.session}, not ${session}`);
  if (git(root, "branch", "--show-current") !== state.branch) throw new Error("Current branch differs from the workflow binding");
  return state;
}
