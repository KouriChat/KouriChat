<script setup lang="ts">
import { ref } from "vue";
import { api, type LoginState } from "../api";
import { useStatus } from "../composables/useStatus";
import QrCode from "../components/QrCode.vue";
import { toast } from "../lib/toast";
import type { ChipTone } from "../components/ui/types";
import GAlertDialog from "../components/ui/GAlertDialog.vue";
import GButton from "../components/ui/GButton.vue";
import GCard from "../components/ui/GCard.vue";
import GEmptyState from "../components/ui/GEmptyState.vue";
import GList from "../components/ui/GList.vue";
import GListRow from "../components/ui/GListRow.vue";
import GStatusChip from "../components/ui/GStatusChip.vue";

const { status, refresh } = useStatus();
const busy = ref(false);

async function startLogin() {
  busy.value = true;
  try {
    await api.login();
    await refresh();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : String(err));
  } finally {
    busy.value = false;
  }
}

async function refreshQr() {
  busy.value = true;
  try {
    await api.loginRefresh();
    await refresh();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : String(err));
  } finally {
    busy.value = false;
  }
}

async function relogin(accountId: string) {
  busy.value = true;
  try {
    await api.relogin(accountId);
    await refresh();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : String(err));
  } finally {
    busy.value = false;
  }
}

const logoutOpen = ref(false);
const logoutTarget = ref("");

function askLogout(accountId: string) {
  logoutTarget.value = accountId;
  logoutOpen.value = true;
}

async function confirmLogout() {
  const accountId = logoutTarget.value;
  busy.value = true;
  try {
    const res = await api.logout(accountId);
    toast.success(res.note ?? "已登出");
    await refresh();
  } catch (err) {
    toast.error(err instanceof Error ? err.message : String(err));
  } finally {
    busy.value = false;
    logoutOpen.value = false;
  }
}

function loginBadge(state: LoginState): { text: string; tone: ChipTone } {
  if (state.status === "success") return { text: "登录成功", tone: "success" };
  if (state.status === "failed") return { text: "登录失败", tone: "error" };
  return { text: "待扫码", tone: "warning" };
}

const accountTone: Record<string, ChipTone> = {
  online: "success",
  invalid: "error",
  offline: "neutral",
};
const accountLabel: Record<string, string> = {
  online: "在线",
  invalid: "失效",
  offline: "离线",
};
</script>

<template>
  <div class="grid gap-6 lg:grid-cols-2">
    <!-- 扫码登录 -->
    <GCard>
      <div class="flex items-center justify-between gap-3">
        <h2 class="text-[20px]">扫码登录</h2>
        <GStatusChip
          v-if="status?.login"
          :label="loginBadge(status.login).text"
          :tone="loginBadge(status.login).tone"
        />
      </div>

      <template v-if="!status?.login">
        <p class="mt-3 text-[14px] text-ink-soft">
          通过 openclaw-onebotv11 的 weixin_login 动作获取二维码，用手机微信扫码完成登录。
        </p>
        <GButton class="mt-4" :loading="busy" @click="startLogin">发起扫码登录</GButton>
      </template>

      <template v-else>
        <div class="mt-4 flex flex-col items-start gap-4 sm:flex-row">
          <QrCode
            v-if="status.login.status === 'pending'"
            :value="status.login.qrcodeUrl"
            :size="176"
          />
          <div class="min-w-0 text-[14px]">
            <p v-if="status.login.status === 'pending'" class="text-ink">
              用手机微信扫描左侧二维码完成登录
            </p>
            <p v-else-if="status.login.status === 'success'" class="text-success">
              ✅ 登录成功
            </p>
            <p v-else class="text-error">登录失败：{{ status.login.message }}</p>
            <a
              v-if="status.login.status === 'pending' && status.login.qrcodeUrl"
              :href="status.login.qrcodeUrl"
              target="_blank"
              rel="noopener"
              class="mt-2 block break-all text-[12px]"
            >{{ status.login.qrcodeUrl }}</a>
            <GButton
              v-if="status.login.status === 'pending'"
              variant="secondary"
              size="sm"
              class="mt-3"
              :loading="busy"
              @click="refreshQr"
            >刷新二维码</GButton>
            <p
              v-if="status.login.status === 'pending' && status.login.message"
              class="mt-2 text-[12px] text-ink-soft"
            >
              {{ status.login.message }}
            </p>
            <p v-if="status.login.status === 'failed'" class="mt-2 text-[12px] text-warning">
              二维码可能已失效，可重新获取。
            </p>
            <GButton
              v-if="status.login.status === 'failed'"
              variant="secondary"
              size="sm"
              class="mt-3"
              :loading="busy"
              @click="startLogin"
            >重新获取二维码</GButton>
          </div>
        </div>
      </template>
    </GCard>

    <!-- 账号列表 -->
    <GCard>
      <h2 class="text-[20px]">已登录账号（本地镜像）</h2>
      <GEmptyState
        v-if="!status?.accounts.length"
        class="mt-2"
        title="暂无账号"
        description="先在左侧扫码登录。"
      />
      <GList v-else class="mt-4">
        <GListRow v-for="acc in status.accounts" :key="acc.accountId">
          <div class="flex flex-wrap items-center gap-2">
            <GStatusChip
              :label="accountLabel[acc.status] ?? acc.status"
              :tone="accountTone[acc.status] ?? 'neutral'"
            />
            <code class="text-[14px] font-medium text-ink">{{ acc.accountId }}</code>
            <span v-if="acc.userId" class="text-[12px] text-neutral"
              >userId: {{ acc.userId }}</span
            >
          </div>
          <div class="mt-3 flex gap-2">
            <GButton
              v-if="acc.status === 'invalid'"
              variant="secondary"
              size="sm"
              :loading="busy"
              @click="relogin(acc.accountId)"
            >重新登录</GButton>
            <GButton
              variant="destructive"
              size="sm"
              :loading="busy"
              @click="askLogout(acc.accountId)"
            >登出</GButton>
          </div>
        </GListRow>
      </GList>
    </GCard>

    <GAlertDialog
      v-model:open="logoutOpen"
      title="确认登出账号？"
      :description="`将通知网关 weixin_logout 并本地移除 ${logoutTarget}。`"
      confirm-text="登出"
      danger
      :loading="busy"
      @confirm="confirmLogout"
    >
      <template #trigger><span class="hidden" /></template>
    </GAlertDialog>
  </div>
</template>
