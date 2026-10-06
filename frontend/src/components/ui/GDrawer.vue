<script setup lang="ts">
import {
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogOverlay,
  DialogPortal,
  DialogRoot,
  DialogTitle,
  DialogTrigger,
} from "reka-ui";

withDefaults(defineProps<{ open?: boolean; title?: string }>(), {
  open: false,
  title: "导航",
});

const emit = defineEmits<{ "update:open": [value: boolean] }>();
</script>

<template>
  <DialogRoot :open="open" @update:open="emit('update:open', $event)">
    <DialogTrigger as-child>
      <slot name="trigger" />
    </DialogTrigger>
    <DialogPortal>
      <DialogOverlay class="fixed inset-0 z-40 bg-ink/25 backdrop-blur-[2px]" />
      <DialogContent
        class="fixed inset-y-0 right-0 z-50 flex w-[min(88vw,320px)] flex-col border-l border-line bg-surface p-5 shadow-pop focus:outline-none"
      >
        <div class="flex items-center justify-between gap-3">
          <DialogTitle class="text-[16px] font-bold text-ink">{{ title }}</DialogTitle>
          <DialogClose as-child>
            <slot name="close" />
          </DialogClose>
        </div>
        <DialogDescription class="sr-only">{{ title }}</DialogDescription>
        <div class="mt-5 flex-1 overflow-y-auto">
          <slot />
        </div>
      </DialogContent>
    </DialogPortal>
  </DialogRoot>
</template>
