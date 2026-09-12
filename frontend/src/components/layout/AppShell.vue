<script setup lang="ts">
import TopNav from "./TopNav.vue";
</script>

<template>
  <div class="min-h-screen">
    <TopNav />
    <main class="mx-auto w-full max-w-[1280px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
      <slot />
    </main>
  </div>
</template>
