<script setup lang="ts">
import { Inbox } from "@lucide/vue";

withDefaults(defineProps<{ title: string; description?: string }>(), {
  description: "",
});
</script>

<template>
  <div class="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
    <slot name="icon">
      <Inbox class="h-6 w-6 text-neutral" aria-hidden="true" />
    </slot>
    <p class="text-[14px] font-medium text-ink">{{ title }}</p>
    <p v-if="description" class="max-w-sm text-[13px] text-ink-soft">{{ description }}</p>
  </div>
</template>
