<script setup lang="ts">
import { computed } from "vue";

const props = withDefaults(
  defineProps<{
    hover?: boolean;
    padded?: boolean;
    as?: string;
  }>(),
  { hover: false, padded: true, as: "section" },
);

const classes = computed(() => [
  "overflow-hidden rounded-xl border border-line bg-surface transition duration-200 ease-out",
  props.hover ? "hover:-translate-y-0.5 hover:shadow-card" : "",
]);
</script>

<template>
  <component :is="as" :class="classes">
    <div :class="padded ? 'p-5 sm:p-6' : ''">
      <slot />
    </div>
  </component>
</template>
