import type { Config } from "tailwindcss";

// Colors are stored as RGB channel triples in CSS variables (see globals.css)
// so Tailwind's opacity modifiers (e.g. bg-accent/10) work.
const withVar = (name: string) => `rgb(var(${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: withVar("--bg"),
        surface: withVar("--surface"),
        "surface-2": withVar("--surface-2"),
        border: withVar("--border"),
        fg: withVar("--fg"),
        muted: withVar("--muted"),
        accent: withVar("--accent"),
        "accent-fg": withVar("--accent-fg"),
        danger: withVar("--danger"),
        ok: withVar("--ok"),
      },
      fontFamily: {
        sans: [
          "var(--font-sans)",
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
    },
  },
  plugins: [],
};

export default config;
