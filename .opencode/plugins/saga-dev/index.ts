import { Plugin } from "@opencode/plugin";

import { startMonitor } from "./probe";
import { registerTools, type PluginContext } from "./tools";

export default Plugin.define({
  id: "saga.dev",
  async setup(ctx: { location: { directory: string }; tool: PluginContext["tool"] }) {
    const root = ctx.location.directory;
    const stop = startMonitor(root);
    await registerTools(ctx, root);
    return stop;
  },
});
