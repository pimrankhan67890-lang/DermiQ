/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#0b1220"
      },
      boxShadow: {
        glow: "0 20px 60px rgba(59,130,246,0.18)"
      }
    },
  },
  plugins: [],
};
