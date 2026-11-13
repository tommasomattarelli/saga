import { installHooks, uninstallHooks } from "./hooks.ts";
import { activate, bindPlan, claimWriter, completeWriter, pause, prepare, registerReview, runCheck, snapshot } from "./workflow.ts";
import { readState } from "./store.ts";
import { resolve } from "node:path";
import { pathToFileURL } from "node:url";

const help = `SAGA_WORKFLOW_SESSION=<session-id> saga-workflow <operation> [JSON]

Operations:
  activate
  status
  bind          {"adr":"docs/adr/NNNN.md","branch":"...","base":"...","blocks":[{"id":"...","paths":["..."],"checks":["..."]}]}
  claim | done  {"block":"..."}
  check         {"block":"...","command":"registered exact command"}
  review        {"block":"...","correctness":"pass","slop":"pass"}
  prepare
  pause | resume
  install-hooks | uninstall-hooks`;

export function runCli(args: string[], cwd: string, session: string): unknown {
  const [operation, raw = "{}"] = args;
  if (!operation || operation === "--help" || operation === "help") return help;
  const input = JSON.parse(raw) as Record<string, unknown>;
  const string = (key: string): string => {
    const value = input[key];
    if (typeof value !== "string") throw new Error(`Expected string field: ${key}`);
    return value;
  };
  switch (operation) {
    case "activate": return activate(cwd, session);
    case "status": return { state: readState(cwd), snapshot: snapshot(cwd) };
    case "bind": return bindPlan(cwd, session, input as unknown as Parameters<typeof bindPlan>[2]);
    case "claim": return claimWriter(cwd, string("block"), session);
    case "done": return completeWriter(cwd, string("block"), session);
    case "check": return runCheck(cwd, session, string("block"), string("command"));
    case "review": return registerReview(cwd, {
      block: string("block"),
      reviewerSession: session,
      correctness: string("correctness") as "pass" | "fail",
      slop: string("slop") as "pass" | "fail",
    });
    case "prepare": return prepare(cwd);
    case "gate": return readState(cwd) ? prepare(cwd) : { ready: true, inactive: true };
    case "pause": return pause(cwd, session, true);
    case "resume": return pause(cwd, session, false);
    case "install-hooks": return installHooks(cwd);
    case "uninstall-hooks": return uninstallHooks(cwd);
    default: throw new Error(`Unknown operation: ${operation}\n${help}`);
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  try {
    const result = runCli(process.argv.slice(2), process.cwd(), process.env.SAGA_WORKFLOW_SESSION ?? "");
    if (result !== undefined) console.log(typeof result === "string" ? result : JSON.stringify(result, null, 2));
    if (process.argv[2] === "gate") {
      const gate = result as ReturnType<typeof prepare>;
      if (!gate.ready) {
        console.error(`ADR workflow commit gate: ${gate.reason}`);
        process.exitCode = 1;
      }
    }
  } catch (error) {
    console.error(`ADR workflow: ${error instanceof Error ? error.message : "operation failed"}`);
    process.exitCode = 1;
  }
}
