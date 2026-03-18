import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  // When Flask runs on another port (e.g. 5001), set in shell or frontend/.env.local:
  //   FLASK_PROXY_TARGET=http://localhost:5001
  const flaskTarget =
    env.FLASK_PROXY_TARGET || process.env.FLASK_PROXY_TARGET || 'http://localhost:5000';

  return {
  plugins: [
    react(),
    {
      name: 'serve-scenarios-json',
      configureServer(server) {
        // Serve scenarios.json from project root so dev works without Flask.
        server.middlewares.use('/scenarios.json', (_req, res) => {
          const filePath = path.resolve(__dirname, '../scenarios.json');
          if (!fs.existsSync(filePath)) {
            res.statusCode = 404;
            res.end('scenarios.json not found');
            return;
          }
          res.setHeader('Content-Type', 'application/json');
          res.end(fs.readFileSync(filePath));
        });
      },
    },
  ],
  server: {
    proxy: {
      '/api': flaskTarget,
      '/admin': flaskTarget,
    },
  },
  build: {
    // Emit build output to ../../dist so Flask can serve it from the project root
    outDir: '../dist',
    emptyOutDir: true,
  },
  };
});
