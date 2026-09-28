import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Builds src/bridge.jsx as one self-contained script (React included) that the
// legacy AngularJS page can load with a plain <script> tag.
export default defineConfig({
  plugins: [react()],
  define: { 'process.env.NODE_ENV': JSON.stringify('production') },
  build: {
    outDir: 'dist-bridge',
    emptyOutDir: true,
    lib: {
      entry: 'src/bridge.jsx',
      name: 'ReactBridgeBundle',
      formats: ['iife'],
      fileName: () => 'react-bridge.js',
    },
  },
});
