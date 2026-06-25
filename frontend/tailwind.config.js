/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // ZeroRespond dark theme palette
        surface: {
          900: "#0f172a",   // page background
          800: "#1e293b",   // card/panel background
          700: "#334155",   // elevated surfaces
          600: "#475569",   // borders
        },
        severity: {
          critical: "#ef4444",   // red
          high:     "#f97316",   // orange
          medium:   "#eab308",   // yellow
          low:      "#22c55e",   // green
        }
      }
    },
  },
  plugins: [],
}