import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: '0.0.0.0',
  },
  preview: {
    port: 4173,
    host: '0.0.0.0',
  },
  build: {
    sourcemap: false,
    // recharts alone is ~550 kB minified; it is the floor, not a regression.
    chunkSizeWarningLimit: 600,
    // Charts and the map are the two heavy dependencies; splitting them keeps
    // the entry chunk small and lets them cache independently of app code.
    rollupOptions: {
      output: {
        manualChunks: {
          react: ['react', 'react-dom'],
          charts: ['recharts'],
          map: ['leaflet', 'react-leaflet'],
        },
      },
    },
  },
});
