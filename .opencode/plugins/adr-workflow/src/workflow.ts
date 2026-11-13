import { createHash } from "node:crypto";
import { lstatSync, readlinkSync, readFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { git, paths, readState, requireWorkflow, updateState, type Block, type Verdict, type Workflow } from "./store.ts";

function sha(value: string | Buffer): string {
  return createHash("sha256").update(value).digest("hex");
}

function safeRepoPath(root: string, file: string): string {
  if (path.isAbsolute(file) || file.split(/[\\/]/).includes("..")) throw new Error(`Unsafe repository path: ${file}`);
  const full = path.resolve(root, file);
  if (!full.startsWith(`${root}${path.sep}`)) throw new Error(`Path escapes checkout: ${file}`);
  let cursor = root;
  const parts = file.split(/[\\/]/);
  for (const [index, part] of parts.entries()) {
    cursor = path.join(cursor, part);
    try {
      if (lstatSync(cursor).isSymbolicLink() && index < parts.length - 1) throw new Error(`Scope traverses a symlink: ${file}`);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === "ENOENT") break;
      throw error;
    }
  }
  return full;
}

export function fingerprint(root: string, files: string[]): string {
  const actual = paths(root).root;
  const sorted = [...new Set(files)].sort();
  let content = git(actual, "diff", "--cached", "--binary", "HEAD", "--", ...sorted);
  for (const file of sorted) {
    const full = safeRepoPath(actual, file);
    try {
      const stat = lstatSync(full);
      content += `\0${file}\0${stat.mode}\0`;
      if (stat.isSymbolicLink()) content += readlinkSync(full);
      else if (stat.isFile()) {
        try {
          content += readFileSync(full);
        } catch {}
      }
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
  return sha(content);
}

const METADATA_FILES = new Set(["CHANGELOG.md", "docs/adr/README.md"]);

function isMetadataFile(file: string): boolean {
  return METADATA_FILES.has(file);
}

function blockPathsExcludingMetadata(item: Workflow["blocks"][string]): string[] {
  return item.paths.filter((file) => !isMetadataFile(file));
}

function pathsOverlap(left: string[], right: string[]): boolean {
  return left.some((l) =>
    right.some(
      (r) => l === r || l.startsWith(`${r}/`) || r.startsWith(`${l}/`),
    ),
  );
}

function block(state: Workflow, id: string): Workflow["blocks"][string] {
  const found = state.blocks[id];
  if (!found) throw new Error(`Unknown workflow block: ${id}`);
  return found;
}

export function activate(root: string, session: string): Workflow {
  return updateState(root, (prior, actual) => {
    if (prior) return [prior, prior];
    const branch = git(actual.root, "branch", "--show-current");
    const state: Workflow = {
      version: 1,
      root: actual.root,
      gitDir: actual.gitDir,
      branch,
      session,
      maxWriters: 2,
      blocks: {},
    };
    return [state, state];
  });
}

export function bindPlan(root: string, session: string, input: { adr: string; branch: string; base: string; blocks: Block[]; maxWriters?: number }): Workflow {
  const actual = paths(root);
  const adrPath = safeRepoPath(actual.root, input.adr);
  if (lstatSync(adrPath).isSymbolicLink()) throw new Error("Bound ADR must not be a symbolic link");
  const adrHash = sha(readFileSync(adrPath));
  const head = git(actual.root, "rev-parse", "HEAD");
  return updateState(actual.root, (prior, resolved) => {
    if (!prior || prior.session !== session) throw new Error("Activate this session before binding a workflow plan");
    if (prior.adr) {
      const same = prior.adr.path === input.adr && prior.adr.hash === adrHash && prior.branch === input.branch && prior.base === input.base;
      if (!same) throw new Error("Bound ADR, branch, or base differs; refusing silent workflow reset");
      if (prior.boundHead === head) throw new Error("Workflow plan is already bound; resume its existing state");
      if (git(actual.root, "status", "--porcelain")) throw new Error("A new logical block can be bound only after the prior commit leaves a clean tree");
    }
    if (input.branch !== git(actual.root, "branch", "--show-current")) throw new Error("Plan branch does not match the current branch");
    if (!input.blocks.length || new Set(input.blocks.map((b) => b.id)).size !== input.blocks.length) throw new Error("Plan requires uniquely named blocks");
    for (const item of input.blocks) {
      if (!item.paths.length || !item.checks.length) throw new Error(`Block ${item.id} requires explicit paths and checks`);
      for (const file of item.paths) {
        const full = safeRepoPath(actual.root, file);
        const stat = lstatSync(full);
        if (stat.isDirectory()) throw new Error(`Block ${item.id} path ${file} must be a file, not a directory`);
      }
    }
    const state: Workflow = {
      ...prior,
      root: resolved.root,
      gitDir: resolved.gitDir,
      branch: input.branch,
      base: input.base,
      boundHead: head,
      adr: { path: input.adr, hash: adrHash },
      maxWriters: input.maxWriters ?? 2,
      blocks: Object.fromEntries(input.blocks.map((item) => [item.id, { paths: item.paths, checks: item.checks, receipts: [] }])),
    };
    if (state.maxWriters < 1 || state.maxWriters > 3) throw new Error("Writer limit must be between one and three");
    return [state, state];
  });
}

function validateExtensionBlock(root: string, value: unknown): Block {
  if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error("Each extension block must be an object");
  const candidate = value as Record<string, unknown>;
  if (typeof candidate.id !== "string" || !candidate.id.trim()) throw new Error("Block id must be a non-empty string");
  if (!Array.isArray(candidate.paths) || !candidate.paths.length || !candidate.paths.every((file) => typeof file === "string" && file.trim())) {
    throw new Error(`Block ${candidate.id} requires non-empty string paths`);
  }
  if (!Array.isArray(candidate.checks) || !candidate.checks.length || !candidate.checks.every((check) => typeof check === "string" && check.trim())) {
    throw new Error(`Block ${candidate.id} requires non-empty string checks`);
  }
  const files = candidate.paths as string[];
  const checks = candidate.checks as string[];
  if (new Set(files).size !== files.length || new Set(checks).size !== checks.length) throw new Error(`Block ${candidate.id} paths and checks must be unique`);
  for (const file of files) {
    if (file.split(/[\\/]/).some((part) => !part || part === "." || part === "..")) throw new Error(`Unsafe repository path: ${file}`);
    const full = safeRepoPath(root, file);
    try {
      const stat = lstatSync(full);
      if (stat.isSymbolicLink()) throw new Error(`Block ${candidate.id} path ${file} must not be a symbolic link`);
      if (stat.isDirectory()) throw new Error(`Block ${candidate.id} path ${file} must be a file, not a directory`);
      if (!stat.isFile()) throw new Error(`Block ${candidate.id} path ${file} must be a file`);
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== "ENOENT") throw error;
    }
  }
  return { id: candidate.id, paths: files, checks };
}

export function extendPlan(root: string, session: string, input: unknown): Workflow {
  if (!Array.isArray(input) || !input.length) throw new Error("Plan extension requires at least one block");
  return updateState(root, (state, actual) => {
    if (!state || state.session !== session) throw new Error("Only the workflow owner may extend the plan");
    if (state.root !== actual.root || state.gitDir !== actual.gitDir) throw new Error("Workflow registry belongs to another checkout");
    if (state.paused) throw new Error("Resume the workflow before extending its plan");
    if (git(actual.root, "branch", "--show-current") !== state.branch) throw new Error("Current branch differs from the workflow binding");
    if (!state.adr || !state.base || !state.boundHead) throw new Error("Workflow plan is not bound");
    const adrPath = safeRepoPath(actual.root, state.adr.path);
    if (lstatSync(adrPath).isSymbolicLink() || sha(readFileSync(adrPath)) !== state.adr.hash) throw new Error("Bound ADR changed; owner review is required");

    const additions = input.map((value) => validateExtensionBlock(actual.root, value));
    if (new Set(additions.map((item) => item.id)).size !== additions.length) throw new Error("Plan extension requires uniquely named blocks");
    const nextBlocks = { ...state.blocks };
    for (const addition of additions) {
      const prior = state.blocks[addition.id];
      if (!prior) {
        for (const [otherId, other] of Object.entries(state.blocks)) {
          if (other.writer?.state === "active" && pathsOverlap(blockPathsExcludingMetadata(addition), blockPathsExcludingMetadata(other))) {
            throw new Error(`Block ${addition.id} overlaps active writer block ${otherId}`);
          }
        }
        nextBlocks[addition.id] = { paths: addition.paths, checks: addition.checks, receipts: [] };
        continue;
      }
      if (prior.writer?.state === "active") throw new Error(`Block ${addition.id} requires an inactive writer`);
      if (!prior.paths.every((file) => addition.paths.includes(file))) throw new Error(`Block ${addition.id} scope cannot shrink`);
      for (const [otherId, other] of Object.entries(state.blocks)) {
        if (otherId !== addition.id && other.writer?.state === "active" && pathsOverlap(blockPathsExcludingMetadata(addition), blockPathsExcludingMetadata(other))) {
          throw new Error(`Block ${addition.id} overlaps active writer block ${otherId}`);
        }
      }
      nextBlocks[addition.id] = {
        ...prior,
        paths: addition.paths,
        checks: addition.checks,
        receipts: [],
        review: undefined,
      };
    }
    const result: Workflow = { ...state, blocks: nextBlocks };
    return [result, result];
  });
}

export function claimWriter(root: string, id: string, writerSession: string): void {
  updateState(root, (state) => {
    if (!state) throw new Error("Workflow is not active");
    const target = block(state, id);
    const active = Object.values(state.blocks).filter((item) => item.writer?.state === "active").length;
    if (!target.writer && active >= state.maxWriters) throw new Error("Maximum concurrent writers reached");
    if (target.writer?.state === "active") throw new Error(`Block ${id} already has an active writer`);
    for (const [otherId, other] of Object.entries(state.blocks)) {
      if (otherId === id || other.writer?.state !== "active") continue;
      if (
        pathsOverlap(
          blockPathsExcludingMetadata(target),
          blockPathsExcludingMetadata(other),
        )
      ) {
        throw new Error(`Block ${id} overlaps active writer block ${otherId}`);
      }
    }
    target.writer = { session: writerSession, state: "active" };
    return [state, undefined];
  });
}

export function completeWriter(root: string, id: string, writerSession: string): void {
  updateState(root, (state) => {
    if (!state) throw new Error("Workflow is not active");
    const target = block(state, id);
    if (target.writer?.session !== writerSession || target.writer.state !== "active") throw new Error("Writer does not own this active block");
    target.writer.state = "done";
    return [state, undefined];
  });
}

export function runCheck(root: string, session: string, id: string, command: string): { exitCode: number; fingerprint: string } {
  const state = requireWorkflow(root, session);
  const target = block(state, id);
  if (!target.checks.includes(command)) throw new Error("Check command is not registered for this block");
  if (
    Object.values(state.blocks).some(
      (item) =>
        item.writer?.state === "active" &&
        pathsOverlap(blockPathsExcludingMetadata(target), blockPathsExcludingMetadata(item)),
    )
  ) {
    throw new Error("Checks require writers of overlapping blocks to be stopped");
  }
  const before = fingerprint(root, target.paths);
  const result = spawnSync(command, { cwd: state.root, shell: "/bin/sh", encoding: "utf8" });
  const exitCode = result.status ?? 1;
  const after = fingerprint(root, target.paths);
  if (before !== after) throw new Error("Block content changed while the check was running; receipt was not recorded");
  const receipt = { command, exitCode, fingerprint: after };
  updateState(root, (current) => {
    if (!current || current.session !== session) throw new Error("Workflow session mismatch");
    const currentBlock = block(current, id);
    currentBlock.receipts = currentBlock.receipts.filter((item) => item.command !== command);
    currentBlock.receipts.push(receipt);
    currentBlock.review = undefined;
    return [current, receipt];
  });
  return receipt;
}

export function registerReview(root: string, input: { block: string; reviewerSession: string; correctness: Verdict; slop: Verdict }): void {
  updateState(root, (state) => {
    if (!state) throw new Error("Workflow is not active");
    if (input.reviewerSession === state.session) throw new Error("Review must come from an independent session");
    const target = block(state, input.block);
    if (input.reviewerSession === target.writer?.session) throw new Error("An implementer cannot approve their own block");
    const current = fingerprint(root, target.paths);
    if (target.receipts.length !== target.checks.length || target.receipts.some((r) => r.exitCode !== 0 || r.fingerprint !== current)) throw new Error("Fresh successful checks are required before review");
    if (input.correctness !== "pass" && input.correctness !== "fail") throw new Error("Correctness verdict must be pass or fail");
    if (input.slop !== "pass" && input.slop !== "fail") throw new Error("Slop verdict must be pass or fail");
    target.review = { session: input.reviewerSession, correctness: input.correctness, slop: input.slop, fingerprint: current };
    return [state, undefined];
  });
}

export function prepare(root: string): { ready: boolean; reason?: string } {
  const state = readState(root);
  if (!state) return { ready: false, reason: "ADR workflow is not active" };
  if (state.paused) return { ready: false, reason: "ADR workflow is paused" };
  if (state.root !== paths(root).root || state.gitDir !== paths(root).gitDir) return { ready: false, reason: "Workflow registry belongs to another checkout" };
  if (git(root, "branch", "--show-current") !== state.branch) return { ready: false, reason: "Current branch differs from the workflow binding" };
  if (state.adr) {
    const adrPath = safeRepoPath(state.root, state.adr.path);
    if (lstatSync(adrPath).isSymbolicLink() || sha(readFileSync(adrPath)) !== state.adr.hash) return { ready: false, reason: "Bound ADR changed; rebind after owner review" };
  }
  if (Object.values(state.blocks).some((item) => item.writer?.state === "active")) return { ready: false, reason: "Active writers remain" };
  const staged = git(root, "diff", "--cached", "--name-only", "-z").split("\0").filter(Boolean);
  if (!staged.length) return { ready: false, reason: "No staged files to commit" };
  const candidates = Object.entries(state.blocks).filter(([, item]) => {
    const blockFiles = staged.some((file) =>
      !isMetadataFile(file) &&
      file !== state.adr?.path &&
      item.paths.some((scope) => file === scope || file.startsWith(`${scope}/`)),
    );
    if (!blockFiles) return false;
    return staged.every((file) =>
      file === state.adr?.path ||
      isMetadataFile(file) ||
      item.paths.some((scope) => file === scope || file.startsWith(`${scope}/`)),
    );
  });
  if (candidates.length !== 1) return { ready: false, reason: "Stage files for exactly one unambiguous workflow block per commit" };
  for (const [id, item] of candidates) {
    const unstaged = git(root, "diff", "--name-only", "--", ...item.paths).split("\n").filter(Boolean);
    const untracked = git(root, "ls-files", "--others", "--exclude-standard", "--", ...item.paths).split("\n").filter(Boolean);
    if (unstaged.length || untracked.length) return { ready: false, reason: `Block ${id} has unstaged or untracked scoped files` };
    const current = fingerprint(root, item.paths);
    if (item.receipts.length !== item.checks.length || item.receipts.some((r) => r.exitCode !== 0 || r.fingerprint !== current)) return { ready: false, reason: `Block ${id} lacks fresh successful checks` };
    if (!item.review || item.review.correctness !== "pass" || item.review.slop !== "pass" || item.review.fingerprint !== current) return { ready: false, reason: `Block ${id} lacks fresh independent correctness and slop review` };
  }
  return { ready: true };
}

export function pause(root: string, session: string, paused: boolean): void {
  updateState(root, (state) => {
    if (!state || (paused && state.session !== session)) throw new Error("Workflow session mismatch");
    if (!paused) state.session = session;
    state.paused = paused;
    return [state, undefined];
  });
}

export function snapshot(root: string): string {
  const actual = paths(root).root;
  return [
    `Worktree: ${actual}`,
    `Branch: ${git(actual, "branch", "--show-current")}`,
    "Recent commits:",
    git(actual, "log", "-10", "--oneline"),
    "Status:",
    git(actual, "status", "-sb"),
  ].join("\n");
}
