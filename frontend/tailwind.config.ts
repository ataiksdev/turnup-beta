import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Backgrounds
        bg: {
          DEFAULT: "#09090B",   // near-black
          surface: "#111116",
          card: "#18181B",
          elevated: "#27272A",
          overlay: "#2E2E35",
        },
        border: {
          DEFAULT: "#2A2A35",
          subtle: "#1E1E26",
          strong: "#3F3F50",
        },
        // Brand
        primary: {
          DEFAULT: "#F97316",   // orange-500 — energetic
          hover: "#EA580C",
          light: "#FED7AA",
          muted: "#431407",
        },
        // Text
        text: {
          DEFAULT: "#FAFAFA",
          secondary: "#A1A1AA",
          muted: "#71717A",
          disabled: "#52525B",
        },
        // Semantic
        success: "#22C55E",
        error:   "#EF4444",
        warning: "#EAB308",
        info:    "#3B82F6",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      borderRadius: {
        "2xl": "1rem",
        "3xl": "1.5rem",
        "4xl": "2rem",
      },
      animation: {
        "fade-in":  "fadeIn 0.3s ease-out",
        "slide-up": "slideUp 0.4s cubic-bezier(0.16,1,0.3,1)",
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
      },
      keyframes: {
        fadeIn:  { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp: { from: { transform: "translateY(16px)", opacity: "0" },
                   to:   { transform: "translateY(0)",    opacity: "1" } },
      },
      boxShadow: {
        card:    "0 4px 24px rgba(0,0,0,0.4)",
        glow:    "0 0 40px rgba(249,115,22,0.15)",
        "glow-sm":"0 0 20px rgba(249,115,22,0.10)",
      },
      backgroundImage: {
        "gradient-radial":   "radial-gradient(var(--tw-gradient-stops))",
        "hero-overlay":      "linear-gradient(to top, rgba(9,9,11,0.95) 0%, rgba(9,9,11,0.3) 60%, transparent 100%)",
        "card-overlay":      "linear-gradient(to top, rgba(9,9,11,0.9) 0%, transparent 60%)",
      },
    },
  },
  plugins: [animate],
};

export default config;
