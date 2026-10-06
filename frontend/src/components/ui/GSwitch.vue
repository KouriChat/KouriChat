<script setup lang="ts">
import { SwitchRoot, SwitchThumb } from "reka-ui";

withDefaults(
  defineProps<{ modelValue?: boolean; disabled?: boolean; id?: string }>(),
  { modelValue: false, disabled: false },
);

const emit = defineEmits<{ "update:modelValue": [value: boolean] }>();
</script>

<template>
  <SwitchRoot
    :id="id"
    :model-value="modelValue"
    :disabled="disabled"
    class="focus-ring relative inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full bg-line transition-colors data-[state=checked]:bg-primary disabled:cursor-not-allowed disabled:opacity-50"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <SwitchThumb
      class="block h-4 w-4 translate-x-0.5 rounded-full bg-white shadow-sm transition-transform data-[state=checked]:translate-x-[18px]"
    />
  </SwitchRoot>
</template>
