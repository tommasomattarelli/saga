import { Plugin } from "@opencode/plugin";
import * as Schema from "effect/Schema";
import { activate, snapshot } from "./src/workflow.ts";
import { runCli } from "./src/cli.ts";

export default Plugin.define({
  id: "saga-adr-workflow",
  async setup(ctx) {
    await ctx.tool.transform((editor) => {
      editor.add({
        name: "workflow",
        description: "Operate the bounded ADR implementation ledger: activate/status, bind blocks, writer claims, checks, review verdicts, and commit readiness.",
        input: Schema.Struct({
          operation: Schema.String,
          payload: Schema.optional(Schema.String),
        }),
        execute: async ({ operation, payload }, toolContext) => {
          const session = await ctx.session.get({ sessionID: toolContext.sessionID });
          const cwd = session.location.directory;
          if (operation === "review") {
            const data = JSON.parse(payload ?? "{}") as Record<string, unknown>;
            data.reviewerSession = toolContext.sessionID;
            return { content: JSON.stringify(runCli([operation, JSON.stringify(data)], cwd, toolContext.sessionID)) };
          }
          return { content: JSON.stringify(runCli([operation, payload ?? "{}"], cwd, toolContext.sessionID)) };
        },
      });
    });

    await ctx.tool.hook("execute.after", async (event) => {
      const input = event.input;
      if (
        event.status !== "completed" ||
        event.tool !== "skill" ||
        typeof input !== "object" ||
        input === null ||
        !("id" in input) ||
        input.id !== "adr-implement"
      ) return;
      try {
        const session = await ctx.session.get({ sessionID: event.sessionID });
        const cwd = session.location.directory;
        activate(cwd, event.sessionID);
        const text = snapshot(cwd);
        const content = event.result.content;
        event.result = {
          ...event.result,
          content: typeof content === "string"
            ? `${content}\n\n${text}`
            : [...(content ?? []), { type: "text", text }],
        };
      } catch {
        return;
      }
    });
  },
});
