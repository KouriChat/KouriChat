<script setup lang="ts">
import { onMounted, onUnmounted, ref } from "vue";
import { api } from "../api";
import GButton from "./ui/GButton.vue";
import GInput from "./ui/GInput.vue";
import GOverline from "./ui/GOverline.vue";

const emit = defineEmits<{ ready: [] }>();
const initialized = ref(false);
const username = ref("");
const password = ref("");
const confirm = ref("");
const loading = ref(true);
const busy = ref(false);
const ready = ref(false);
const error = ref("");

async function submit() {
  error.value = "";
  if (!username.value.trim()) {
    error.value = "请输入管理员账号";
    return;
  }
  if (password.value.length < 12) {
    error.value = "密码至少需要 12 个字符";
    return;
  }
  if (!initialized.value && password.value !== confirm.value) {
    error.value = "两次密码不一致";
    return;
  }
  busy.value = true;
  try {
    if (initialized.value) await api.authLogin(username.value, password.value);
    else await api.authSetup(username.value, password.value);
    ready.value = true;
    emit("ready");
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

function onExpired() {
  ready.value = false;
  loading.value = false;
}

onMounted(async () => {
  window.addEventListener("kouri-auth-expired", onExpired);
  try {
    const status = await api.authStatus();
    initialized.value = status.initialized;
    if (status.authenticated) {
      ready.value = true;
      emit("ready");
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loading.value = false;
  }
});

onUnmounted(() => window.removeEventListener("kouri-auth-expired", onExpired));
</script>

<template>
  <slot v-if="!loading && ready" />

  <div v-else class="dot-grid flex min-h-screen items-center justify-center px-4">
    <p v-if="loading" class="text-[14px] text-ink-soft">加载中…</p>

    <div v-else class="w-full max-w-[420px] rounded-xl border border-line bg-surface p-8">
      <div class="flex items-center gap-2">
        <span
          class="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-[14px] font-bold text-white"
          >K</span
        >
        <span class="font-display text-[15px] font-bold tracking-tight text-ink"
          >KouriChat</span
        >
      </div>

      <GOverline class="mt-10">{{ initialized ? "管理员登录" : "首次初始化" }}</GOverline>
      <h1 class="mt-2 text-[28px] leading-tight">
        {{ initialized ? "欢迎回来" : "创建管理员账号" }}
      </h1>
      <p class="mt-2 text-[14px] text-ink-soft">
        {{
          initialized
            ? "请输入管理员凭据进入本地控制台。"
            : "首次使用请设置管理员账号和密码（至少 12 位）。"
        }}
      </p>

      <form class="mt-6 space-y-4" @submit.prevent="submit">
        <label class="block">
          <span class="mb-1.5 block text-[13px] font-medium text-ink">账号</span>
          <GInput v-model="username" autocomplete="username" placeholder="admin" />
        </label>
        <label class="block">
          <span class="mb-1.5 block text-[13px] font-medium text-ink">密码</span>
          <GInput
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="至少 12 个字符"
          />
        </label>
        <label v-if="!initialized" class="block">
          <span class="mb-1.5 block text-[13px] font-medium text-ink">确认密码</span>
          <GInput v-model="confirm" type="password" autocomplete="new-password" />
        </label>

        <p v-if="error" class="rounded-md bg-error/10 px-3 py-2 text-[13px] text-error">
          {{ error }}
        </p>

        <GButton type="submit" size="lg" block :loading="busy">
          {{ busy ? "处理中…" : initialized ? "登录" : "创建并登录" }}
        </GButton>
      </form>
    </div>
  </div>
</template>
