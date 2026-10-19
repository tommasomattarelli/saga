# Ensemble panel plugin (OpenCode V2)

Project-local sidebar widget for `@hueyexe/opencode-ensemble`. It shows the
live team, its members and the task counts, plus a link to the ensemble
dashboard.

Read-only: it reads the dashboard's `/api/state` over local HTTP. No LLM
calls, no npm dependencies.

## What it does

- A TUI plugin (`tui.tsx`) polls `http://localhost:<port>/api/state` every 3
  seconds and renders a `sidebar.content` widget:

  ```
  ────────────────────
  ENSEMBLE → http://localhost:4747
    panel-check
    ● worker (busy)
    tasks: 1 open / 0 done
  ────────────────────
  ```

  `●` marks a member that is working, `○` an idle one. When no team is
  active the widget says so, and it reports the error when the dashboard
  cannot be reached.
- The port comes from `.opencode/ensemble.json` (`dashboardPort`, default
  `4747`).
- `index.ts` is an empty server entrypoint: the panel lives entirely in the
  TUI.

## Why a local plugin

The companion shipped by `@hueyexe/opencode-ensemble` resolves its own
`solid-js` copy, so its signals never reach the host renderer and the widget
stays frozen on its initial state ("no active team"). A local plugin resolves
the host's instance, and the widget then updates live.

The npm companion is disabled in `~/.config/opencode/opencode.json` with the
`-ensemble.tui` directive, so only one ensemble widget is drawn.

## Notes

- The ensemble plugin must be running: it owns the dashboard server that this
  widget reads.
- The widget never executes commands and never mutates team state.
- To disable the panel, remove `.opencode/plugins/ensemble-panel/`.
