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
          // neutral dark ramp (50 lightest → 900 darkest), slight cool bias
          50: "#e7e9ee",
          100: "#dcdfe6",
          200: "#c2c7d0",
          300: "#a2a8b3",
          400: "#7f8693",
          500: "#5f6572",
          600: "#444a55",
          700: "#2f353e",
          800: "#1a1e24",
          900: "#0f1216",
        },
        accent: {
          DEFAULT: "var(--accent)",
          bright: "var(--accent-bright)",
        },
        gold: {
          DEFAULT: "var(--gold)",
          bright: "var(--gold-bright)",
          deep: "var(--gold-deep)",
          400: "#a9cec2",
          500: "#8fb8ac",
          600: "#6e9a8d",
        },
        blood: {
          DEFAULT: "var(--blood)",
          dark: "var(--blood-dark)",
          50: "#f8e9e6",
          500: "#d3705f",
          700: "#a4483a",
          900: "#6d2b22",
        },
        line: {
          DEFAULT: "var(--line)",
          strong: "var(--line-strong)",
        },
        arcane: {
          DEFAULT: "var(--arcane)",
          deep: "var(--arcane-deep)",
        },
      },
      fontFamily: {
        display: ["var(--font-display)", "ui-sans-serif", "system-ui", "sans-serif"],
        body: ["var(--font-body)", "Georgia", "serif"],
        // legacy alias
        serif: ["var(--font-body)", "Georgia", "serif"],
      },
      transitionDuration: {
        "page-turn": "220ms",
        "ink-draw": "500ms",
        "mood-crossfade": "1000ms",
      },
      transitionTimingFunction: {
        "page-turn": "cubic-bezier(0.4, 0, 0.2, 1)",
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
