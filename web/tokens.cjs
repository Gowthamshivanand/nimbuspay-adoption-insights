/* ONE place for the visual language. Swap these values to apply Gowtham's Figma hi-fi look.
   Light consulting + Apple-clean: neutral greys, one accent, no gradients/glows.
   Values from the Figma hi-fi kit (figma/hifi-kit/tokens.json): navy #0B2E59, orange fill #E8751A, orange text #C2410C, grey #4B5563, Inter.
   Contrast on white (WCAG AA >= 4.5:1): ink 16.8, navy 13.6, muted 7.6, accent text 5.2, verified 7.6, critical 6.5.
   accentFill (#E8751A) is ~2.9:1 on white, so it is used ONLY for non-text marks (bars, dots, focus ring), never under text. */
module.exports = {
  colors: {
    canvas: "#FFFFFF",      // page background
    surface: "#FAFAFA",     // sidebar, chat well, table headers
    line: "#E5E5E5",        // hairlines
    lineStrong: "#D4D4D4",  // input borders
    ink: "#1D1D1F",         // primary text
    muted: "#4B5563",       // secondary text (grey)
    accent: "#C2410C",      // orange TEXT accent (metric IDs, selected labels)
    accentFill: "#E8751A",  // orange FILL (bars, dots, borders) - not for text
    navy: "#0B2E59",        // primary actions and selected states
    accentSoft: "#FFF4ED",  // accent tint for selected states
    verified: "#0F5E63",    // ONLY for "verified" figures (M17, verified evidence)
    critical: "#B91C1C",    // ONLY for critical risk / refusals / mismatches
  },
  font: {
    sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "Helvetica Neue", "Arial", "sans-serif"],
    mono: ["SFMono-Regular", "Menlo", "Consolas", "monospace"],
  },
  radius: { tile: "12px", control: "8px" },
  motion: { fast: "150ms", base: "180ms" },
};
