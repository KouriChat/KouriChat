import { createRouter, createWebHistory, type RouteRecordRaw } from "vue-router";

const routes: RouteRecordRaw[] = [
  {
    path: "/",
    name: "overview",
    component: () => import("./views/Overview.vue"),
    meta: { title: "总览" },
  },
  {
    path: "/accounts",
    name: "accounts",
    component: () => import("./views/Accounts.vue"),
    meta: { title: "账号" },
  },
  {
    path: "/chat",
    name: "chat",
    component: () => import("./views/ChatDebug.vue"),
    meta: { title: "聊天调试" },
  },
  {
    path: "/logs",
    name: "logs",
    component: () => import("./views/Logs.vue"),
    meta: { title: "日志" },
  },
  {
    path: "/settings",
    name: "settings",
    component: () => import("./views/Config.vue"),
    meta: { title: "设置" },
  },
  {
    path: "/onboarding",
    name: "onboarding",
    component: () => import("./views/Onboarding.vue"),
    meta: { title: "快速引导" },
  },
  { path: "/:pathMatch(.*)*", redirect: "/" },
];

export const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
});

router.afterEach((to) => {
  const title = typeof to.meta.title === "string" ? to.meta.title : "";
  document.title = title ? `${title} · KouriChat 控制台` : "KouriChat 控制台";
});
