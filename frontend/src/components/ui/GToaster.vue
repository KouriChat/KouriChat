<script setup lang="ts">
import { Toaster } from "vue-sonner";
</script>

<template>
  <Toaster
    position="top-right"
    :offset="16"
    :toast-options="{
      class: 'rounded-lg border border-line bg-surface text-ink shadow-pop',
      descriptionClass: 'text-ink-soft',
    }"
  />
</template>
