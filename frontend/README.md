# KouriChat 控制台前端（Vue 3 + Vite + TS + Tailwind CSS v4）

消费 `kourichat.webui` 插件的 JSON API；构建产物 `dist/` 由 webui 插件静态托管
（默认 `static_dir = ./frontend/dist`，打包时由 `build.ps1` 填充到
`kourichat/webui/static/`）。

## 设计系统

界面参照根目录 `genesis-DESIGN.md` 重做（T21–T28）：浅色 editorial 风格、
#FAFAFA 页面 / #FFFFFF 卡片、indigo(#6366F1) 仅用于交互、克制阴影、
General Sans + DM Sans + JetBrains Mono + Noto Sans SC（CDN）。

- Design token：`src/style.css` 的 Tailwind v4 `@theme`（颜色/字体/阴影/字号）。
- UI 原语：`src/components/ui/`（GButton / GInput / GTextarea / GSelect /
  GCard / GChip / GStatusChip / GList / GListRow / GOverline / GSkeleton /
  GEmptyState / GAlertDialog / GDropdownMenu / GTooltip / GDrawer / GSwitch /
  GToaster）。
- 图标：`@lucide/vue` 为主；品牌/兜底图标用 `unplugin-icons`
  （`~icons/simple-icons/wechat`、`~icons/ph/...`），编译期内联、离线可用。
- 通知：`vue-sonner`，统一从 `src/lib/toast.ts` 触发。

## 路由

`vue-router` history 模式（webui 静态服务已支持 SPA fallback）：

| 路径 | 页面 |
| --- | --- |
| `/` | 总览 |
| `/accounts` | 账号 |
| `/chat` | 聊天调试 |
| `/logs` | 日志 |
| `/settings` | 设置 |
| `/onboarding` | 首次引导（全屏、无顶栏） |

未知路径重定向 `/`；`document.title` 随路由更新。

## 目录

- `src/api.ts`        —— JSON API 类型化封装 + JWT 用户名解析（`authUsername`）
- `src/router.ts`     —— 路由表（视图级懒加载）
- `src/App.vue`       —— AuthGate + Onboarding/AppShell 分流
- `src/components/layout/` —— TopNav / AppShell（顶栏 + 响应式抽屉）
- `src/components/ui/`     —— Genesis UI 原语
- `src/composables/`  —— `useStatus`（共享 3s 轮询）/ `useAuth`
- `src/views/*.vue`   —— 各视图

## 开发

```bash
npm install
npm run dev        # http://localhost:5173，/api 已 proxy 到 http://127.0.0.1:8080
npm run typecheck  # vue-tsc --noEmit
npm run build      # 产出 dist/
```

先启动 kourichat（含 webui 插件，默认端口 8080），再启动 dev server 联调。
