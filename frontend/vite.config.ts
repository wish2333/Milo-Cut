/// <reference types="vitest" />
import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import { resolve } from "path";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  resolve: {
    alias: { "@": resolve(__dirname, "src") },
  },
  server: {
    host: "127.0.0.1",
    port: 5200,
    strictPort: true,
  },
  build: {
    outDir: "../frontend_dist",
    emptyOutDir: true,
    // Enable tree-shaking with rollup options
    rollupOptions: {
      output: {
        // Split vendor chunks for better caching
        manualChunks: {
          vue: ["vue"],
        },
      },
    },
    // Report compressed size
    reportCompressedSize: true,
    // Warn on large chunks (>500 KB)
    chunkSizeWarningLimit: 500,
  },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.{test,spec}.ts"],
    // Perf-gate files (projectPatch.perf / undoScale.perf / useRowLayout.perf)
    // assert wall-clock p50/p95 -- parallel file workers add CPU contention
    // noise that flips them. The suite is seconds-scale, so serial files are
    // the cheap, deterministic option.
    fileParallelism: false,
  },
});
