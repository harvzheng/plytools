import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "node:path";
import { plytoolsViewer } from "./server/plugin";

export default defineConfig({
  plugins: [react(), plytoolsViewer()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  server: {
    port: 5173,
  },
});
