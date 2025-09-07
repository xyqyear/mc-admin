import react from "@vitejs/plugin-react";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
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
