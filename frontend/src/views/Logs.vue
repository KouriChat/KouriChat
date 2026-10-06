<script setup lang="ts">
import { nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import { api, type LogRow } from "../api";
import type { ChipTone } from "../components/ui/types";
import GButton from "../components/ui/GButton.vue";
import GCard from "../components/ui/GCard.vue";
import GChip from "../components/ui/GChip.vue";
import GEmptyState from "../components/ui/GEmptyState.vue";
import GSelect from "../components/ui/GSelect.vue";

const older = ref<LogRow[]>([]);
const latest = ref<LogRow[]>([]);
const level = ref("DEBUG");
const error = ref("");
const listEl = ref<HTMLElement | null>(null);
const loadingOlder = ref(false);
const noMore = ref(false);
let timer: number | undefined;
let olderCount = 0;
const PAGE = 300;

function atBottom(): boolean {
  const el = listEl.value;
  if (!el) return false;
  return el.scrollTop + el.clientHeight >= el.scrollHeight - 40;
}

async function refresh() {
  const follow = atBottom();
  const prevTop = listEl.value?.scrollTop ?? 0;
  try {
    latest.value = (await api.logs(PAGE, level.value)).logs;
    error.value = "";
    await nextTick();
    if (follow) {
      const el = listEl.value;
      if (el) el.scrollTop = el.scrollHeight;
    } else if (listEl.value) {
      listEl.value.scrollTop = prevTop;
    }
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  }
}

async function loadOlder() {
  if (loadingOlder.value || noMore.value) return;
  loadingOlder.value = true;
  error.value = "";
  const el = listEl.value;
  const prevHeight = el?.scrollHeight ?? 0;
  try {
    const rows = (await api.logs(PAGE, level.value, olderCount)).logs;
    if (!rows.length) {
      noMore.value = true;
      return;
    }
    older.value = [...rows, ...older.value];
    olderCount += rows.length;
    await nextTick();
    if (el) el.scrollTop += el.scrollHeight - prevHeight;
  } catch (err) {
    error.value = err instanceof Error ? err.message : String(err);
  } finally {
    loadingOlder.value = false;
  }
}

function clear() {
  older.value = [];
  latest.value = [];
  olderCount = 0;
  noMore.value = false;
}

watch(level, () => {
  older.value = [];
  olderCount = 0;
  noMore.value = false;
  refresh();
});

onMounted(() => {
  refresh();
  timer = window.setInterval(refresh, 2000);
});

onUnmounted(() => {
  if (timer !== undefined) window.clearInterval(timer);
});

const levelTone: Record<string, ChipTone> = {
  DEBUG: "neutral",
  INFO: "neutral",
  WARNING: "warning",
  ERROR: "error",
};
const levelColor: Record<string, string> = {
  DEBUG: "text-ink-soft",
  INFO: "text-ink-soft",
  WARNING: "text-warning",
  ERROR: "text-error",
};
</script>

<template>
  <GCard>
    <div class="flex flex-wrap items-center gap-3">
      <h2 class="text-[20px]">运行日志（loguru 环形缓冲）</h2>
      <div class="ml-auto flex items-center gap-2">
        <GSelect v-model="level" class="w-32">
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
        </GSelect>
        <GButton variant="secondary" size="sm" @click="clear">清空显示</GButton>
      </div>
    </div>
    <p class="mt-2 text-[12px] text-ink-soft">
      刷新不会改变滚动位置；滚动到顶可加载更早日志。
    </p>
    <p v-if="error" class="mt-2 rounded-md bg-error/10 px-3 py-2 text-[12px] text-error">
      {{ error }}
    </p>

    <div
      ref="listEl"
      class="terminal mt-4 h-[26rem] overflow-auto rounded-xl border border-line bg-bg/60 p-2 text-[12px] leading-relaxed"
    >
      <div
        class="sticky top-0 z-10 -mx-2 -mt-2 flex justify-center bg-bg/85 px-2 pb-1 pt-2 backdrop-blur"
      >
        <GButton
          variant="ghost"
          size="sm"
          :disabled="loadingOlder || noMore"
          @click="loadOlder"
        >
          {{ noMore ? "没有更早的日志" : loadingOlder ? "加载中…" : "加载更早日志" }}
        </GButton>
      </div>

      <div
        v-for="(row, i) in [...older, ...latest]"
        :key="i"
        class="flex gap-2 border-b border-line/70 py-1.5"
      >
        <span class="shrink-0 whitespace-nowrap text-neutral">{{ row.time }}</span>
        <GChip :tone="levelTone[row.level] ?? 'neutral'" class="shrink-0">
          {{ row.level }}
        </GChip>
        <span class="min-w-0 break-all" :class="levelColor[row.level] ?? 'text-ink-soft'">{{ row.line }}</span>
      </div>

      <GEmptyState
        v-if="!older.length && !latest.length"
        title="暂无日志"
        description="webui 启动后开始捕获。"
      />
    </div>
  </GCard>
</template>
