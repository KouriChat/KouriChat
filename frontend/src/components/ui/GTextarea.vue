<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    modelValue?: string | number | null;
    modelModifiers?: Record<string, boolean>;
    rows?: number;
    placeholder?: string;
    disabled?: boolean;
    invalid?: boolean;
  }>(),
  { modelValue: "", rows: 3, placeholder: "", disabled: false, invalid: false },
);

const emit = defineEmits<{ "update:modelValue": [value: string | number] }>();

function onInput(event: Event) {
  const raw = (event.target as HTMLTextAreaElement).value;
  if (props.modelModifiers?.number) {
    emit("update:modelValue", raw === "" ? "" : Number(raw));
  } else {
    emit("update:modelValue", raw);
  }
}

const classes = computed(() => [
  "focus-ring w-full rounded-md border bg-surface px-3.5 py-2.5 text-[14px] text-ink",
  "placeholder:text-neutral",
  props.invalid ? "border-error" : "border-line",
  props.disabled ? "cursor-not-allowed opacity-60" : "",
]);
</script>

<template>
  <textarea
    :rows="rows"
    :value="modelValue ?? ''"
    :placeholder="placeholder"
    :disabled="disabled"
    :class="classes"
    @input="onInput"
  />
</template>
