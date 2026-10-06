<script setup lang="ts">
import type { Component } from "vue";
import {
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuPortal,
  DropdownMenuRoot,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "reka-ui";

defineProps<{
  label?: string;
  items: { key: string; label: string; icon?: Component; danger?: boolean }[];
}>();

const emit = defineEmits<{ select: [key: string] }>();
</script>

<template>
  <DropdownMenuRoot>
    <DropdownMenuTrigger as-child>
      <slot name="trigger" />
    </DropdownMenuTrigger>
    <DropdownMenuPortal>
      <DropdownMenuContent
        align="end"
        :side-offset="8"
        class="z-50 min-w-52 rounded-lg border border-line bg-surface p-1.5 shadow-pop focus:outline-none"
      >
        <DropdownMenuLabel
          v-if="label"
          class="px-2.5 py-1.5 text-[11px] font-medium uppercase tracking-[0.08em] text-ink-soft"
        >
          {{ label }}
        </DropdownMenuLabel>
        <DropdownMenuSeparator v-if="label" class="my-1 h-px bg-line" />
        <DropdownMenuItem
          v-for="item in items"
          :key="item.key"
          class="flex cursor-pointer select-none items-center gap-2 rounded-md px-2.5 py-2 text-[14px] outline-none transition-colors data-[highlighted]:bg-bg"
          :class="item.danger ? 'text-error' : 'text-ink'"
          @select="emit('select', item.key)"
        >
          <component :is="item.icon" v-if="item.icon" class="h-4 w-4 shrink-0" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenuPortal>
  </DropdownMenuRoot>
</template>
