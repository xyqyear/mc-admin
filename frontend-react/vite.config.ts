import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": path.resolve(import.meta.dirname, "./src"),
    },
  },
  server: {
    port: 3000,
    proxy: {
      "/api": {
        target: "http://localhost:5678",
        changeOrigin: true,
        secure: false,
        ws: true,
        configure: (proxy) => {
          proxy.on("proxyReq", (proxyReq, req) => {
            console.log(
              `[proxyReq] ${req.method} ${req.url} -> ${proxyReq.path}`,
            );
          });
          proxy.on("proxyRes", (proxyRes, req) => {
            console.log(
              `[proxyRes] ${req.method} ${req.url} <- ${proxyRes.statusCode}: ${proxyRes.read()}`,
            );
          });
          proxy.on("error", (err, req) => {
            console.error(
              `[proxyError] ${req.method} ${req.url} - ${err.message}`,
            );
          });
        },
      },
    },
  },
});
