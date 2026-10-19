import { readFileSync } from "node:fs";
import path from "node:path";

import { Plugin } from "@opencode/plugin/tui";
import { Show, createSignal, onCleanup, onMount } from "solid-js";

type Member = { name: string; status: string };

type TeamState = {
  team: string | null;
  members: Member[];
  tasks: { pending: number; done: number };
};

type TuiContext = {
  location?: { directory: string };
  data?: { location?: { default?: () => { directory: string } | undefined } };
  ui: { slot(input: { append: string; render: (props: unknown) => unknown }): unknown };
};

/** Dashboard port from the project ensemble.json, defaulting to 4747. */
function dashboardPort(root: string | undefined): number {
  let port = 4747;
  try {
    if (!root) return port;
    const raw = readFileSync(path.join(root, ".opencode", "ensemble.json"), "utf8");
    const parsed = JSON.parse(raw) as { dashboardPort?: number };
    if (typeof parsed.dashboardPort === "number" && parsed.dashboardPort > 0) port = parsed.dashboardPort;
  } catch {
    // Missing or invalid config — keep the default port.
  }
  return port;
}

/** Live team state from the ensemble dashboard HTTP API. */
async function fetchTeam(url: string, root: string | undefined): Promise<TeamState> {
  const res = await fetch(`${url}/api/state`, { signal: AbortSignal.timeout(3000) });
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const state = (await res.json()) as {
    projects?: Array<{
      path?: string;
      teams?: Array<{
        name: string;
        status: string;
        members?: Array<{ name: string; status: string; executionStatus?: string }>;
        tasks?: Array<{ status: string }>;
      }>;
    }>;
  };
  const projects = state.projects ?? [];
  const project =
    projects.find((p) => p.path === root) ??
    projects.find((p) => (p.teams ?? []).some((t) => t.status === "active")) ??
    projects[0];
  const team = project?.teams?.find((t) => t.status === "active");
  if (!team) return { team: null, members: [], tasks: { pending: 0, done: 0 } };
  const members = (team.members ?? []).map((m) => ({
    name: m.name,
    status: m.executionStatus === "running" || m.status === "busy" ? "busy" : "ready",
  }));
  const tasks = team.tasks ?? [];
  const done = tasks.filter((t) => t.status === "completed").length;
  return { team: team.name, members, tasks: { pending: tasks.length - done, done } };
}

function EnsemblePanel(props: { url: string; root: string | undefined }) {
  const [state, setState] = createSignal<TeamState | null>(null);
  const [diag, setDiag] = createSignal("loading");

  const load = async (): Promise<void> => {
    try {
      const data = await fetchTeam(props.url, props.root);
      setState(data);
      setDiag(data.team ? "live" : "no team");
    } catch (err) {
      setDiag(`err · ${err instanceof Error ? err.message : String(err)}`);
    }
  };

  onMount(() => {
    void load();
    const timer = setInterval(() => void load(), 3000);
    onCleanup(() => clearInterval(timer));
  });

  return (
    <box flexDirection="column">
      <text>────────────────────</text>
      <text>ENSEMBLE → {props.url}</text>
      <Show when={state()?.team} fallback={<text>  no team · {diag()}</text>}>
        <box flexDirection="column">
          <text>  {state()?.team}</text>
          {(state()?.members ?? []).map((member) => (
            <text>
              {member.status === "busy" ? "●" : "○"} {member.name} ({member.status})
            </text>
          ))}
          <text>
            tasks: {(state()?.tasks.pending ?? 0)} open / {(state()?.tasks.done ?? 0)} done
          </text>
        </box>
      </Show>
      <text>────────────────────</text>
    </box>
  );
}

export default Plugin.define({
  id: "ensemble.panel",
  setup(context: TuiContext) {
    const root =
      context.location?.directory ??
      context.data?.location?.default?.()?.directory ??
      process.cwd();
    const url = `http://localhost:${dashboardPort(root)}`;

    context.ui.slot({
      append: "sidebar.content",
      render: () => <EnsemblePanel url={url} root={root} />,
    });
  },
});
