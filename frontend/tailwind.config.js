/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        canvas: '#0B1220',
        surface: '#131B2E',
        raised: '#1B2436',
        line: '#223047',
        edge: '#2A3855',
        ink: '#E8EDF5',
        muted: '#8291AA',
        accent: '#F2A65A',
        good: '#009865',
        satisfactory: '#A3C853',
        moderate: '#FFD500',
        poor: '#FF7E00',
        verypoor: '#FF0000',
        severe: '#7E0023',
      },
      fontFamily: {
        display: ['"Space Grotesk"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      boxShadow: {
        panel: '0 18px 44px rgba(3, 7, 18, 0.45)',
      },
      keyframes: {
        'fade-up': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'fade-up': 'fade-up 220ms ease-out',
      },
    },
  },
  plugins: [],
};
