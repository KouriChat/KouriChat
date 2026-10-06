<script setup lang="ts">
import { onMounted, reactive, ref, watch } from "vue";
import { api, type SettingsFields } from "../api";
import { toast } from "../lib/toast";
import type { ChipTone } from "../components/ui/types";
import GButton from "../components/ui/GButton.vue";
import GCard from "../components/ui/GCard.vue";
import GChip from "../components/ui/GChip.vue";
import GInput from "../components/ui/GInput.vue";
import GSelect from "../components/ui/GSelect.vue";
import GSwitch from "../components/ui/GSwitch.vue";

const fields = reactive<SettingsFields>({
  core: { log_level: "INFO" },
  openclaw: {
    gateway_url: "http://127.0.0.1:8765",
    access_token: "",
    data_dir: "./data",
    autologin: true,
    poll_interval: 2.0,
  },
  llm: {
    base_url: "https://api.openai.com/v1",
    api_key: "",
    model: "gpt-4o-mini",
    data_dir: "./data",
  },
  webui: { host: "127.0.0.1", port: 8080 },
  persona: { personas_dir: "./personas", enable: "" },
  echo: { enabled: true },
});

const loading = ref(true);
const status = ref<"idle" | "saving" | "saved" | "error">("idle");
const error = ref("");
let saveTimer: number | undefined;
let saving = false;
let ready = false;

async function load() {
  loading.value = true;
  try {
    const res = await api.settingsGet();
    Object.assign(fields, res.fields);
    ready = true;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
    status.value = "error";
  } finally {
    loading.value = false;
  }
}

async function doSave() {
  if (saving) return;
  saving = true;
  status.value = "saving";
  error.value = "";
  try {
    await api.settingsSave(JSON.parse(JSON.stringify(fields)));
    status.value = "saved";
  } catch (err) {
    status.value = "error";
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    saving = false;
  }
}

watch(
  fields,
  () => {
    if (!ready) return;
    status.value = "idle";
    if (saveTimer !== undefined) window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(doSave, 800);
  },
  { deep: true },
);

const testing = ref(false);
const testResult = ref<{ ok: boolean; text: string } | null>(null);

async function testLlm() {
  testing.value = true;
  testResult.value = null;
  try {
    const r = await api.llmTest(JSON.parse(JSON.stringify(fields.llm)));
    testResult.value = r.ok
      ? { ok: true, text: `✅ 连通正常（${r.model ?? ""}）：${r.reply ?? ""}` }
      : { ok: false, text: `❌ ${r.error ?? "未知错误"}` };
    if (r.ok) toast.success("LLM 连通正常");
    else toast.error(r.error ?? "LLM 连通失败");
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    testResult.value = { ok: false, text: `❌ ${message}` };
    toast.error(message);
  } finally {
    testing.value = false;
  }
}

const reloading = ref(false);
const reloadResult = ref<{ ok: boolean; text: string } | null>(null);

async function reloadLlm() {
  reloading.value = true;
  reloadResult.value = null;
  try {
    await api.settingsSave(JSON.parse(JSON.stringify(fields)));
    const r = await api.llmReload();
    reloadResult.value = r.ok
      ? { ok: true, text: `✅ ${r.note ?? "LLM 组件已热重载"}` }
      : { ok: false, text: `❌ ${r.error ?? "热重载失败"}` };
    if (r.ok) toast.success(r.note ?? "LLM 组件已热重载");
    else toast.error(r.error ?? "热重载失败");
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    reloadResult.value = { ok: false, text: `❌ ${message}` };
    toast.error(message);
  } finally {
    reloading.value = false;
  }
}

const statusTone: Record<typeof status.value, ChipTone> = {
  idle: "neutral",
  saving: "warning",
  saved: "success",
  error: "error",
};
const statusText: Record<typeof status.value, string> = {
  idle: "修改即自动保存",
  saving: "保存中…",
  saved: "已保存",
  error: "保存失败",
};

onMounted(load);
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center gap-3">
      <h1 class="text-[32px] leading-tight">设置</h1>
      <GChip :tone="statusTone[status]">{{ statusText[status] }}</GChip>
      <p
        v-if="error"
        class="rounded-md bg-error/10 px-3 py-1.5 text-[12px] text-error"
      >
        {{ error }}
      </p>
    </div>

    <p v-if="loading" class="text-[14px] text-ink-soft">加载中…</p>
    <template v-else>
      <!-- 核心 -->
      <GCard>
        <h3 class="text-[20px]">核心</h3>
        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">日志级别</span>
            <GSelect v-model="fields.core.log_level">
              <option value="DEBUG">DEBUG</option>
              <option value="INFO">INFO</option>
              <option value="WARNING">WARNING</option>
              <option value="ERROR">ERROR</option>
            </GSelect>
          </label>
        </div>
      </GCard>

      <!-- OpenClaw 网关 -->
      <GCard>
        <h3 class="text-[20px]">OpenClaw 网关</h3>
        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">网关地址</span>
            <GInput v-model="fields.openclaw.gateway_url" placeholder="http://127.0.0.1:8765" />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">Access Token</span>
            <GInput
              v-model="fields.openclaw.access_token"
              type="password"
              placeholder="网关 config.json 的 accessToken"
            />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">数据目录</span>
            <GInput v-model="fields.openclaw.data_dir" />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">
              轮询间隔（秒，兼容保留）
            </span>
            <GInput
              v-model.number="fields.openclaw.poll_interval"
              type="number"
              placeholder="2.0"
            />
          </label>
          <div
            class="flex items-center justify-between gap-4 rounded-lg border border-line px-4 py-3 sm:col-span-2"
          >
            <span class="text-[14px] text-ink">无本地账号时自动发起扫码登录</span>
            <GSwitch v-model="fields.openclaw.autologin" />
          </div>
        </div>
      </GCard>

      <!-- LLM -->
      <GCard>
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h3 class="text-[20px]">LLM（elixir / OpenAI 兼容）</h3>
          <div class="flex items-center gap-2">
            <GButton variant="secondary" size="sm" :loading="testing" @click="testLlm">
              测试连通
            </GButton>
            <GButton size="sm" :loading="reloading" @click="reloadLlm">
              保存并热重载
            </GButton>
          </div>
        </div>
        <p
          v-if="testResult"
          class="mt-3 rounded-md px-3 py-2 text-[12px]"
          :class="testResult.ok ? 'bg-success/10 text-success' : 'bg-error/10 text-error'"
        >
          {{ testResult.text }}
        </p>
        <p
          v-if="reloadResult"
          class="mt-3 rounded-md px-3 py-2 text-[12px]"
          :class="reloadResult.ok ? 'bg-success/10 text-success' : 'bg-error/10 text-error'"
        >
          {{ reloadResult.text }}
        </p>
        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">Base URL</span>
            <GInput v-model="fields.llm.base_url" />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">API Key</span>
            <GInput v-model="fields.llm.api_key" type="password" placeholder="sk-..." />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">模型</span>
            <GInput v-model="fields.llm.model" />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">数据目录</span>
            <GInput v-model="fields.llm.data_dir" />
          </label>
        </div>
      </GCard>

      <!-- 默认任务 -->
      <GCard>
        <h3 class="text-[20px]">默认任务</h3>
        <div
          class="mt-4 flex items-center justify-between gap-4 rounded-lg border border-line px-4 py-3"
        >
          <span class="text-[14px] text-ink">
            echo 回显（收到 /echo 后原样回显下一条消息；开启时这两条消息不进命令/大模型）
          </span>
          <GSwitch v-model="fields.echo.enabled" />
        </div>
      </GCard>

      <!-- WebUI / 人设 -->
      <GCard>
        <h3 class="text-[20px]">WebUI / 人设</h3>
        <div class="mt-4 grid gap-4 sm:grid-cols-2">
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">WebUI 监听地址</span>
            <GInput v-model="fields.webui.host" />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">WebUI 端口</span>
            <GInput v-model.number="fields.webui.port" type="number" />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">人设目录</span>
            <GInput v-model="fields.persona.personas_dir" />
          </label>
          <label class="block">
            <span class="mb-1.5 block text-[13px] font-medium text-ink">启用人设</span>
            <GInput v-model="fields.persona.enable" placeholder="可留空取第一个" />
          </label>
        </div>
      </GCard>

      <p class="text-[12px] text-ink-soft">
        更改会自动保存到 kourichat.toml（TOML 校验后原子写入），部分设置需重启生效。
      </p>
    </template>
  </div>
</template>
