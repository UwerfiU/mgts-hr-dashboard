import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, process.cwd(), 'API_PROXY_TARGET').API_PROXY_TARGET;

  return {
    server: target ? { proxy: { '/api': { target, changeOrigin: true } } } : undefined,
    build: {
      rolldownOptions: {
        onwarn(warning, warn) {
          // This is a client-only SPA; dependencies' RSC directives have no role here.
          if (warning.code === 'MODULE_LEVEL_DIRECTIVE' && warning.message.includes('use client')) return;
          warn(warning);
        },
        output: {
          codeSplitting: {
            groups: [{ name: 'charts', test: /node_modules[/\\](?:recharts|d3-[^/\\]+|victory-vendor)[/\\]/ }],
          },
        },
      },
    },
  };
});
