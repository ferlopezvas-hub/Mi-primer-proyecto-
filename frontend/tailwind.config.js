/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        bg: "var(--bg)", surface: "var(--surface)", "surface-2": "var(--surface-2)", line: "var(--line)",
        ink: "var(--ink)", "ink-2": "var(--ink-2)", muted: "var(--muted)",
        brand: "var(--brand)", "brand-ink": "var(--brand-ink)",
        s1: "var(--series-1)", s2: "var(--series-2)", s3: "var(--series-3)",
        good: "var(--good)", warn: "var(--warning)", bad: "var(--critical)", live: "var(--live)",
      },
      fontFamily: { sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"] },
    },
  },
  plugins: [],
};
