<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from "vue";
import * as d3 from "d3";
import { api } from "../api";
import { useStatus } from "../composables/useStatus";
import GCard from "../components/ui/GCard.vue";
import GOverline from "../components/ui/GOverline.vue";

const { status } = useStatus();

const personas = ref<{ count: number; active: string | null }>({ count: 0, active: null });
const firstRun = ref(false);
const donutEl = ref<HTMLElement | null>(null);
const sparkEl = ref<HTMLElement | null>(null);
let dashTimer: number | undefined;
let logTimer: number | undefined;

/** 数字滚动：从当前值缓动到目标；rAF 被后台节流时用 timeout 兜底最终值。 */
function useCountUp(target: () => number, duration = 700) {
  const value = ref(0);
  let raf = 0;
  let fallback: number | undefined;

  watch(
    target,
    (to) => {
      const begin = value.value;
      if (begin === to) return;
      if (fallback !== undefined) window.clearTimeout(fallback);
      cancelAnimationFrame(raf);
      const start = performance.now();
      const step = (now: number) => {
        const t = Math.min(1, (now - start) / duration);
        const eased = 1 - Math.pow(1 - t, 3);
        value.value = Math.round(begin + (to - begin) * eased);
        if (t < 1) raf = requestAnimationFrame(step);
        else value.value = to;
      };
      raf = requestAnimationFrame(step);
      fallback = window.setTimeout(() => {
        value.value = to;
      }, duration + 120);
    },
    { immediate: true },
  );

  onUnmounted(() => {
    cancelAnimationFrame(raf);
    if (fallback !== undefined) window.clearTimeout(fallback);
  });

  return value;
}

const accountsNum = useCountUp(() => status.value?.accounts.length ?? 0);
const onlineNum = useCountUp(
  () => (status.value?.accounts ?? []).filter((a) => a.status === "online").length,
);
const personasNum = useCountUp(() => personas.value.count);

async function refreshDashboard() {
  try {
    const d = await api.dashboard();
    personas.value = d.personas;
    firstRun.value = d.first_run;
  } catch (err) {
    console.warn("dashboard fetch failed", err);
  }
}

async function refreshSpark() {
  try {
    const { logs } = await api.logs(500, "DEBUG");
    drawSpark(logs.map((l) => new Date(l.time).getTime()));
  } catch {
    /* 图表留空 */
  }
}

const STATUS_COLORS: Record<string, string> = {
  online: "#10b981",
  invalid: "#ef4444",
  offline: "#9c9c9c",
};

function statusSummary() {
  const a = status.value?.accounts ?? [];
  return {
    online: a.filter((x) => x.status === "online").length,
    invalid: a.filter((x) => x.status === "invalid").length,
    offline: a.filter((x) => x.status === "offline").length,
  };
}

function drawDonut() {
  const el = donutEl.value;
  if (!el) return;
  const counts: Record<string, number> = { online: 0, invalid: 0, offline: 0 };
  for (const a of status.value?.accounts ?? []) counts[a.status] = (counts[a.status] ?? 0) + 1;
  const data = Object.entries(counts)
    .map(([statusKey, value]) => ({ status: statusKey, value }))
    .filter((d) => d.value > 0);
  el.innerHTML = "";
  if (!data.length) return;
  const total = data.reduce((s, d) => s + d.value, 0);
  const W = 190;
  const R = 74;
  const svg = d3
    .select(el)
    .append("svg")
    .attr("width", W)
    .attr("height", W)
    .append("g")
    .attr("transform", `translate(${W / 2},${W / 2})`);
  const arc = d3.arc<d3.PieArcDatum<{ status: string; value: number }>>().innerRadius(R - 28).outerRadius(R);
  const pie = d3
    .pie<{ status: string; value: number }>()
    .value((d) => d.value)
    .sort(null);
  svg
    .selectAll("path")
    .data(pie(data))
    .enter()
    .append("path")
    .attr("d", arc as never)
    .attr("fill", (d) => STATUS_COLORS[d.data.status] ?? "#9c9c9c")
    .attr("stroke", "#ffffff")
    .attr("stroke-width", "3");
  const mid = svg.append("g");
  mid
    .append("text")
    .attr("text-anchor", "middle")
    .attr("dy", "0.35em")
    .attr("fill", "#0a0a0a")
    .attr("font-size", "30")
    .attr("font-weight", "700")
    .text(String(total));
  mid
    .append("text")
    .attr("text-anchor", "middle")
    .attr("dy", "24")
    .attr("fill", "#6b6b6b")
    .attr("font-size", "11")
    .text("账号");
}

let sparkTimes: number[] = [];

function drawSpark(times: number[]) {
  const el = sparkEl.value;
  if (!el) return;
  sparkTimes = times;
  el.innerHTML = "";
  if (!times.length) {
    el.innerHTML = '<p class="text-[12px] text-ink-soft">暂无日志数据</p>';
    return;
  }
  const W = Math.max(260, Math.floor(el.clientWidth) || 360);
  const H = 160;
  const pad = 20;
  const now = Date.now();
  const windowMs = 10 * 60 * 1000;
  const buckets = 6;
  const binSize = windowMs / buckets;
  const bins = Array.from({ length: buckets }, (_, i) => ({
    count: times.filter(
      (t) => t >= now - windowMs + i * binSize && t < now - windowMs + (i + 1) * binSize,
    ).length,
  }));
  const max = Math.max(1, d3.max(bins, (b) => b.count) ?? 1);
  const x = d3
    .scaleBand<number>()
    .domain(bins.map((_, i) => i))
    .range([pad, W - pad])
    .padding(0.28);
  const y = d3.scaleLinear().domain([0, max]).range([H - pad, pad]);
  const svg = d3.select(el).append("svg").attr("width", W).attr("height", H);
  for (let i = 0; i <= 4; i++) {
    const yy = pad + ((H - 2 * pad) / 4) * i;
    svg
      .append("line")
      .attr("x1", pad)
      .attr("x2", W - pad)
      .attr("y1", yy)
      .attr("y2", yy)
      .attr("stroke", "rgba(10,10,10,0.06)")
      .attr("stroke-dasharray", "3 5");
  }
  svg
    .selectAll("rect")
    .data(bins)
    .enter()
    .append("rect")
    .attr("x", (_, i) => x(i) as number)
    .attr("y", (d) => y(d.count))
    .attr("width", Math.max(4, x.bandwidth()))
    .attr("height", (d) => (d.count > 0 ? Math.max(3, H - pad - y(d.count)) : 0))
    .attr("rx", 4)
    .attr("fill", "#6366f1")
    .append("title")
    .text((d) => `${d.count} 条日志`);
  svg
    .append("line")
    .attr("x1", pad)
    .attr("x2", W - pad)
    .attr("y1", H - pad)
    .attr("y2", H - pad)
    .attr("stroke", "rgba(10,10,10,0.12)");
  svg
    .append("text")
    .attr("x", W - pad)
    .attr("y", 14)
    .attr("text-anchor", "end")
    .attr("fill", "#6b6b6b")
    .attr("font-size", "11")
    .text("近 10 分钟日志频率");
}

watch(
  () => status.value?.accounts,
  () => drawDonut(),
  { deep: true, immediate: true },
);

function redrawSpark() {
  if (sparkTimes.length) drawSpark(sparkTimes);
}

onMounted(() => {
  window.addEventListener("resize", redrawSpark);
  refreshDashboard();
  refreshSpark();
  dashTimer = window.setInterval(refreshDashboard, 5000);
  logTimer = window.setInterval(refreshSpark, 4000);
  drawDonut();
});

onUnmounted(() => {
  window.removeEventListener("resize", redrawSpark);
  if (dashTimer !== undefined) window.clearInterval(dashTimer);
  if (logTimer !== undefined) window.clearInterval(logTimer);
});
</script>

<template>
  <div class="space-y-6">
    <!-- KPI -->
    <div class="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <GCard hover>
        <GOverline>网关连接</GOverline>
        <p class="mt-2 flex items-center gap-2 text-[32px] font-bold leading-none tracking-tight">
          <span
            class="inline-block h-2.5 w-2.5 rounded-full"
            :class="status?.connected ? 'bg-success' : 'bg-error'"
          />
          <span>{{ status?.connected ? "已连接" : "未连接" }}</span>
        </p>
        <p v-if="status?.gateway_url" class="mt-3 truncate text-[13px] text-ink-soft">
          {{ status.gateway_url }}
        </p>
      </GCard>

      <GCard hover>
        <GOverline>已登录账号</GOverline>
        <p class="mt-2 text-[32px] font-bold leading-none tabular-nums">
          {{ accountsNum }}
          <span class="text-[15px] font-normal text-ink-soft">个</span>
        </p>
        <p class="mt-3 text-[13px] text-ink-soft">
          在线 <span class="tabular-nums text-ink">{{ onlineNum }}</span> · 失效
          {{ statusSummary().invalid }}
        </p>
      </GCard>

      <GCard hover>
        <GOverline>人设</GOverline>
        <p class="mt-2 text-[32px] font-bold leading-none tabular-nums">{{ personasNum }}</p>
        <p class="mt-3 truncate text-[13px] text-ink-soft">
          {{ personas.active ? `启用：${personas.active}` : "未启用" }}
        </p>
      </GCard>

      <GCard hover>
        <GOverline>登录状态</GOverline>
        <p
          class="mt-2 text-[32px] font-bold leading-none"
          :class="
            status?.login?.status === 'success'
              ? 'text-success'
              : status?.login?.status === 'failed'
                ? 'text-error'
                : 'text-warning'
          "
        >
          {{
            status?.login
              ? status.login.status === "pending"
                ? "扫码中"
                : status.login.status === "success"
                  ? "已登录"
                  : "失败"
              : "未发起"
          }}
        </p>
        <p v-if="status?.login?.message" class="mt-3 truncate text-[13px] text-ink-soft">
          {{ status.login.message }}
        </p>
      </GCard>
    </div>

    <!-- 图表 + 指引 -->
    <div class="grid gap-6 lg:grid-cols-3">
      <GCard>
        <h2 class="text-[20px]">账号状态分布</h2>
        <div ref="donutEl" class="mt-4 flex items-center justify-center" />
        <div class="mt-3 flex flex-wrap items-center justify-center gap-4 text-[13px]">
          <span class="flex items-center gap-1.5 text-ink-soft">
            <span class="h-2 w-2 rounded-full bg-success" />在线 {{ statusSummary().online }}
          </span>
          <span class="flex items-center gap-1.5 text-ink-soft">
            <span class="h-2 w-2 rounded-full bg-error" />失效 {{ statusSummary().invalid }}
          </span>
          <span class="flex items-center gap-1.5 text-ink-soft">
            <span class="h-2 w-2 rounded-full bg-neutral" />离线 {{ statusSummary().offline }}
          </span>
        </div>
      </GCard>

      <GCard>
        <h2 class="text-[20px]">活动频率</h2>
        <div ref="sparkEl" class="mt-4 overflow-x-auto" />
      </GCard>

      <GCard>
        <h2 class="text-[20px]">快速指引</h2>
        <ul class="mt-4 space-y-2.5 text-[14px] text-ink-soft">
          <li class="flex gap-2"><span class="text-primary">›</span><span>「账号」页扫码登录 / 失效重登 / 登出。</span></li>
          <li class="flex gap-2"><span class="text-primary">›</span><span>「聊天调试」页模拟入向或直发平台。</span></li>
          <li class="flex gap-2"><span class="text-primary">›</span><span>「日志」页实时查看并过滤日志。</span></li>
          <li class="flex gap-2"><span class="text-primary">›</span><span>「设置」页表单形式即时保存。</span></li>
        </ul>
        <p
          v-if="firstRun"
          class="mt-4 rounded-lg border border-warning/30 bg-warning/[0.08] p-3 text-[13px] text-warning"
        >
          首次使用：先完成快速引导（API token / 登录账号），再接入正式网关。
        </p>
      </GCard>
    </div>

    <!-- 失效警示 -->
    <GCard v-if="status?.needs_relogin?.length" class="border-warning/40">
      <h2 class="text-[20px] text-warning">有账号登录失效，需要重新登录</h2>
      <ul class="mt-3 flex flex-wrap gap-2">
        <li
          v-for="aid in status.needs_relogin"
          :key="aid"
          class="rounded-md border border-warning/30 bg-warning/[0.06] px-3 py-1.5 font-mono text-[12px] text-warning"
        >
          {{ aid }}
        </li>
      </ul>
    </GCard>
  </div>
</template>
