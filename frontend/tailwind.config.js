/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        wax: { 50: '#fbf8f3', 100: '#f4ede1', 200: '#e8d9c0', 500: '#b08a57', 600: '#94703f', 700: '#765832', 900: '#3b2c19' },
      },
    },
  },
  plugins: [],
}
