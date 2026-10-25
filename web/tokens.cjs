/* Tailwind bridge. Colour values live in src/tokens.css so light/dark stay in one place. */
module.exports = {
  colors: {
    canvas: "var(--np-canvas)",
    surface: "var(--np-surface)",
    elevated: "var(--np-elevated)",
    line: "var(--np-line)",
    lineStrong: "var(--np-line-strong)",
    ink: "var(--np-ink)",
    muted: "var(--np-muted)",
    accent: "var(--np-accent)",
    accentFill: "var(--np-accent-fill)",
    navy: "var(--np-navy)",
    accentSoft: "var(--np-accent-soft)",
    verified: "var(--np-verified)",
    critical: "var(--np-critical)",
    slate: "var(--np-slate)",
  },
  font: {
    sans: ["-apple-system", "BlinkMacSystemFont", "SF Pro Display", "SF Pro Text", "Inter", "sans-serif"],
    mono: ["SFMono-Regular", "ui-monospace", "Menlo", "Consolas", "monospace"],
  },
  radius: { tile: "14px", control: "10px" },
  motion: { fast: "200ms", base: "280ms" },
};
