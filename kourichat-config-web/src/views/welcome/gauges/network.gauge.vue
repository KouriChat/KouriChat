<template>
  <div class="network-gauge">
    <div class="statistic-container">
      <el-statistic :value="download" :precision="2">
        <template #suffix>/ {{ upload }} KB/s</template>
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
  download: number;
  upload: number;
}>();

// 图表引用和实例
const chartRef = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

// 用于存储历史数据
const MAX_DATA_POINTS = 10;
const timeData = ref<string[]>([]);
const downloadData = ref<number[]>([]);
const uploadData = ref<number[]>([]);

// 初始化图表配置
const option: EChartsOption = {
  tooltip: {
    trigger: "axis",
    axisPointer: {
      type: "shadow"
    }
  },
  legend: {
    data: ["下载", "上传"],
    textStyle: {
      color: "#666"
    }
  },
  grid: {
    left: "3%",
    right: "4%",
    bottom: "3%",
    containLabel: true
  },
  xAxis: {
    type: "category",
    data: timeData.value,
    axisLine: {
      lineStyle: {
        color: "#999"
      }
    },
    axisLabel: {
      formatter: (value: string) => {
        return value.substring(value.length - 8); // 仅显示时间部分 HH:MM:SS
      }
    }
  },
  yAxis: {
    type: "value",
    name: "KB/s",
    nameTextStyle: {
      padding: [0, 0, 0, 40]
    },
    axisLine: {
      lineStyle: {
        color: "#999"
      }
    },
    splitLine: {
      lineStyle: {
        type: "dashed",
        color: "#eee"
      }
    },
    axisLabel: {
      formatter: (value: number) => {
        if (value >= 1024) {
          return (value / 1024).toFixed(1) + " MB/s";
        }
        return value + " KB/s";
      }
    }
  },
  series: [
    {
      name: "下载",
      type: "line",
      smooth: true,
      showAllSymbol: true,
      symbol: "emptyCircle",
      symbolSize: 8,
      lineStyle: {
        width: 3,
        color: "#37a2da"
      },
      itemStyle: {
        color: "#37a2da"
      },
      data: downloadData.value
    },
    {
      name: "上传",
      type: "bar",
      barWidth: 10,
      itemStyle: {
        borderRadius: 5,
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: "#67e0e3" },
          { offset: 1, color: "#3fb1e3" }
        ])
      },
      data: uploadData.value
    },
    {
      name: "下载背景",
      type: "bar",
      barGap: "-100%",
      barWidth: 10,
      itemStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: "rgba(55,162,218,0.3)" },
          { offset: 0.2, color: "rgba(55,162,218,0.1)" },
          { offset: 1, color: "rgba(55,162,218,0)" }
        ])
      },
      z: -12,
      data: downloadData.value
    },
    {
      name: "装饰点",
      type: "pictorialBar",
      symbol: "rect",
      itemStyle: {
        color: "#ffffff"
      },
      symbolRepeat: true,
      symbolSize: [12, 4],
      symbolMargin: 1,
      z: -10,
      data: downloadData.value
    }
  ]
};

// 初始化图表
function initChart() {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value);
    chart.setOption(option);
  }
}

// 添加新数据点
function addDataPoint(download: number, upload: number) {
  const now = new Date();
  const timeStr = `${now.getHours().toString().padStart(2, "0")}:${now.getMinutes().toString().padStart(2, "0")}:${now.getSeconds().toString().padStart(2, "0")}`;

  // 添加新数据
  timeData.value.push(timeStr);
  downloadData.value.push(download);
  uploadData.value.push(upload);

  // 保持数据长度不超过MAX_DATA_POINTS
  if (timeData.value.length > MAX_DATA_POINTS) {
    timeData.value.shift();
    downloadData.value.shift();
    uploadData.value.shift();
  }

  updateChart();
}

// 更新图表
function updateChart() {
  if (!chart) return;

  // 计算y轴最大值，确保有足够的空间显示
  const maxValue = Math.max(...downloadData.value, ...uploadData.value) * 1.2; // 增加20%的空间

  chart.setOption({
    xAxis: {
      data: timeData.value
    },
    yAxis: {
      max: maxValue
    },
    series: [
      {
        data: downloadData.value
      },
      {
        data: uploadData.value
      },
      {
        data: downloadData.value
      },
      {
        data: downloadData.value
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
  () => [props.download, props.upload],
  ([newDownload, newUpload]) => {
    addDataPoint(newDownload, newUpload);
  }
);

// 生命周期钩子
onMounted(() => {
  initChart();
  window.addEventListener("resize", handleResize);

  // 初始数据
  const now = new Date();
  for (let i = 0; i < 5; i++) {
    const time = new Date(now.getTime() - (5 - i) * 1000);
    const timeStr = `${time.getHours().toString().padStart(2, "0")}:${time.getMinutes().toString().padStart(2, "0")}:${time.getSeconds().toString().padStart(2, "0")}`;
    timeData.value.push(timeStr);
    downloadData.value.push(0);
    uploadData.value.push(0);
  }
  updateChart();
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  chart?.dispose();
});
</script>

<style scoped>
.network-gauge {
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
