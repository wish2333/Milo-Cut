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
  },
  test: {
    environment: "happy-dom",
    include: ["src/**/*.{test,spec}.ts"],
  },
});
