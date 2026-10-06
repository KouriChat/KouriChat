<script setup lang="ts">
import { computed } from "vue";
import { LoaderCircle } from "@lucide/vue";

type Variant = "primary" | "secondary" | "ghost" | "destructive";
type Size = "sm" | "md" | "lg";

const props = withDefaults(
  defineProps<{
    variant?: Variant;
    size?: Size;
    type?: "button" | "submit" | "reset";
    disabled?: boolean;
    loading?: boolean;
    block?: boolean;
  }>(),
  {
    variant: "primary",
    size: "md",
    type: "button",
    disabled: false,
    loading: false,
    block: false,
  },
);

const variantClass: Record<Variant, string> = {
  primary: "border border-transparent bg-primary text-white hover:bg-primary-hover hover:shadow-primary",
  secondary: "border border-line bg-surface text-ink hover:border-neutral/60 hover:bg-bg",
  ghost: "border border-transparent text-ink-soft hover:bg-ink/[0.05] hover:text-ink",
  destructive: "border border-error/40 text-error hover:border-error hover:bg-error/[0.06]",
};

const sizeClass: Record<Size, string> = {
  sm: "h-8 gap-1.5 px-3 text-[13px]",
  md: "h-[38px] gap-2 px-4 text-[14px]",
  lg: "h-11 gap-2 px-6 text-[15px]",
};

const classes = computed(() => [
  "focus-ring inline-flex shrink-0 items-center justify-center rounded-md font-medium",
  "transition duration-200 ease-out hover:-translate-y-px active:translate-y-0",
  "disabled:pointer-events-none disabled:opacity-50",
  sizeClass[props.size],
  variantClass[props.variant],
  props.block ? "w-full" : "",
]);
</script>

<template>
  <button :type="type" :disabled="disabled || loading" :class="classes">
    <LoaderCircle v-if="loading" class="h-4 w-4 animate-spin" aria-hidden="true" />
    <slot />
  </button>
</template>
