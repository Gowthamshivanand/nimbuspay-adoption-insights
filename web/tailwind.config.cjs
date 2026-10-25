const t = require("./tokens.cjs");
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: t.colors,
      fontFamily: { sans: t.font.sans, mono: t.font.mono },
      borderRadius: t.radius,
      transitionDuration: { fast: t.motion.fast, base: t.motion.base },
      transitionTimingFunction: { spring: "cubic-bezier(0.32, 0.72, 0, 1)" },
      fontSize: {
        "2xs": ["12px", "16px"],
        xs: ["13px", "18px"],
        sm: ["15px", "22px"],
        base: ["17px", "24px"],
        lg: ["22px", "28px"],
        xl: ["28px", "34px"],
        "2xl": ["40px", "46px"],
      },
    },
  },
  plugins: [],
};
