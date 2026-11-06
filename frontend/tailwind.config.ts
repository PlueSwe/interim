import type { Config } from "tailwindcss";

// Ljust tema, medvetet. Ingen dark-variant och inga dark:-klasser i koden.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#15191e",
        muted: "#5b6672",
        line: "#e3e8ee",
        surface: "#f7f9fb",
        accent: {
          DEFAULT: "#13506b",
          hover: "#0e3e53",
          soft: "#e7f0f4",
        },
        pass: { DEFAULT: "#166534", soft: "#e8f5ec" },
        review: { DEFAULT: "#92400e", soft: "#fdf1e3" },
        excluded: { DEFAULT: "#991b1b", soft: "#fdeceb" },
      },
      fontFamily: {
        sans: ['"Inter var"', "Inter", "system-ui", "Segoe UI", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(21,25,30,0.04), 0 1px 10px rgba(21,25,30,0.03)",
      },
    },
  },
  plugins: [],
};

export default config;
