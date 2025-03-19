<template>
  <div class="disk-gauge">
    <div class="statistic-container">
      <el-statistic :value="used" :precision="2">
        <template #suffix>/{{ total }} GB</template>
      </el-statistic>
    </div>
    <div ref="chartRef" style="width: 100%; height: 240px" />
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount } from "vue";
import * as echarts from "echarts";
import type { EChartsOption } from "echarts";

const props = defineProps<{
  used: number;
  total: number;
}>();

const chartRef = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

// 定义仪表盘数据
const gaugeData = ref([
  {
    value: 0,
    name: "磁盘使用",
    title: {
      offsetCenter: ["0%", "30%"]
    },
    detail: {
      valueAnimation: true,
      offsetCenter: ["0%", "0%"]
    }
  }
]);

// 初始化图表配置
const option: EChartsOption = {
  series: [
    {
      type: "gauge",
      startAngle: 90,
      endAngle: -270,
      pointer: {
        show: false
      },
      progress: {
        show: true,
        overlap: false,
        roundCap: true,
        clip: false,
        itemStyle: {
          borderWidth: 1,
          borderColor: "#464646"
        }
      },
      axisLine: {
        lineStyle: {
          width: 20
        }
      },
      splitLine: {
        show: false,
        distance: 0,
        length: 10
      },
      axisTick: {
        show: false
      },
      axisLabel: {
        show: false,
        distance: 50
      },
      data: gaugeData.value,
      title: {
        fontSize: 14,
        fontWeight: "bold"
      },
      detail: {
        width: 50,
        height: 14,
        fontSize: 14,
        fontWeight: "bold",
        color: "inherit",
        borderColor: "inherit",
        borderRadius: 20,
        borderWidth: 1,
        formatter: "{value}%"
      }
    }
  ]
};

// 初始化图表
function initChart() {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value);
    chart.setOption(option);
    updateChart();
  }
}

// 更新图表
function updateChart() {
  if (!chart) return;

  const percentage = (props.used / props.total) * 100;
  gaugeData.value[0].value = parseFloat(percentage.toFixed(2));

  chart.setOption({
    series: [
      {
        data: gaugeData.value,
        pointer: {
          show: false
        }
      }
    ]
  });
}

// 处理窗口大小变化
function handleResize() {
  chart?.resize();
}

// 监听属性变化
watch(
  () => [props.used, props.total],
  () => {
    updateChart();
  }
);

// 生命周期钩子
onMounted(() => {
  initChart();
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  chart?.dispose();
});
</script>

<style scoped>
.disk-gauge {
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
