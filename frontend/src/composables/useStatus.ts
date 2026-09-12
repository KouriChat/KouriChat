import { onMounted, onUnmounted, ref } from "vue";
import { api, type Status } from "../api";

const status = ref<Status | null>(null);
const statusError = ref("");
let consumers = 0;
let timer: number | undefined;

async function refresh() {
  try {
    status.value = await api.status();
    statusError.value = "";
  } catch (err) {
    statusError.value = err instanceof Error ? err.message : String(err);
  }
}

/**
 * 共享的网关状态轮询（3s）。多个消费者共用同一个 interval，
 * 最后一个卸载时自动停止。
 */
export function useStatus() {
  onMounted(() => {
    consumers += 1;
    if (consumers === 1) {
      refresh();
      timer = window.setInterval(refresh, 3000);
    }
  });
  onUnmounted(() => {
    consumers = Math.max(0, consumers - 1);
    if (consumers === 0 && timer !== undefined) {
      window.clearInterval(timer);
      timer = undefined;
    }
  });

  return { status, statusError, refresh };
}
