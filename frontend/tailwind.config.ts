import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          primary: "var(--ink-primary)",
          secondary: "var(--ink-secondary)",
          faded: "var(--ink-faded)",
        },
        parchment: {
          base: "var(--parchment-base)",
          aged: "var(--parchment-aged)",
          shadow: "var(--parchment-shadow)",
          // legacy scale — kept for backwards compat during transition
          50: "#faf8f2",
          100: "#f3efe3",
          200: "#e6ddc5",
          300: "#d4c59e",
          400: "#c2ab78",
          500: "#b4965c",
          600: "#a67f4e",
          700: "#8b6541",
          800: "#72533a",
          900: "#5e4532",
        },
        gold: {
          DEFAULT: "var(--gold)",
          bright: "var(--gold-bright)",
          deep: "var(--gold-deep)",
          // legacy scale
          400: "#d4a843",
          500: "#c49a2e",
          600: "#a88225",
        },
        blood: {
          DEFAULT: "var(--blood)",
          dark: "var(--blood-dark)",
          50: "#fef2f2",
          500: "#8b1a1a",
          700: "#5c1010",
          900: "#3d0808",
        },
        arcane: {
          DEFAULT: "var(--arcane)",
          deep: "var(--arcane-deep)",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "serif"],
        body: ["var(--font-body)", "Georgia", "serif"],
        // legacy aliases
        serif: ["var(--font-body)", "Georgia", "serif"],
      },
      transitionDuration: {
        "page-turn": "600ms",
        "ink-draw": "1200ms",
        "mood-crossfade": "1800ms",
      },
      transitionTimingFunction: {
        "page-turn": "cubic-bezier(0.77, 0, 0.175, 1)",
        "ink-draw": "cubic-bezier(0.22, 1, 0.36, 1)",
      },
      letterSpacing: {
        grimoire: "0.15em",
        "grimoire-wide": "0.2em",
        "grimoire-xl": "0.3em",
      },
    },
  },
  plugins: [],
} satisfies Config;
