import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";
import Icons from "unplugin-icons/vite";

export default defineConfig({
  plugins: [
    vue(),
    tailwindcss(),
    // 品牌/兜底图标编译期内联为 Vue 组件（离线可用，见 T21 Q4-C / Q6）
    Icons({ compiler: "vue3", scale: 1 }),
  ],
  server: {
    proxy: {
      // 开发期：前端 dev server 把 /api 转发到 kourichat webui 插件
      "/api": "http://127.0.0.1:8080",
    },
  },
  build: {
    outDir: "dist",
    rollupOptions: {
      output: {
        manualChunks: {
          d3: ["d3"],
          reka: ["reka-ui"],
        },
      },
    },
  },
});
