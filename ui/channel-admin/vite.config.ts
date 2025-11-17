import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5174,
    host: "0.0.0.0", // Listen on all interfaces (IPv4 and IPv6)
    open: true,
    proxy: {
      "/api": {
        target: process.env.VITE_API_BASE || "http://localhost:8000",
        changeOrigin: true,
        timeout: 10000,
        proxyTimeout: 10000
      }
    }
  }
});

