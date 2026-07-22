/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#0f172a',
        mist: '#e2e8f0',
        haze: '#f8fafc',
        signal: '#14b8a6',
        amber: '#f59e0b',
        alert: '#ef4444',
      },
      boxShadow: {
        glow: '0 24px 60px rgba(15, 23, 42, 0.18)',
      },
    },
  },
  plugins: [],
};
