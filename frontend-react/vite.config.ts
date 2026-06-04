import path from "node:path";
import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const fontAssetPattern = /\.(eot|otf|ttf|woff2?)$/i;
const imageAssetPattern = /\.(avif|gif|ico|jpe?g|png|svg|webp)$/i;

function normalizeModuleId(id: string) {
  return id.split(path.sep).join(path.posix.sep);
}

function manualChunks(id: string) {
  const moduleId = normalizeModuleId(id);

  if (!moduleId.includes("node_modules/")) {
    return undefined;
  }

  if (
    moduleId.includes("monaco-editor/") ||
    moduleId.includes("monaco-yaml/")
  ) {
    return "vendor/monaco";
  }

  if (moduleId.includes("leaflet/")) {
    return "vendor/map";
  }

  return "vendor/vendor";
}

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        assetFileNames: (assetInfo) => {
          const name = assetInfo.name ?? "";

          if (fontAssetPattern.test(name)) {
            return "assets/fonts/[name]-[hash][extname]";
          }

          if (imageAssetPattern.test(name)) {
            return "assets/media/[name]-[hash][extname]";
          }

          if (name.endsWith(".css")) {
            return "assets/styles/[name]-[hash][extname]";
          }

          return "assets/media/[name]-[hash][extname]";
        },
        chunkFileNames: (chunkInfo) => {
          if (chunkInfo.name.startsWith("vendor/")) {
            return "assets/[name]-[hash].js";
          }

          if (chunkInfo.name.includes("worker")) {
            return "assets/workers/[name]-[hash].js";
          }

          return "assets/app/[name]-[hash].js";
        },
        entryFileNames: "assets/app/[name]-[hash].js",
        manualChunks,
      },
    },
  },
  worker: {
    rollupOptions: {
      output: {
        chunkFileNames: "assets/workers/[name]-[hash].js",
        entryFileNames: "assets/workers/[name]-[hash].js",
      },
    },
  },
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
