import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        // Use IPv4 loopback explicitly to avoid localhost/IPv6 resolution
        // mismatches that can surface as ECONNREFUSED in Vite proxy logs.
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
      },
    },
  },
});
