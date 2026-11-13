import { chmodSync, existsSync, readFileSync, renameSync, unlinkSync, writeFileSync } from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { git } from "./store.ts";

function hookDir(root: string): string {
  const config = spawnSync("git", ["config", "--show-origin", "--get", "core.hooksPath"], { cwd: root, encoding: "utf8" });
  if (config.status === 0) throw new Error(`Refusing hook install: custom core.hooksPath is configured (${config.stdout.trim()})`);
  return path.resolve(root, git(root, "rev-parse", "--git-path", "hooks"));
}

function wrapper(hook: string): string {
  const original = `${hook}.saga-original`;
  return `#!/bin/sh
set -eu
original="$(dirname "$0")/${original}"
git_dir="$(git rev-parse --absolute-git-dir)"
common_dir="$(git rev-parse --path-format=absolute --git-common-dir)"
linked=false
if [ "$git_dir" != "$common_dir" ]; then linked=true; fi
run() {
  if [ "$linked" = true ]; then
    (unset GIT_DIR GIT_WORK_TREE GIT_INDEX_FILE GIT_COMMON_DIR GIT_PREFIX GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES; "$@")
  else
    "$@"
  fi
}
if [ -f "$original" ]; then run "$original" "$@"; fi
repo_root="$(git rev-parse --show-toplevel)"
cli="$repo_root/.opencode/plugins/adr-workflow/src/cli.ts"
if [ -f "$cli" ]; then run node --experimental-strip-types "$cli" gate; fi
`;
}

export function installHooks(root: string): void {
  const directory = hookDir(root);
  const wanted = ["pre-commit", "commit-msg"];
  for (const hook of wanted) {
    const target = path.join(directory, hook);
    const backup = `${target}.saga-original`;
    const contents = wrapper(hook);
    if (existsSync(target) && readFileSync(target, "utf8") === contents) continue;
    if (existsSync(backup)) throw new Error(`Refusing to overwrite existing hook backup: ${backup}`);
    if (existsSync(target)) renameSync(target, backup);
    writeFileSync(target, contents, { mode: 0o755, flag: "wx" });
    chmodSync(target, 0o755);
  }
}

export function uninstallHooks(root: string): void {
  const directory = hookDir(root);
  for (const hook of ["pre-commit", "commit-msg"]) {
    const target = path.join(directory, hook);
    const backup = `${target}.saga-original`;
    if (!existsSync(target)) continue;
    const expected = wrapper(hook);
    if (readFileSync(target, "utf8") !== expected) throw new Error(`Refusing to remove edited or unknown hook: ${target}`);
    if (existsSync(backup)) renameSync(backup, target);
    else unlinkSync(target);
  }
}
