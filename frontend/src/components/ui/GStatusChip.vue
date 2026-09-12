<script setup lang="ts">
import type { ChipTone } from "./types";
import GChip from "./GChip.vue";

defineProps<{ label: string; tone: ChipTone }>();
</script>

<template>
  <GChip :tone="tone" dot>{{ label }}</GChip>
</template>
