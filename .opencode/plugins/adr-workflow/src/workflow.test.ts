import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { mkdtempSync, mkdirSync, readFileSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, test } from "node:test";
import { runCli } from "./cli.ts";
import { activate, bindPlan, claimWriter, completeWriter, extendPlan, pause, rebindPlan, registerReview, runCheck } from "./workflow.ts";
import { paths, readState } from "./store.ts";

const roots: string[] = [];
const hash = (value: string): string => createHash("sha256").update(value).digest("hex");

afterEach(() => {
  for (const root of roots.splice(0)) rmSync(root, { recursive: true, force: true });
});

function repository(): string {
  const root = mkdtempSync(path.join(os.tmpdir(), "saga-workflow-"));
  roots.push(root);
  execFileSync("git", ["init", "-q", "-b", "feat/test"], { cwd: root });
  execFileSync("git", ["config", "user.email", "test@example.invalid"], { cwd: root });
  execFileSync("git", ["config", "user.name", "Test"], { cwd: root });
  mkdirSync(path.join(root, "docs", "adr"), { recursive: true });
  mkdirSync(path.join(root, "src"), { recursive: true });
  writeFileSync(path.join(root, "docs/adr/0001-test.md"), "ADR\n");
  writeFileSync(path.join(root, "src/one.ts"), "one\n");
  writeFileSync(path.join(root, "src/two.ts"), "two\n");
  execFileSync("git", ["add", "."], { cwd: root });
  execFileSync("git", ["commit", "-qm", "baseline"], { cwd: root });
  return root;
}

function bound(root: string): void {
  activate(root, "owner");
  bindPlan(root, "owner", {
    adr: "docs/adr/0001-test.md",
    branch: "feat/test",
    base: "main",
    blocks: [
      { id: "one", paths: ["src/one.ts"], checks: ["true"] },
      { id: "two", paths: ["src/two.ts"], checks: ["true"] },
    ],
  });
}

test("extend conservatively updates affected scopes and adds blocks without losing unrelated proof", () => {
  const root = repository();
  bound(root);
  writeFileSync(path.join(root, "src/one.ts"), "one dirty\n");
  writeFileSync(path.join(root, "src/untracked.txt"), "untracked\n");
  const dirtyStatus = execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" });
  const trackedContent = readFileSync(path.join(root, "src/one.ts"), "utf8");
  const untrackedContent = readFileSync(path.join(root, "src/untracked.txt"), "utf8");
  assert.notEqual(dirtyStatus, "");
  claimWriter(root, "one", "writer-one");
  completeWriter(root, "one", "writer-one");
  runCheck(root, "owner", "one", "true");
  registerReview(root, { block: "one", reviewerSession: "reviewer-one", correctness: "pass", slop: "pass" });
  claimWriter(root, "two", "writer-two");
  completeWriter(root, "two", "writer-two");
  runCheck(root, "owner", "two", "true");
  registerReview(root, { block: "two", reviewerSession: "reviewer-two", correctness: "pass", slop: "pass" });
  const before = readState(root)!;
  assert.ok(before.blocks.one.review);
  assert.ok(before.blocks.two.review);

  extendPlan(root, "owner", [
    { id: "one", paths: ["src/one.ts", "src/new-test.ts"], checks: ["true", "printf ok"] },
    { id: "utility", paths: ["src/workflow-test.ts"], checks: ["true"] },
  ]);

  const after = readState(root)!;
  assert.deepEqual(after.blocks.two, before.blocks.two);
  assert.deepEqual(after.blocks.one.writer, { session: "writer-one", state: "done" });
  assert.deepEqual(after.blocks.one.receipts, []);
  assert.equal(after.blocks.one.review, undefined);
  assert.deepEqual(after.blocks.two.review, before.blocks.two.review);
  assert.deepEqual(after.blocks.one.paths, ["src/one.ts", "src/new-test.ts"]);
  assert.deepEqual(after.blocks.one.checks, ["true", "printf ok"]);
  assert.deepEqual(after.blocks.utility, { paths: ["src/workflow-test.ts"], checks: ["true"], receipts: [] });
  assert.equal(after.adr?.hash, before.adr?.hash);
  assert.equal(after.boundHead, before.boundHead);
  assert.equal(after.branch, before.branch);
  assert.equal(readFileSync(path.join(root, "src/one.ts"), "utf8"), trackedContent);
  assert.equal(readFileSync(path.join(root, "src/untracked.txt"), "utf8"), untrackedContent);
  assert.equal(execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" }), dirtyStatus);
});

test("extend rejects non-owner, active affected writer, and overlap with another active writer atomically", () => {
  const root = repository();
  bound(root);
  const before = readFileSync(paths(root).state, "utf8");
  assert.throws(() => extendPlan(root, "not-owner", [{ id: "one", paths: ["src/one.ts"], checks: ["true"] }]), /owner/i);
  claimWriter(root, "one", "writer-one");
  const activeOne = readFileSync(paths(root).state, "utf8");
  assert.throws(() => extendPlan(root, "owner", [{ id: "one", paths: ["src/one.ts"], checks: ["true"] }]), /inactive/i);
  assert.equal(readFileSync(paths(root).state, "utf8"), activeOne);
  completeWriter(root, "one", "writer-one");
  claimWriter(root, "two", "writer-two");
  const activeBoth = readFileSync(paths(root).state, "utf8");
  assert.throws(
    () => extendPlan(root, "owner", [{ id: "one", paths: ["src/one.ts", "src/two.ts"], checks: ["true"] }]),
    /overlaps active writer block two/,
  );
  assert.equal(readFileSync(paths(root).state, "utf8"), activeBoth);
  assert.notEqual(activeOne, before);
});

test("extend rejects scope shrink, invalid data, directories, and symlink traversal", () => {
  const root = repository();
  bound(root);
  claimWriter(root, "one", "writer-one");
  completeWriter(root, "one", "writer-one");
  mkdirSync(path.join(root, "src", "folder"));
  symlinkSync(path.join(root, "src"), path.join(root, "linked"));
  const invalid: Array<{ id: string; paths: string[]; checks: string[] }> = [
    { id: "one", paths: [], checks: ["true"] },
    { id: "one", paths: ["src/one.ts"], checks: [] },
    { id: "one", paths: ["src/one.ts", "src/one.ts"], checks: ["true"] },
    { id: "one", paths: ["../escape"], checks: ["true"] },
    { id: "one", paths: ["./src/one.ts"], checks: ["true"] },
    { id: "one", paths: ["src/folder"], checks: ["true"] },
    { id: "one", paths: ["linked/new.ts"], checks: ["true"] },
    { id: "", paths: ["src/file.ts"], checks: ["true"] },
    { id: "utility", paths: ["src/file.ts"], checks: [" "] },
  ];
  const beforeInvalid = readFileSync(paths(root).state, "utf8");
  for (const entry of invalid) {
    assert.throws(() => extendPlan(root, "owner", [entry]));
    assert.equal(readFileSync(paths(root).state, "utf8"), beforeInvalid);
  }
  assert.throws(() => extendPlan(root, "owner", [{ id: "one", paths: ["src/other.ts"], checks: ["true"] }]), /shrink/i);
});

test("extend revalidates the bound branch and ADR before changing the ledger", () => {
  const root = repository();
  bound(root);
  const before = readFileSync(paths(root).state, "utf8");
  execFileSync("git", ["checkout", "-qb", "other"], { cwd: root });
  assert.throws(() => extendPlan(root, "owner", [{ id: "utility", paths: ["src/new.ts"], checks: ["true"] }]), /branch/i);
  assert.equal(readFileSync(paths(root).state, "utf8"), before);
  execFileSync("git", ["checkout", "-q", "feat/test"], { cwd: root });
  writeFileSync(path.join(root, "docs/adr/0001-test.md"), "changed ADR\n");
  assert.throws(() => extendPlan(root, "owner", [{ id: "utility", paths: ["src/new.ts"], checks: ["true"] }]), /ADR changed/i);
  assert.equal(readFileSync(paths(root).state, "utf8"), before);
});

test("CLI exposes the additive extend operation", () => {
  const root = repository();
  bound(root);
  const result = runCli(
    ["extend", JSON.stringify([{ id: "utility", paths: ["src/new.ts"], checks: ["true"] }])],
    root,
    "owner",
  ) as { blocks: Record<string, unknown> };
  assert.ok(result.blocks.utility);
  assert.match(runCli(["help"], root, "owner") as string, /extend/);
});

test("owner rebinds a reviewed ADR hash with compare-and-swap and invalidates every proof", () => {
  const root = repository();
  bound(root);
  for (const id of ["one", "two"]) {
    claimWriter(root, id, `writer-${id}`);
    completeWriter(root, id, `writer-${id}`);
    runCheck(root, "owner", id, "true");
    registerReview(root, { block: id, reviewerSession: `reviewer-${id}`, correctness: "pass", slop: "pass" });
  }
  const before = readState(root)!;
  const oldHash = before.adr!.hash;
  const adrFile = path.join(root, before.adr!.path);
  writeFileSync(adrFile, "reviewed ADR replacement\n");
  const replacementHash = hash(readFileSync(adrFile, "utf8"));
  const dirtyStatus = execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" });

  const after = rebindPlan(root, "owner", { expectedHash: oldHash, replacementHash });

  assert.equal(after.adr?.hash, replacementHash);
  assert.equal(after.boundHead, before.boundHead);
  assert.equal(after.base, before.base);
  assert.equal(after.branch, before.branch);
  assert.equal(after.root, before.root);
  assert.equal(after.gitDir, before.gitDir);
  assert.equal(after.maxWriters, before.maxWriters);
  assert.deepEqual(after.blocks.one.paths, before.blocks.one.paths);
  assert.deepEqual(after.blocks.one.checks, before.blocks.one.checks);
  assert.deepEqual(after.blocks.one.writer, before.blocks.one.writer);
  assert.deepEqual(after.blocks.two.writer, before.blocks.two.writer);
  for (const item of Object.values(after.blocks)) {
    assert.deepEqual(item.receipts, []);
    assert.equal(item.review, undefined);
  }
  assert.equal(readFileSync(adrFile, "utf8"), "reviewed ADR replacement\n");
  assert.equal(execFileSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" }), dirtyStatus);
});

test("rebind rejects stale or mismatched hashes, non-owner, no-op, and preserves state", () => {
  const root = repository();
  bound(root);
  const adrFile = path.join(root, "docs/adr/0001-test.md");
  const originalHash = readState(root)!.adr!.hash;
  const beforeNoOp = readFileSync(paths(root).state, "utf8");
  assert.throws(() => rebindPlan(root, "owner", { expectedHash: originalHash, replacementHash: originalHash }), /same|unchanged|no-op/i);
  assert.equal(readFileSync(paths(root).state, "utf8"), beforeNoOp);
  writeFileSync(adrFile, "replacement\n");
  const before = readFileSync(paths(root).state, "utf8");
  const replacementHash = hash(readFileSync(adrFile, "utf8"));
  const unchanged = (): void => assert.equal(readFileSync(paths(root).state, "utf8"), before);

  assert.throws(() => rebindPlan(root, "not-owner", { expectedHash: "stale", replacementHash }), /owner/i);
  unchanged();
  assert.throws(() => rebindPlan(root, "owner", { expectedHash: "stale", replacementHash }), /expected|stale/i);
  unchanged();
  assert.throws(() => rebindPlan(root, "owner", { expectedHash: readState(root)!.adr!.hash, replacementHash: "wrong" }), /actual|replacement|hash/i);
  unchanged();
});

test("rebind rejects paused, active-writer, branch-mismatched, checkout-mismatched, and symlinked ADR bindings atomically", () => {
  const root = repository();
  bound(root);
  const adrFile = path.join(root, "docs/adr/0001-test.md");
  writeFileSync(adrFile, "replacement\n");
  const replacementHash = hash(readFileSync(adrFile, "utf8"));
  const attempt = (): void => rebindPlan(root, "owner", { expectedHash: readState(root)!.adr!.hash, replacementHash });
  const unchangedAttempt = (): void => {
    const state = readFileSync(paths(root).state, "utf8");
    assert.throws(attempt);
    assert.equal(readFileSync(paths(root).state, "utf8"), state);
    assert.equal(readFileSync(adrFile, "utf8"), "replacement\n");
  };

  claimWriter(root, "one", "writer-one");
  unchangedAttempt();
  completeWriter(root, "one", "writer-one");
  const stateBeforePause = readFileSync(paths(root).state, "utf8");
  pause(root, "owner", true);
  const paused = readFileSync(paths(root).state, "utf8");
  assert.throws(attempt, /resume|paused/i);
  assert.equal(readFileSync(paths(root).state, "utf8"), paused);
  pause(root, "owner", false);
  assert.notEqual(readFileSync(paths(root).state, "utf8"), stateBeforePause);

  execFileSync("git", ["checkout", "-qb", "other"], { cwd: root });
  unchangedAttempt();
  execFileSync("git", ["checkout", "-q", "feat/test"], { cwd: root });
  const state = readState(root)!;
  state.root = `${root}-other`;
  writeFileSync(paths(root).state, `${JSON.stringify(state, null, 2)}\n`);
  unchangedAttempt();
  state.root = root;
  writeFileSync(paths(root).state, `${JSON.stringify(state, null, 2)}\n`);

  rmSync(adrFile);
  const missingState = readFileSync(paths(root).state, "utf8");
  assert.throws(attempt);
  assert.equal(readFileSync(paths(root).state, "utf8"), missingState);
  symlinkSync(path.join(root, "src/one.ts"), adrFile);
  const symlinkState = readFileSync(paths(root).state, "utf8");
  assert.throws(attempt, /symbolic link/i);
  assert.equal(readFileSync(paths(root).state, "utf8"), symlinkState);
});

test("ordinary bind still refuses an unnoticed ADR change and CLI exposes explicit rebind", () => {
  const root = repository();
  bound(root);
  writeFileSync(path.join(root, "docs/adr/0001-test.md"), "changed\n");
  assert.throws(
    () => bindPlan(root, "owner", {
      adr: "docs/adr/0001-test.md",
      branch: "feat/test",
      base: "main",
      blocks: [{ id: "one", paths: ["src/one.ts"], checks: ["true"] }],
    }),
    /differs|reset/i,
  );
  const replacementHash = hash(readFileSync(path.join(root, "docs/adr/0001-test.md"), "utf8"));
  const result = runCli(
    ["rebind", JSON.stringify({ expectedHash: readState(root)!.adr!.hash, replacementHash })],
    root,
    "owner",
  ) as { adr: { hash: string } };
  assert.equal(result.adr.hash, replacementHash);
  assert.match(runCli(["help"], root, "owner") as string, /rebind/);
});
