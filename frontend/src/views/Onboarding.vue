<script setup lang="ts">
import { onMounted, reactive, ref } from "vue";
import { api, type LoginState, type SettingsFields } from "../api";
import QrCode from "../components/QrCode.vue";
import GButton from "../components/ui/GButton.vue";
import GCard from "../components/ui/GCard.vue";
import GInput from "../components/ui/GInput.vue";
import GOverline from "../components/ui/GOverline.vue";

const emit = defineEmits<{ done: [] }>();

const step = ref(1);
const busy = ref(false);
const error = ref("");
const notice = ref("");
const loginState = ref<LoginState | null>(null);

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

onMounted(async () => {
  try {
    const res = await api.settingsGet();
    Object.assign(fields, res.fields);
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
});

async function saveSettings() {
  busy.value = true;
  error.value = "";
  try {
    await api.settingsSave(JSON.parse(JSON.stringify(fields)));
    notice.value = "设置已保存";
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

async function next() {
  if (step.value === 1) {
    error.value = "";
    if (!fields.llm.api_key) {
      error.value = "请填写 LLM API Key（可稍后在设置页修改）";
      return;
    }
    await saveSettings();
    step.value = 2;
  } else if (step.value === 2) {
    await saveSettings();
    step.value = 3;
  }
}

async function startLogin() {
  busy.value = true;
  error.value = "";
  await saveSettings();
  if (error.value) {
    busy.value = false;
    return;
  }
  try {
    loginState.value = await api.login();
    pollLogin();
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    busy.value = false;
  }
}

async function pollLogin() {
  let tick = 0;
  const t = window.setInterval(async () => {
    tick += 1;
    try {
      const st = await api.status();
      loginState.value = st.login;
      if (st.login?.status === "success" || st.login?.status === "failed") {
        window.clearInterval(t);
      } else if (tick > 60) {
        window.clearInterval(t);
      }
    } catch {
      /* keep polling */
    }
  }, 1500);
}

async function finish() {
  await saveSettings();
  try {
    await api.llmReload();
  } catch {
    /* 热重载失败不阻断进入控制台 */
  }
  emit("done");
}

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
  } catch (err) {
    testResult.value = {
      ok: false,
      text: `❌ ${err instanceof Error ? err.message : String(err)}`,
    };
  } finally {
    testing.value = false;
  }
}
</script>

<template>
  <div class="dot-grid min-h-screen w-full">
    <div class="mx-auto max-w-[720px] px-4 py-12">
      <div class="text-center">
        <span
          class="mx-auto flex h-11 w-11 items-center justify-center rounded-xl bg-primary text-[18px] font-bold text-white"
          >K</span
        >
        <h1 class="mt-5 text-[32px] leading-tight">欢迎使用 KouriChat</h1>
        <p class="mt-2 text-[14px] text-ink-soft">
          首次使用，跟着三步完成最小配置：设置模型 API → 连接网关并登录 → 完成。
        </p>
      </div>

      <div class="mt-8 flex items-center gap-2">
        <div
          v-for="i in 3"
          :key="i"
          class="h-1.5 flex-1 rounded-full transition-colors"
          :class="step >= i ? 'bg-primary' : 'bg-line'"
        />
      </div>

      <GCard class="mt-6">
        <!-- 步骤 1：LLM API -->
        <template v-if="step === 1">
          <GOverline>步骤 1 / 3</GOverline>
          <h2 class="mt-2 text-[24px]">设置模型 API</h2>
          <p class="mt-1 text-[13px] text-ink-soft">
            填写 LLM（OpenAI 兼容）的接入信息，用于角色扮演对话。
          </p>
          <div class="mt-5 space-y-4">
            <label class="block">
              <span class="mb-1.5 block text-[13px] font-medium text-ink">Base URL</span>
              <GInput v-model="fields.llm.base_url" />
            </label>
            <label class="block">
              <span class="mb-1.5 block text-[13px] font-medium text-ink"
                >API Key <span class="text-error">*</span></span
              >
              <GInput v-model="fields.llm.api_key" type="password" placeholder="sk-..." />
            </label>
            <label class="block">
              <span class="mb-1.5 block text-[13px] font-medium text-ink">模型</span>
              <GInput v-model="fields.llm.model" />
            </label>
          </div>
          <div class="mt-4 flex flex-wrap items-center gap-3">
            <GButton variant="secondary" size="sm" :loading="testing" @click="testLlm">
              测试连通
            </GButton>
            <p
              v-if="testResult"
              class="rounded-md px-3 py-2 text-[12px]"
              :class="testResult.ok ? 'bg-success/10 text-success' : 'bg-error/10 text-error'"
            >
              {{ testResult.text }}
            </p>
          </div>
        </template>

        <!-- 步骤 2：网关 + 登录 -->
        <template v-else-if="step === 2">
          <GOverline>步骤 2 / 3</GOverline>
          <h2 class="mt-2 text-[24px]">连接网关并登录</h2>
          <p class="mt-1 text-[13px] text-ink-soft">
            填写 openclaw-onebotv11 网关地址，然后扫码登录微信。
          </p>
          <div class="mt-5 space-y-4">
            <label class="block">
              <span class="mb-1.5 block text-[13px] font-medium text-ink">网关地址</span>
              <GInput v-model="fields.openclaw.gateway_url" />
            </label>
            <label class="block">
              <span class="mb-1.5 block text-[13px] font-medium text-ink">
                Access Token（网关 config.json 自动生成）
              </span>
              <GInput v-model="fields.openclaw.access_token" type="password" />
            </label>

            <div
              v-if="!loginState"
              class="rounded-xl border border-dashed border-line p-6 text-center text-[14px] text-ink-soft"
            >
              先保存网关配置，再发起登录
            </div>
            <div
              v-else
              class="flex items-start gap-4 rounded-xl border border-line bg-bg/70 p-5"
            >
              <template v-if="loginState.status === 'pending' && loginState.qrcodeUrl">
                <QrCode :value="loginState.qrcodeUrl" :size="160" />
                <div class="min-w-0 text-[14px]">
                  <p class="text-ink">用手机微信扫码完成登录</p>
                  <p v-if="loginState.message" class="mt-1 text-[12px] text-ink-soft">
                    {{ loginState.message }}
                  </p>
                </div>
              </template>
              <p v-else-if="loginState.status === 'success'" class="text-success">
                ✅ 登录成功
              </p>
              <p v-else class="text-error">登录失败：{{ loginState.message }}</p>
            </div>

            <GButton block :loading="busy" @click="startLogin">
              {{ loginState ? "重新获取二维码" : "保存并扫码登录" }}
            </GButton>
          </div>
        </template>

        <!-- 步骤 3：完成 -->
        <template v-else>
          <GOverline>步骤 3 / 3</GOverline>
          <h2 class="mt-2 text-[24px]">完成</h2>
          <p class="mt-2 text-[14px] text-ink-soft">
            最小配置已完成。接下来可在控制台查看账号、聊天调试、日志与设置。
          </p>
          <ul class="mt-4 space-y-1.5 text-[14px] text-ink">
            <li>· LLM：{{ fields.llm.base_url }} / {{ fields.llm.model }}</li>
            <li>· 网关：{{ fields.openclaw.gateway_url }}</li>
            <li>· 账号：已登录 {{ loginState?.status === "success" ? "成功" : "待登录" }}</li>
          </ul>
          <GButton class="mt-6" block :loading="busy" @click="finish">
            进入控制台
          </GButton>
        </template>

        <div class="mt-6 flex items-center justify-between">
          <GButton v-if="step > 1" variant="ghost" size="sm" @click="step -= 1">
            上一步
          </GButton>
          <span class="text-[12px] text-neutral">第 {{ step }} / 3 步</span>
          <GButton
            v-if="step < 3"
            variant="secondary"
            size="sm"
            :loading="busy"
            @click="next"
          >
            下一步
          </GButton>
        </div>

        <p v-if="error" class="mt-3 rounded-md bg-error/10 px-3 py-2 text-[13px] text-error">
          {{ error }}
        </p>
        <p v-if="notice" class="mt-3 text-[13px] text-success">{{ notice }}</p>
      </GCard>
    </div>
  </div>
</template>
