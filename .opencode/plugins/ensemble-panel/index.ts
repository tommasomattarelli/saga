import { Plugin } from "@opencode/plugin";

export default Plugin.define({
  id: "ensemble.panel",
  setup() {
    // The panel is a terminal companion: it lives entirely in the TUI.
    return () => {};
  },
});
