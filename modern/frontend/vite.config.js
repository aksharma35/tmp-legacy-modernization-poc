import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The React app talks to the upgraded Python 3 API through the dev-server proxy,
// so the same relative URLs (/api/...) work exactly like in the legacy app.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: { '/api': 'http://localhost:5002' },
  },
});
