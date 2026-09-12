<script setup lang="ts">
import { computed } from "vue";
import { RouterView, useRoute, useRouter } from "vue-router";
import AuthGate from "./components/AuthGate.vue";
import AppShell from "./components/layout/AppShell.vue";
import GToaster from "./components/ui/GToaster.vue";
import { api } from "./api";
import { useStatus } from "./composables/useStatus";

const route = useRoute();
const router = useRouter();
const { refresh } = useStatus();

/** Onboarding 走全屏无顶栏；其余页面进 AppShell。 */
const bare = computed(() => route.name === "onboarding");

/**
 * first_run 检查必须在认证完成后进行：
 * `/api/setup/status` 需要鉴权，登录前请求会 401；因此挂到 AuthGate 的 ready 事件。
 */
async function onAuthReady() {
  try {
    const s = await api.setupStatus();
    if (s.first_run && route.name !== "onboarding") router.replace("/onboarding");
  } catch {
    /* 后端不可用则按控制台渲染 */
  }
}
</script>

<template>
  <AuthGate @ready="onAuthReady">
    <RouterView v-if="bare" v-slot="{ Component }">
      <component :is="Component" @done="router.replace('/')" />
    </RouterView>
    <AppShell v-else>
      <RouterView v-slot="{ Component }">
        <component :is="Component" @changed="refresh" />
      </RouterView>
    </AppShell>
  </AuthGate>
  <GToaster />
</template>
