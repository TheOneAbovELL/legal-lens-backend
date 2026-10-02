/// <reference types="vitest/config" />
import { fileURLToPath, URL } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

// Dev server proxies API calls to the backend so no request URL needs editing
// (VITE_API_URL stays empty in development; set it for a remote backend).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const backend = env.VITE_DEV_PROXY_TARGET || "http://127.0.0.1:8000";
  return {
    plugins: [react()],
    resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
    server: {
      port: Number(env.VITE_PORT || 5173),
      strictPort: false,
      proxy: {
        "/api": { target: backend, changeOrigin: true },
        "/health": { target: backend, changeOrigin: true },
        "/ready": { target: backend, changeOrigin: true },
      },
    },
    build: {
      sourcemap: false,
      target: "es2022",
      rollupOptions: {
        output: {
          manualChunks: {
            react: ["react", "react-dom", "react-router-dom"],
            query: ["@tanstack/react-query"],
            markdown: ["react-markdown", "remark-gfm"],
          },
        },
      },
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./tests/setup.ts"],
      include: ["tests/**/*.test.{ts,tsx}", "src/**/*.test.{ts,tsx}"],
      exclude: ["e2e/**", "node_modules/**"],
      css: false,
    },
  };
});
