import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  base: "/static/",
  plugins: [react()],
  build: {
    outDir: "../static",
    emptyOutDir: true,
    sourcemap: false,
  },
  server: {
    proxy: {
      "/runs": "http://127.0.0.1:8000",
    },
  },
});
