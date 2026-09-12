<script setup lang="ts">
import { computed } from "vue";
import type { ChipTone } from "./types";

const props = withDefaults(
  defineProps<{ tone?: ChipTone; dot?: boolean }>(),
  { tone: "neutral", dot: false },
);

const toneClass: Record<ChipTone, string> = {
  neutral: "bg-ink/[0.05] text-ink-soft",
  active: "bg-primary text-white",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  error: "bg-error/10 text-error",
};

const dotClass: Record<ChipTone, string> = {
  neutral: "bg-neutral",
  active: "bg-white/90",
  success: "bg-success",
  warning: "bg-warning",
  error: "bg-error",
};

const classes = computed(() => [
  "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-[12px] font-medium whitespace-nowrap",
  toneClass[props.tone],
]);
</script>

<template>
  <span :class="classes">
    <span v-if="dot" class="h-1.5 w-1.5 shrink-0 rounded-full" :class="dotClass[tone]" aria-hidden="true" />
    <slot />
  </span>
</template>
