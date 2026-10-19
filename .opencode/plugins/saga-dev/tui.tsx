import { readFile, stat } from "node:fs/promises";

import { Plugin } from "@opencode/plugin/tui";
import { createSignal, onCleanup, onMount } from "solid-js";

import {
  formatAge,
  formatDuration,
  projectPaths,
  type BrowserSnapshot,
  type CheckResult,
  type CiSnapshot,
  type ServiceInfo,
  type ServiceStatus,
  type Snapshot,
} from "./types";

type SlotProps = {
  sessionID?: string;
  name?: string;
  close?: () => void;
  width?: number;
  presentation?: string;
  focused?: boolean;
};

function useSnapshot(root: string): () => Snapshot | null {
  const [snapshot, setSnapshot] = createSignal<Snapshot | null>(null);

  onMount(() => {
    const file = projectPaths(root).stateFile;
    let lastMtime = 0;
    let stopped = false;

    const tick = async (): Promise<void> => {
      try {
        const info = await stat(file);
        if (info.mtimeMs === lastMtime) return;
        lastMtime = info.mtimeMs;
        const parsed = JSON.parse(await readFile(file, "utf8")) as Snapshot;
        if (!stopped) setSnapshot(parsed);
      } catch {
        // The state file is written atomically; missing just means the monitor has not started yet.
      }
    };

    void tick();
    const timer = setInterval(() => void tick(), 1000);
    onCleanup(() => {
      stopped = true;
      clearInterval(timer);
    });
  });

  return snapshot;
}

function SagaSidebar(props: { root: string }) {
  const snapshot = useSnapshot(props.root);
  const current = snapshot();
  if (!current) return <text>SAGA · waiting for monitor…</text>;

  const ci = current.ci;
  const backendTests = ci.checks.backendTests;
  const frontendTests = ci.checks.frontendTests;
  const testChecks = [backendTests, frontendTests].filter((check): check is CheckResult => check != null);
  const testsLine =
    testChecks.length > 0
      ? `${testChecks.every((check) => check.status === "pass") ? "✓" : "✗"} tests ${testChecks.reduce(
          (total, check) => total + (check.passed ?? 0),
          0,
        )}/${testChecks.reduce((total, check) => total + (check.passed ?? 0) + (check.failed ?? 0), 0)}`
      : null;

  return (
    <box flexDirection="column">
      <text>SAGA</text>
      <text>────────────</text>
      <text>SERVICES</text>
      <text>{serviceLine("backend", current.services.backend)}</text>
      <text>{serviceLine("frontend", current.services.frontend)}</text>
      <text>{serviceLine("postgres", current.services.database)}</text>
      <text> </text>
      <text>CHECKS</text>
      <text>{checksHeader(ci)}</text>
      {ci.checks.lint ? <text>{`${checkMark(ci.checks.lint)} lint`}</text> : null}
      {ci.checks.types ? <text>{`${checkMark(ci.checks.types)} types`}</text> : null}
      {testsLine ? <text>{testsLine}</text> : null}
      <text> </text>
      <text>GIT</text>
      <text>{current.git.branch || "-"}</text>
      <text>{`+${current.git.added} -${current.git.removed}`}</text>
      {current.browser.status !== "unavailable" ? (
        <>
          <text> </text>
          <text>BROWSER</text>
          <text>{`${current.browser.status} console=${current.browser.consoleErrors ?? "-"} network=${
            current.browser.networkFailures ?? "-"
          }`}</text>
        </>
      ) : null}
    </box>
  );
}

function SagaPanel(props: { root: string; panel: SlotProps }) {
  const snapshot = useSnapshot(props.root);
  const current = snapshot();
  if (!current) return <text>waiting for monitor…</text>;

  const ci = current.ci;
  return (
    <box flexDirection="column">
      <text>{`SAGA DEV STATUS            ${formatAge(current.updatedAt)} ago`}</text>
      <text> </text>
      <text>Services</text>
      <text>{`  ${serviceDetail("backend", current.services.backend)}`}</text>
      <text>{`  ${serviceDetail("frontend", current.services.frontend)}`}</text>
      <text>{`  ${serviceDetail("postgres", current.services.database)}`}</text>
      <text> </text>
      <text>{`Local CI   ${
        ci.status === "not-run"
          ? "not run"
          : `${ci.scope ?? "-"} · ${formatAge(ci.finishedAt)} ago${ci.stale ? " · stale" : ""}`
      }`}</text>
      {Object.entries(ci.checks).map(([id, check]) => (
        <text>{`  ${id.padEnd(16)} ${checkLine(check)}`}</text>
      ))}
      <text> </text>
      <text>Last failure</text>
      {ci.lastFailure
        ? ci.lastFailure.summary.split("\n").map((line) => <text>{`  ${line}`}</text>)
        : <text>  none</text>}
      <text> </text>
      <text>Git</text>
      <text>{`  branch ${current.git.branch || "-"}`}</text>
      <text>{`  tree   ${current.git.dirty === 0 ? "clean" : `${current.git.dirty} modified`}`}</text>
      <text>{`  diff   +${current.git.added} -${current.git.removed}`}</text>
      <text> </text>
      <text>Browser</text>
      <text>{`  ${browserLine(current.browser)}`}</text>
      <text> </text>
      <text>State: .opencode/state/saga-dev.json</text>
    </box>
  );
}

function serviceLine(name: string, service: ServiceInfo): string {
  const latency = service.latencyMs == null ? "" : ` ${service.latencyMs}ms`;
  return `${dot(service.status)} ${name.padEnd(8)} :${service.port}${latency}`;
}

function serviceDetail(name: string, service: ServiceInfo): string {
  const latency = service.latencyMs == null ? "" : `${service.latencyMs}ms`;
  return `${name.padEnd(9)} ${service.status.toUpperCase().padEnd(4)} :${service.port}  ${latency}`.trimEnd();
}

function dot(status: ServiceStatus): string {
  if (status === "up") return "●";
  if (status === "down") return "○";
  return "·";
}

function checksHeader(ci: CiSnapshot): string {
  if (ci.status === "not-run") return "—";
  return `${ci.status === "pass" ? "✓" : "✗"} ${ci.scope ?? "-"} · ${formatAge(ci.finishedAt)}${
    ci.stale ? " · stale" : ""
  }`;
}

function checkMark(check: CheckResult): string {
  if (check.status === "pass") return "✓";
  if (check.status === "skipped") return "–";
  return "✗";
}

function checkLine(check: CheckResult): string {
  const parts = [check.status.toUpperCase()];
  if (check.durationMs != null) parts.push(formatDuration(check.durationMs));
  if (check.passed != null) parts.push(`${check.passed}/${check.passed + (check.failed ?? 0)}`);
  if (check.detail) parts.push(check.detail.slice(0, 80));
  return parts.join("  ");
}

function browserLine(browser: BrowserSnapshot): string {
  if (browser.status === "unavailable") {
    return `not run${browser.reason ? ` (${browser.reason})` : ""}`;
  }
  return `${browser.status} console=${browser.consoleErrors ?? "-"} network=${
    browser.networkFailures ?? "-"
  } ${browser.durationMs == null ? "" : formatDuration(browser.durationMs)}`.trim();
}

export default Plugin.define({
  id: "saga.dev.tui",
  setup(context: {
    location?: { directory: string };
    data: { location: { default(): { directory: string } | undefined } };
    ui: {
      slot(input: { append: string; render: (props: SlotProps) => unknown }): unknown;
      panel: { open(name: string): boolean };
    };
    keymap: { layer(factory: () => Record<string, unknown>): unknown };
  }) {
    const root = context.location?.directory ?? context.data.location.default()?.directory;
    if (!root) return;

    context.ui.slot({
      append: "sidebar.content",
      render: () => <SagaSidebar root={root} />,
    });

    context.ui.slot({
      append: "session.panel",
      render: (panel) => (panel.name === "saga.dev" ? <SagaPanel root={root} panel={panel} /> : null),
    });

    context.keymap.layer(() => ({
      mode: "global",
      commands: [
        {
          id: "saga.dev.panel",
          title: "SAGA: dev status",
          group: "SAGA",
          slash: { name: "saga" },
          palette: true,
          run: () => context.ui.panel.open("saga.dev"),
        },
      ],
    }));
  },
});
