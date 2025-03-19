<template>
  <div class="memory-gauge">
    <div class="statistic-container">
      <el-statistic :value="used" :precision="2">
        <template #suffix>/{{ total }} GB</template>
      </el-statistic>
    </div>
    <div ref="chartRef" style="width: 100%; height: 240px" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount, inject } from "vue";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";

const props = defineProps<{
  used: number;
  total: number;
}>();

onMounted(() => {
  initChart();
});

const chartRef = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

// 渐变色定义
const colorStops = [
  { offset: 0, color: "#67e0e3" }, // 浅青色 - 开始
  { offset: 0.25, color: "#37a2da" }, // 蓝色
  { offset: 0.5, color: "#9fe6b8" }, // 浅绿色
  { offset: 0.75, color: "#ffdb5c" }, // 黄色
  { offset: 1, color: "#fd666d" } // 红色 - 结束
];

const option: EChartsOption = {
  series: [
    {
      type: "gauge",
      startAngle: 180,
      endAngle: 0,
      center: ["50%", "75%"],
      radius: "95%",
      min: 0,
      max: 100,
      splitNumber: 8,
      axisLine: {
        lineStyle: {
          width: 10,
          color: [
            [
              1,
              new echarts.graphic.LinearGradient(0, 0, 1, 0, [
                { offset: 0, color: "#67e0e3" }, // 浅青色
                { offset: 0.33, color: "#37a2da" }, // 蓝色
                { offset: 0.66, color: "#ffdb5c" }, // 黄色
                { offset: 1, color: "#fd666d" } // 红色
              ]) as any
            ]
          ]
        }
      },
      pointer: {
        icon: "path://M12.8,0.7l12,40.1H0.7L12.8,0.7z",
        length: "12%",
        width: 20,
        offsetCenter: [0, "-60%"],
        itemStyle: {
          color: "inherit"
        }
      },
      axisTick: {
        show: true,
        length: 8,
        lineStyle: {
          color: "inherit",
          width: 1
        }
      },
      splitLine: {
        length: 12,
        lineStyle: {
          color: "inherit",
          width: 2
        }
      },
      axisLabel: {
        color: "#464646",
        fontSize: 14,
        fontWeight: "bold",
        distance: -60,
        formatter: function (value: number) {
          if (value === 0 || value === 100) {
            return value + "";
          }
          return "";
        }
      },
      detail: {
        fontSize: 28,
        offsetCenter: [0, "0%"],
        valueAnimation: true,
        formatter: function (value: number) {
          return value.toFixed(1) + "%";
        },
        color: "inherit"
      },
      data: [
        {
          value: 0
        }
      ]
    }
  ]
};

function initChart() {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value);
    chart.setOption(option);
    updateChart();
  }
}

function updateChart() {
  if (chart) {
    const percentage = (props.used / props.total) * 100;
    chart.setOption({
      series: [
        {
          data: [
            {
              value: percentage
            }
          ]
        }
      ]
    });
  }
}

watch(
  () => [props.used, props.total],
  () => {
    updateChart();
  }
);
</script>

<style scoped>
.memory-gauge {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  height: 100%;
}

.statistic-container {
  margin-bottom: 0;
}

:deep(.el-statistic__content) {
  font-size: 20px;
  font-weight: bold;
  color: var(--el-color-primary);
}

:deep(.el-statistic__suffix) {
  margin-left: 4px;
  font-size: 14px;
  color: var(--el-text-color-regular);
}
</style>
