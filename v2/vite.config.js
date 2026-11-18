import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  base: './', // dist is loaded via file:// inside Qt, absolute /assets paths would 404
  server: { host: '127.0.0.1' },
});
