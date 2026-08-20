/// <reference types="vitest/config" />

import tailwindcss from "@tailwindcss/vite"
import react from "@vitejs/plugin-react"
import { defineConfig } from "vite"

// Port the local API listens on. `make dev-ui` passes DEV_API_PORT through
// from the repo-root Makefile, which uses the same value for `make dev-api`.
const apiPort = process.env.DEV_API_PORT || "8742"

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 3000,
    proxy: {
      "/api/v1": {
        target: `http://localhost:${apiPort}`,
      },
    },
  },
  test: {
    environment: "happy-dom",
    globals: true,
    setupFiles: ["./src/test-setup.ts"],
  },
})
