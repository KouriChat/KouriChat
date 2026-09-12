<script setup lang="ts">
import {
  TooltipContent,
  TooltipPortal,
  TooltipProvider,
  TooltipRoot,
  TooltipTrigger,
} from "reka-ui";

withDefaults(
  defineProps<{ content: string; side?: "top" | "right" | "bottom" | "left" }>(),
  { side: "top" },
);
</script>

<template>
  <TooltipProvider :delay-duration="200">
    <TooltipRoot>
      <TooltipTrigger as-child>
        <slot />
      </TooltipTrigger>
      <TooltipPortal>
        <TooltipContent
          :side="side"
          :side-offset="6"
          class="z-50 rounded-md bg-ink px-2.5 py-1.5 text-[12px] font-medium text-white shadow-pop"
        >
          {{ content }}
        </TooltipContent>
      </TooltipPortal>
    </TooltipRoot>
  </TooltipProvider>
</template>
