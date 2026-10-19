import { mkdir, readFile, rename, writeFile } from "node:fs/promises";

import { emptySnapshot, snapshotKey, type ProjectPaths, type Snapshot } from "./types";

let writeChain: Promise<void> = Promise.resolve();

export async function readState(paths: ProjectPaths): Promise<Snapshot | null> {
  try {
    const raw = await readFile(paths.stateFile, "utf8");
    return normalize(JSON.parse(raw) as Partial<Snapshot>);
  } catch {
    return null;
  }
}

export async function writeState(paths: ProjectPaths, snapshot: Snapshot): Promise<void> {
  await mkdir(paths.stateDir, { recursive: true });
  const tempFile = `${paths.stateFile}.${process.pid}.tmp`;
  await writeFile(tempFile, `${JSON.stringify(snapshot, null, 2)}\n`, "utf8");
  await rename(tempFile, paths.stateFile);
}

export async function updateState(
  paths: ProjectPaths,
  patch: (current: Snapshot) => Snapshot,
  options: { onlyIfChanged?: boolean } = {},
): Promise<Snapshot> {
  const task = writeChain.then(async () => {
    const current = (await readState(paths)) ?? emptySnapshot();
    const next = patch(current);
    if (options.onlyIfChanged && snapshotKey(current) === snapshotKey(next)) return current;
    next.updatedAt = new Date().toISOString();
    await writeState(paths, next);
    return next;
  });
  writeChain = task.then(
    () => undefined,
    () => undefined,
  );
  return task;
}

function normalize(parsed: Partial<Snapshot>): Snapshot {
  const base = emptySnapshot();
  return {
    ...base,
    ...parsed,
    services: {
      backend: { ...base.services.backend, ...(parsed.services?.backend ?? {}) },
      frontend: { ...base.services.frontend, ...(parsed.services?.frontend ?? {}) },
      database: { ...base.services.database, ...(parsed.services?.database ?? {}) },
    },
    ci: {
      ...base.ci,
      ...(parsed.ci ?? {}),
      checks: { ...(parsed.ci?.checks ?? {}) },
    },
    git: { ...base.git, ...(parsed.git ?? {}) },
    browser: { ...base.browser, ...(parsed.browser ?? {}) },
  };
}
