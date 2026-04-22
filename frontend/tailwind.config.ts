import type { Config } from "tailwindcss";
import animate from "tailwindcss-animate";

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
          DEFAULT: "#A855F7",
          hover:   "#9333EA",
          light:   "#EDE9FE",
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
      // Neo-brutalist: minimal border radii everywhere; full kept for circles
      borderRadius: {
        none:    "0px",
        DEFAULT: "1px",
        sm:      "1px",
        md:      "2px",
        lg:      "2px",
        xl:      "2px",
        "2xl":   "2px",
        "3xl":   "2px",
        "4xl":   "2px",
        full:    "9999px",
      },
      animation: {
        "fade-in":    "fadeIn 0.2s ease-out",
        "slide-up":   "slideUp 0.25s cubic-bezier(0.16,1,0.3,1)",
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "shimmer":    "shimmer 1.6s linear infinite",
      },
      keyframes: {
        fadeIn:  { from: { opacity: "0" }, to: { opacity: "1" } },
        slideUp: { from: { transform: "translateY(10px)", opacity: "0" },
                   to:   { transform: "translateY(0)", opacity: "1" } },
        shimmer: { from: { backgroundPosition: "-200% 0" },
                   to:   { backgroundPosition: "200% 0" } },
      },
      // Hard-offset shadows with CSS custom property for automatic theme switching
      boxShadow: {
        brutal:           "3px 3px 0 rgb(var(--shadow-color))",
        "brutal-sm":      "2px 2px 0 rgb(var(--shadow-color))",
        "brutal-lg":      "5px 5px 0 rgb(var(--shadow-color))",
        "brutal-primary":    "3px 3px 0 #A855F7",
        "brutal-primary-lg": "5px 5px 0 #A855F7",
        "brutal-error":      "3px 3px 0 #EF4444",
        card:                "3px 3px 0 rgb(var(--shadow-color))",
        glow:             "0 0 20px rgba(168,85,247,0.25)",
        "glow-sm":        "0 0 10px rgba(168,85,247,0.18)",
      },
      backgroundImage: {
        "gradient-radial": "radial-gradient(var(--tw-gradient-stops))",
        "hero-overlay":    "linear-gradient(to top, rgba(0,0,0,0.92) 0%, rgba(0,0,0,0.4) 55%, transparent 100%)",
        "card-overlay":    "linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 55%)",
      },
    },
  },
  plugins: [animate],
};

export default config;
