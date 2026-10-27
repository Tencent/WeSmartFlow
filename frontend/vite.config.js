import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import { fileURLToPath, URL } from "node:url";

const frontendDir = fileURLToPath(new URL(".", import.meta.url));
const examplesDir = fileURLToPath(new URL("../examples", import.meta.url));

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
      "@explore-catalog": fileURLToPath(
        new URL("../examples/explore-catalog.json", import.meta.url),
      ),
    },
  },
  server: {
    // 开发服务器会把 /api 代理到本机后端；监听 0.0.0.0 等于把后端暴露给整个局域网。
    // 需要局域网/手机调试时：VITE_DEV_HOST=0.0.0.0 npm run dev
    host: process.env.VITE_DEV_HOST || "127.0.0.1",
    port: 5173,
    fs: {
      allow: [frontendDir, examplesDir],
    },
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      "/files": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
      // examples demo 的图（dev 模式下由后端 mount 静态目录提供）
      "/court-assets": {
        target: "http://localhost:8080",
        changeOrigin: true,
      },
    },
  },
});
