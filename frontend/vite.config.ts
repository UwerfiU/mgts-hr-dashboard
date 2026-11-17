import { defineConfig, loadEnv } from 'vite';

export default defineConfig(({ mode }) => {
  const target = loadEnv(mode, process.cwd(), 'API_PROXY_TARGET').API_PROXY_TARGET;

  return {
    server: target ? { proxy: { '/api': { target, changeOrigin: true } } } : undefined,
    build: {
      rolldownOptions: {
        output: {
          codeSplitting: {
            groups: [{ name: 'charts', test: /node_modules[/\\](?:recharts|d3-[^/\\]+|victory-vendor)[/\\]/ }],
          },
        },
      },
    },
  };
});
