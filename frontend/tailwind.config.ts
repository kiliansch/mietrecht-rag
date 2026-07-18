import type { Config } from "tailwindcss";
import forms from "@tailwindcss/forms";

// "Lexical Integrity" design system — tokens copied from
// docs/stitch_mietrecht_assistent_ui_design/lexical_integrity/DESIGN.md.
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: "#00236f",
        "primary-container": "#1e3a8a",
        "on-primary": "#ffffff",
        "on-primary-container": "#90a8ff",
        secondary: "#515f74",
        "secondary-container": "#d5e3fd",
        tertiary: "#272b2d",
        background: "#f8f9ff",
        surface: "#f8f9ff",
        "surface-container-lowest": "#ffffff",
        "surface-container-low": "#eff4ff",
        "surface-container": "#e5eeff",
        "surface-container-high": "#dce9ff",
        "surface-container-highest": "#d3e4fe",
        "surface-variant": "#d3e4fe",
        "on-surface": "#0b1c30",
        "on-surface-variant": "#444651",
        "inverse-surface": "#213145",
        "inverse-on-surface": "#eaf1ff",
        outline: "#757682",
        "outline-variant": "#c5c5d3",
        // Status colors mapped to German legal verdicts.
        success: "#16794a",
        "success-container": "#c6f0d6",
        "on-success-container": "#00391c",
        warning: "#8a6500",
        "warning-container": "#ffe28a",
        "on-warning-container": "#2a1e00",
        error: "#ba1a1a",
        "error-container": "#ffdad6",
        "on-error-container": "#93000a",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      borderRadius: {
        DEFAULT: "0.25rem",
        lg: "0.5rem",
        xl: "0.75rem",
        "2xl": "1rem",
        full: "9999px",
      },
      boxShadow: {
        // Level 1 (cards) and Level 2 (dropdowns/modals) ambient shadows.
        card: "0px 4px 12px rgba(30, 58, 138, 0.05)",
        elevated: "0px 8px 24px rgba(30, 58, 138, 0.12)",
      },
      maxWidth: {
        prose: "70ch",
      },
    },
  },
  plugins: [forms],
} satisfies Config;
