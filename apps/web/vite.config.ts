import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vitest/config';

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/graphql': {
        target:
          process.env.VITE_DEV_API_TARGET ??
          `http://localhost:${process.env.API_PORT ?? '8000'}`,
        changeOrigin: true,
      },
    },
  },
  preview: {
    host: '127.0.0.1',
    port: 4173,
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes('/node_modules/@apollo/') ||
            id.includes('/node_modules/graphql/')
          ) {
            return 'graphql';
          }

          if (
            id.includes('/node_modules/react-hook-form/') ||
            id.includes('/node_modules/@hookform/') ||
            id.includes('/node_modules/zod/')
          ) {
            return 'forms';
          }

          if (
            id.includes('/node_modules/react/') ||
            id.includes('/node_modules/react-dom/') ||
            id.includes('/node_modules/scheduler/')
          ) {
            return 'react';
          }

          return undefined;
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    css: true,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
    },
  },
});
