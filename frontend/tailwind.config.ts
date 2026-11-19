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
        // Themed (see src/lib/themes.ts). "on-primary" is the text colour that's readable ON
        // the accent: white for most themes, dark for bright accents like gold or cyan.
        primary: {
          DEFAULT: "rgb(var(--primary) / <alpha-value>)",
          hover:   "rgb(var(--primary-hover) / <alpha-value>)",
          light:   "rgb(var(--primary-light) / <alpha-value>)",
          muted:   "rgb(var(--primary-muted) / <alpha-value>)",
        },
        "on-primary": "rgb(var(--on-primary) / <alpha-value>)",
        success: "#22C55E",
        error:   "#EF4444",
        warning: "#EAB308",
        info:    "#3B82F6",
      },
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      // Themed radii: near-square for the neo-brutalist themes, soft for Glass, very round for
      // Fluffy (values in src/lib/themes.ts). "full" stays a circle/pill everywhere.
      borderRadius: {
        none:    "0px",
        DEFAULT: "var(--radius)",
        sm:      "var(--radius-sm)",
        md:      "var(--radius-md)",
        lg:      "var(--radius-md)",
        xl:      "var(--radius-lg)",
        "2xl":   "var(--radius-lg)",
        "3xl":   "var(--radius-lg)",
        "4xl":   "var(--radius-lg)",
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
      // Themed shadows: hard offsets for neo-brutalist themes, soft diffuse ones for Glass
      // and Fluffy. Class names kept as-is so every component follows the theme.
      boxShadow: {
        brutal:           "var(--shadow)",
        "brutal-sm":      "var(--shadow-sm)",
        "brutal-lg":      "var(--shadow-lg)",
        "brutal-primary":    "var(--shadow-primary)",
        "brutal-primary-lg": "var(--shadow-primary-lg)",
        "brutal-error":      "3px 3px 0 #EF4444",
        card:                "var(--shadow)",
        glow:             "0 0 20px rgb(var(--primary) / 0.25)",
        "glow-sm":        "0 0 10px rgb(var(--primary) / 0.18)",
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
