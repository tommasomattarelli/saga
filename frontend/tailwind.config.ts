import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        parchment: {
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
        blood: {
          50: "#fef2f2",
          500: "#8b1a1a",
          700: "#5c1010",
          900: "#3d0808",
        },
        gold: {
          400: "#d4a843",
          500: "#c49a2e",
          600: "#a88225",
        },
      },
      fontFamily: {
        serif: ["Merriweather", "Georgia", "serif"],
        display: ["Cinzel", "serif"],
      },
    },
  },
  plugins: [],
} satisfies Config;
