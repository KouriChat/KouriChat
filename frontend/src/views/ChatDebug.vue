<script setup lang="ts">
import { ref } from "vue";
import { api } from "../api";
import { toast } from "../lib/toast";
import GButton from "../components/ui/GButton.vue";
import GCard from "../components/ui/GCard.vue";
import GEmptyState from "../components/ui/GEmptyState.vue";
import GChip from "../components/ui/GChip.vue";
import GInput from "../components/ui/GInput.vue";
import GList from "../components/ui/GList.vue";
import GListRow from "../components/ui/GListRow.vue";

const channelId = ref("");
const sendText = ref("");
const mockText = ref("");
const busy = ref(false);

interface ActionRow {
  kind: "send" | "mock" | "error";
  text: string;
}
const history = ref<ActionRow[]>([]);

async function doSend() {
  if (!channelId.value.trim() || !sendText.value.trim()) return;
  busy.value = true;
  try {
    const res = await api.chatSend({
      channel_id: channelId.value.trim(),
      channel_type: "private",
      text: sendText.value.trim(),
    });
    history.value.unshift({
      kind: "send",
      text: `→ ${channelId.value.trim()} (private): ${sendText.value.trim()}  [id=${res.message_id}]`,
    });
    sendText.value = "";
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    history.value.unshift({ kind: "error", text: `✗ 发送失败: ${message}` });
    toast.error(message);
  } finally {
    busy.value = false;
  }
}

async function doMock() {
  if (!mockText.value.trim()) return;
  busy.value = true;
  try {
    await api.chatMock(mockText.value.trim());
    history.value.unshift({ kind: "mock", text: `✎ 注入消息: ${mockText.value.trim()}` });
    mockText.value = "";
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    history.value.unshift({ kind: "error", text: `✗ 注入失败: ${message}` });
    toast.error(message);
  } finally {
    busy.value = false;
  }
}

const kindTone: Record<ActionRow["kind"], "neutral" | "success" | "error"> = {
  send: "neutral",
  mock: "success",
  error: "error",
};
const kindLabel: Record<ActionRow["kind"], string> = { send: "出", mock: "注", error: "错" };
</script>

<template>
  <div class="grid gap-6 lg:grid-cols-2">
    <GCard>
      <h2 class="text-[20px]">出向发送（私聊 adapter.send）</h2>
      <div class="mt-4 space-y-4">
        <label class="block">
          <span class="mb-1.5 block text-[13px] font-medium text-ink">目标 user_id（微信用户）</span>
          <GInput v-model="channelId" placeholder="如 wxu-123" />
        </label>
        <label class="block">
          <span class="mb-1.5 block text-[13px] font-medium text-ink">文本</span>
          <GInput v-model="sendText" placeholder="要发送的内容" @keyup.enter="doSend" />
        </label>
        <GButton
          block
          :loading="busy"
          :disabled="!channelId.trim() || !sendText.trim()"
          @click="doSend"
        >发送</GButton>
      </div>
    </GCard>

    <GCard>
      <h2 class="text-[20px]">入向模拟（注入 MESSAGE_RECEIVE）</h2>
      <div class="mt-4 space-y-4">
        <label class="block">
          <span class="mb-1.5 block text-[13px] font-medium text-ink">模拟文本</span>
          <GInput
            v-model="mockText"
            placeholder="模拟一条平台消息文本（走完整逻辑链）"
            @keyup.enter="doMock"
          />
        </label>
        <GButton
          variant="secondary"
          block
          :loading="busy"
          :disabled="!mockText.trim()"
          @click="doMock"
        >注入</GButton>
      </div>
    </GCard>

    <GCard class="lg:col-span-2">
      <h2 class="text-[20px]">动作记录</h2>
      <GEmptyState
        v-if="!history.length"
        class="mt-2"
        title="暂无动作"
        description="尝试发送或注入一条消息。"
      />
      <GList v-else class="mt-4">
        <GListRow v-for="(item, i) in history" :key="i">
          <div class="flex items-start gap-2.5">
            <GChip :tone="kindTone[item.kind]" class="shrink-0">{{ kindLabel[item.kind] }}</GChip>
            <span class="terminal break-all text-[12px] text-ink">{{ item.text }}</span>
          </div>
        </GListRow>
      </GList>
    </GCard>
  </div>
</template>
