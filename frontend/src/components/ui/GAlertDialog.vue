<script setup lang="ts">
import {
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogOverlay,
  AlertDialogPortal,
  AlertDialogRoot,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "reka-ui";
import GButton from "./GButton.vue";

withDefaults(
  defineProps<{
    open?: boolean;
    title: string;
    description?: string;
    confirmText?: string;
    cancelText?: string;
    danger?: boolean;
    loading?: boolean;
  }>(),
  {
    open: false,
    description: "",
    confirmText: "确认",
    cancelText: "取消",
    danger: false,
    loading: false,
  },
);

const emit = defineEmits<{ "update:open": [value: boolean]; confirm: [] }>();
</script>

<template>
  <AlertDialogRoot :open="open" @update:open="emit('update:open', $event)">
    <AlertDialogTrigger as-child>
      <slot name="trigger" />
    </AlertDialogTrigger>
    <AlertDialogPortal>
      <AlertDialogOverlay class="fixed inset-0 z-40 bg-ink/25 backdrop-blur-[2px]" />
      <AlertDialogContent
        class="fixed left-1/2 top-1/2 z-50 w-[min(92vw,420px)] -translate-x-1/2 -translate-y-1/2 rounded-xl border border-line bg-surface p-6 shadow-pop focus:outline-none"
      >
        <AlertDialogTitle class="text-[20px] font-bold tracking-tight text-ink">
          {{ title }}
        </AlertDialogTitle>
        <AlertDialogDescription v-if="description" class="mt-2 text-[14px] text-ink-soft">
          {{ description }}
        </AlertDialogDescription>
        <div class="mt-6 flex justify-end gap-2">
          <AlertDialogCancel as-child>
            <GButton variant="secondary" size="sm" @click="emit('update:open', false)">
              {{ cancelText }}
            </GButton>
          </AlertDialogCancel>
          <AlertDialogAction as-child>
            <GButton
              :variant="danger ? 'destructive' : 'primary'"
              size="sm"
              :loading="loading"
              @click="emit('confirm')"
            >
              {{ confirmText }}
            </GButton>
          </AlertDialogAction>
        </div>
      </AlertDialogContent>
    </AlertDialogPortal>
  </AlertDialogRoot>
</template>
