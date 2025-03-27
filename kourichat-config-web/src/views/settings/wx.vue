<script setup lang="ts">
import LogViewerDemo from "../log-viewer-demo.vue";
defineOptions({
  // name 作为一种规范最好必须写上并且和路由的name保持一致
  name: "Settings"
});
</script>

<template>
  <log-viewer-demo />
</template>
