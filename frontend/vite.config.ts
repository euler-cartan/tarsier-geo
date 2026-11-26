import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
  },
  server: {
    fs: { allow: [".."] },
  },
  test: {
    setupFiles: ["./scripts/require-data-home.mjs"],
    environment: "jsdom",
    globals: true,
    include: ["../tests/frontend/**/*.test.tsx"],
  },
});

