import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    // When served through the Cloudflare tunnel, allow its hostname and point the
    // HMR websocket at the public HTTPS origin; unset locally, so dev is unchanged.
    allowedHosts: process.env.VITE_PUBLIC_HOST ? [process.env.VITE_PUBLIC_HOST] : undefined,
    hmr: process.env.VITE_PUBLIC_HOST
      ? {protocol: 'wss', host: process.env.VITE_PUBLIC_HOST, clientPort: 443}
      : undefined,
    proxy: {
      '/api/': {
        target: 'http://api:8000',
        changeOrigin: true,
        rewrite: (path) => path.slice('/api'.length),
      },
    },
    // Docker Desktop bind mounts on Windows do not reliably forward native
    // filesystem events into Linux containers. Polling keeps Vite HMR working
    // without restarting the UI service after every source edit.
    watch: {
      usePolling: true,
      interval: 250,
    },
  },
  build: {
    assetsDir: 'assets',
    rollupOptions: {
      output: {
        assetFileNames: 'assets/[name]-[hash][extname]',
        chunkFileNames: 'assets/[name]-[hash].js',
        entryFileNames: 'assets/[name]-[hash].js',
      },
    },
  },
})
