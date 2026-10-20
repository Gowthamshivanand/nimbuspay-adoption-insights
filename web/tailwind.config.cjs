const t = require("./tokens.cjs");
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: t.colors,
      fontFamily: { sans: t.font.sans, mono: t.font.mono },
      borderRadius: t.radius,
      transitionDuration: { fast: t.motion.fast, base: t.motion.base },
    },
  },
  plugins: [],
};
