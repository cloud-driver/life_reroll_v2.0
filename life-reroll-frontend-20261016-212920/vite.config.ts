/// <reference types="vitest/config" />
import { fileURLToPath, URL } from 'node:url';
import { readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { gzipSync } from 'node:zlib';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';
const backend = process.env.LIFE_API_PROXY || 'http://127.0.0.1:8000';
let outDir = 'dist';

// Frontend-only handoff; /api requires a separate backend.
export default defineConfig({
  plugins: [
    react(),
    {
      name: 'precompress-static',
      configResolved(config) {
        outDir = resolve(config.root, config.build.outDir);
      },
      closeBundle() {
        const walk = (dir: string) => {
          for (const file of readdirSync(dir, { withFileTypes: true })) {
            const path = join(dir, file.name);
            if (file.isDirectory()) {
              walk(path);
              continue;
            }
            if (!/\.(js|css|html|json)$/.test(file.name) || file.name === 'config.js') continue;
            const bytes = readFileSync(path);
            if (bytes.length < 1024) continue;
            writeFileSync(path + '.gz', gzipSync(bytes, { level: 9 }));
          }
        };
        walk(outDir);
      },
    },
  ],
  resolve: { alias: { '@': fileURLToPath(new URL('.', import.meta.url)) } },
  build: {
    outDir: 'dist',
    rolldownOptions: {
      output: {
        // React changes far less often than game code; a separate chunk stays cached across deploys.
        codeSplitting: {
          groups: [{ name: 'react-vendor', test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/ }],
        },
      },
    },
  },
  test: { include: ['tests/unit/**/*.test.ts'], environment: 'node' },
  server: { host: '0.0.0.0', port: 5173, proxy: { '/api': { target: backend, changeOrigin: false } } },
  preview: { host: '127.0.0.1', port: 4173, proxy: { '/api': { target: backend, changeOrigin: false } } },
});
