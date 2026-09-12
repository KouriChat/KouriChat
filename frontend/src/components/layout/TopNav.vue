<script setup lang="ts">
import { computed, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import {
  LayoutGrid,
  LogOut,
  Menu,
  MessageSquare,
  RotateCcw,
  ScrollText,
  Settings,
  Users,
} from "@lucide/vue";
import { useAuth } from "../../composables/useAuth";
import { useStatus } from "../../composables/useStatus";
import GButton from "../ui/GButton.vue";
import GChip from "../ui/GChip.vue";
import GDrawer from "../ui/GDrawer.vue";
import GDropdownMenu from "../ui/GDropdownMenu.vue";

const route = useRoute();
const router = useRouter();
const { username, logout } = useAuth();
const { status } = useStatus();
const drawerOpen = ref(false);

const nav = [
  { key: "overview", label: "总览", to: "/", icon: LayoutGrid },
  { key: "accounts", label: "账号", to: "/accounts", icon: Users },
  { key: "chat", label: "聊天调试", to: "/chat", icon: MessageSquare },
  { key: "logs", label: "日志", to: "/logs", icon: ScrollText },
  { key: "settings", label: "设置", to: "/settings", icon: Settings },
] as const;

const onlineCount = computed(
  () => status.value?.accounts.filter((a) => a.status === "online").length ?? 0,
);
const accountCount = computed(() => status.value?.accounts.length ?? 0);
const initial = computed(() => (username || "管").slice(0, 1).toUpperCase());

const menuItems = [
  { key: "onboarding", label: "重新走快速引导", icon: RotateCcw },
  { key: "logout", label: "退出登录", icon: LogOut, danger: true },
];

function onMenu(key: string) {
  if (key === "onboarding") router.push("/onboarding");
  else if (key === "logout") void logout();
}

function go(to: string) {
  drawerOpen.value = false;
  router.push(to);
}

const isActive = (to: string) => route.path === to;
</script>

<template>
  <header class="sticky top-0 z-30 border-b border-line bg-surface/80 backdrop-blur-md">
    <div
      class="mx-auto flex h-14 w-full max-w-[1280px] items-center gap-3 px-4 sm:px-6 lg:px-8"
    >
      <RouterLink to="/" class="flex shrink-0 items-center gap-2">
        <span
          class="flex h-7 w-7 items-center justify-center rounded-md bg-primary text-[13px] font-bold text-white"
          >K</span
        >
        <span class="font-display text-[15px] font-bold tracking-tight text-ink"
          >KouriChat</span
        >
      </RouterLink>

      <nav class="ml-5 hidden items-center gap-1 md:flex">
        <RouterLink
          v-for="n in nav"
          :key="n.key"
          :to="n.to"
          class="flex items-center gap-2 rounded-md px-3 py-1.5 text-[14px] font-medium transition-colors"
          :class="
            isActive(n.to)
              ? 'bg-primary/10 text-primary'
              : 'text-ink-soft hover:bg-ink/[0.04] hover:text-ink'
          "
        >
          <component :is="n.icon" class="h-4 w-4" aria-hidden="true" />
          {{ n.label }}
        </RouterLink>
      </nav>

      <div class="ml-auto flex items-center gap-2">
        <div class="hidden items-center gap-2 sm:flex">
          <GChip v-if="accountCount" tone="neutral">
            {{ onlineCount }}/{{ accountCount }} 在线
          </GChip>
          <GChip :tone="status?.connected ? 'success' : 'error'" dot>
            {{ status?.connected ? "已连接" : "未连接" }}
          </GChip>
        </div>

        <GDropdownMenu
          :items="menuItems"
          :label="username || '管理员'"
          @select="onMenu"
        >
          <template #trigger>
            <button
              class="focus-ring flex h-8 w-8 items-center justify-center rounded-full bg-primary text-[13px] font-bold text-white"
              :aria-label="`账号菜单：${username || '管理员'}`"
            >
              {{ initial }}
            </button>
          </template>
        </GDropdownMenu>

        <GButton
          variant="ghost"
          size="sm"
          class="md:hidden"
          aria-label="打开导航"
          @click="drawerOpen = true"
        >
          <Menu class="h-5 w-5" />
        </GButton>
      </div>
    </div>

    <GDrawer :open="drawerOpen" title="导航" @update:open="drawerOpen = $event">
      <template #trigger><span class="hidden" /></template>
      <template #close>
        <GButton variant="ghost" size="sm" aria-label="关闭导航">关闭</GButton>
      </template>
      <nav class="flex flex-col gap-1">
        <button
          v-for="n in nav"
          :key="n.key"
          class="flex items-center gap-2.5 rounded-md px-3 py-2.5 text-[15px] font-medium transition-colors"
          :class="
            isActive(n.to)
              ? 'bg-primary/10 text-primary'
              : 'text-ink-soft hover:bg-ink/[0.04] hover:text-ink'
          "
          @click="go(n.to)"
        >
          <component :is="n.icon" class="h-4 w-4" aria-hidden="true" />
          {{ n.label }}
        </button>
      </nav>
    </GDrawer>
  </header>
</template>
