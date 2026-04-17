import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

// Colors use CSS custom properties with space-separated RGB channels so that
// Tailwind's opacity modifiers (bg-bg/80, text-text/60, etc.) keep working.
const config: Config = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: {
          DEFAULT:  "rgb(var(--bg) / <alpha-value>)",
          surface:  "rgb(var(--bg-surface) / <alpha-value>)",
          card:     "rgb(var(--bg-card) / <alpha-value>)",
          elevated: "rgb(var(--bg-elevated) / <alpha-value>)",
          overlay:  "rgb(var(--bg-overlay) / <alpha-value>)",
        },
        border: {
          DEFAULT: "rgb(var(--border) / <alpha-value>)",
          subtle:  "rgb(var(--border-subtle) / <alpha-value>)",
          strong:  "rgb(var(--border-strong) / <alpha-value>)",
        },
        text: {
          DEFAULT:   "rgb(var(--text) / <alpha-value>)",
          secondary: "rgb(var(--text-secondary) / <alpha-value>)",
          muted:     "rgb(var(--text-muted) / <alpha-value>)",
          disabled:  "rgb(var(--text-disabled) / <alpha-value>)",
        },
        primary: {
          DEFAULT: "#F97316",
          hover:   "#EA580C",
          light:   "#FED7AA",
          muted:   "rgb(var(--primary-muted) / <alpha-value>)",
        },
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
        "fade-in":    "fadeIn 0.3s ease-out",
        "slide-up":   "slideUp 0.4s cubic-bezier(0.16,1,0.3,1)",
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "shimmer":    "shimmer 1.6s linear infinite",
      },
      keyframes: {
        fadeIn:  { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp: { from: { transform: "translateY(16px)", opacity: "0" },
                   to:   { transform: "translateY(0)", opacity: "1" } },
        shimmer: { from: { backgroundPosition: "-200% 0" },
                   to:   { backgroundPosition: "200% 0" } },
      },
      boxShadow: {
        card:     "0 4px 24px rgba(0,0,0,0.4)",
        glow:     "0 0 40px rgba(249,115,22,0.15)",
        "glow-sm":"0 0 20px rgba(249,115,22,0.10)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "hero-overlay":    "linear-gradient(to top, rgba(9,9,11,0.95) 0%, rgba(9,9,11,0.3) 60%, transparent 100%)",
        "card-overlay":    "linear-gradient(to top, rgba(9,9,11,0.9) 0%, transparent 60%)",
      },
    },
  },
  plugins: [animate],
};

export default config;
