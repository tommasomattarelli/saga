import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { Plugin, usePlugin } from "@opencode/plugin/tui";
import { Show, createSignal, onCleanup, onMount } from "solid-js";

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
  toggleFullscreen?: () => void;
  width?: number;
  presentation?: string;
  focused?: boolean;
};

type TuiContext = {
  keymap: { layer(factory: () => Record<string, unknown>): unknown };
};

function pluginRoot(): string | null {
  try {
    const here = path.dirname(fileURLToPath(import.meta.url));
    return path.resolve(here, "..", "..", "..");
  } catch {
    return null;
  }
}

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

  return (
    <Show when={snapshot()} keyed fallback={<text>SAGA · waiting for monitor…</text>}>
      {(s) => {
        const ci = s.ci;
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
            <text>{serviceLine("backend", s.services.backend)}</text>
            <text>{serviceLine("frontend", s.services.frontend)}</text>
            <text>{serviceLine("postgres", s.services.database)}</text>
            <text> </text>
            <text>CHECKS</text>
            <text>{checksHeader(ci)}</text>
            {ci.checks.lint ? <text>{`${checkMark(ci.checks.lint)} lint`}</text> : null}
            {ci.checks.types ? <text>{`${checkMark(ci.checks.types)} types`}</text> : null}
            {testsLine ? <text>{testsLine}</text> : null}
            <text> </text>
            <text>GIT</text>
            <text>{s.git.branch || "-"}</text>
            <text>{`+${s.git.added} -${s.git.removed}`}</text>
            {s.browser.status !== "unavailable" ? (
              <>
                <text> </text>
                <text>BROWSER</text>
                <text>{`${s.browser.status} console=${s.browser.consoleErrors ?? "-"} network=${
                  s.browser.networkFailures ?? "-"
                }`}</text>
              </>
            ) : null}
          </box>
        );
      }}
    </Show>
  );
}

function SagaPanel(props: { root: string; panel: SlotProps }) {
  const plugin = usePlugin() as unknown as TuiContext;
  plugin.keymap.layer(() => ({
    commands: [
      { id: "saga.dev.close", bind: "escape", run: () => props.panel.close?.() },
      { id: "saga.dev.close-q", bind: "q", run: () => props.panel.close?.() },
      { id: "saga.dev.fullscreen", bind: "f", run: () => props.panel.toggleFullscreen?.() },
    ],
  }));

  const snapshot = useSnapshot(props.root);

  return (
    <Show when={snapshot()} keyed fallback={<text>waiting for monitor…</text>}>
      {(s) => {
        const ci = s.ci;
        return (
          <box flexDirection="column">
            <text>{`SAGA DEV STATUS            ${formatAge(s.updatedAt)} ago`}</text>
            <text> </text>
            <text>Services</text>
            <text>{`  ${serviceDetail("backend", s.services.backend)}`}</text>
            <text>{`  ${serviceDetail("frontend", s.services.frontend)}`}</text>
            <text>{`  ${serviceDetail("postgres", s.services.database)}`}</text>
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
            <text>{`  branch ${s.git.branch || "-"}`}</text>
            <text>{`  tree   ${s.git.dirty === 0 ? "clean" : `${s.git.dirty} modified`}`}</text>
            <text>{`  diff   +${s.git.added} -${s.git.removed}`}</text>
            <text> </text>
            <text>Browser</text>
            <text>{`  ${browserLine(s.browser)}`}</text>
            <text> </text>
            <text>State: .opencode/state/saga-dev.json</text>
          </box>
        );
      }}
    </Show>
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
      panel: {
        open(name: string, options?: { presentation?: string }): boolean;
        close(): void;
        current(): unknown;
      };
    };
    keymap: { layer(factory: () => Record<string, unknown>): unknown };
  }) {
    const root =
      pluginRoot() ??
      context.location?.directory ??
      context.data.location.default()?.directory ??
      process.cwd();

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
          run: () => {
            const current = context.ui.panel.current();
            const name =
              typeof current === "string" ? current : (current as { name?: string } | undefined)?.name;
            if (name === "saga.dev") context.ui.panel.close();
            else context.ui.panel.open("saga.dev");
          },
        },
      ],
    }));
  },
});
