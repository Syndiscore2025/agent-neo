import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const proxyTarget = env.VITE_DEV_PROXY_TARGET?.trim();

  return {
    plugins: [react()],
    server: proxyTarget
      ? {
          proxy: {
            '/api/backend': {
              target: proxyTarget,
              changeOrigin: true,
              secure: false,
              rewrite: (path) => path.replace(/^\/api\/backend/, ''),
            },
            '/api/neo': {
              target: proxyTarget,
              changeOrigin: true,
              secure: false,
              rewrite: (path) => path.replace(/^\/api\/neo/, ''),
            },
          },
        }
      : undefined,
  };
});
