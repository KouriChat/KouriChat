<script setup lang="ts">
withDefaults(defineProps<{ modelValue?: string; disabled?: boolean }>(), {
  modelValue: "",
  disabled: false,
});

const emit = defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<template>
  <select
    :value="modelValue"
    :disabled="disabled"
    class="focus-ring w-full appearance-none rounded-md border border-line bg-surface px-3.5 py-2.5 text-[14px] text-ink disabled:cursor-not-allowed disabled:opacity-60"
    @change="emit('update:modelValue', ($event.target as HTMLSelectElement).value)"
  >
    <slot />
  </select>
</template>
