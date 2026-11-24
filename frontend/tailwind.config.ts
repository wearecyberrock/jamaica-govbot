import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ja: {
          green: "#1a472a",
          greenDark: "#13331e",
          greenLight: "#eef7f2",
          gold: "#d4a234",
          goldBright: "#ffd700",
          navy: "#0b3c68",
          sunset: "#f28c18",
          red: "#ce1126",
        },
      },
      fontFamily: {
        sans: ["Plus Jakarta Sans", "Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
