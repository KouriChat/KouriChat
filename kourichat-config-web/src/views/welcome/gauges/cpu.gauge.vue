<template>
  <div ref="chartRef" style="width: 100%; height: 240px" />
</template>

<script setup lang="ts">
import { ref, onMounted, watch, onBeforeUnmount } from "vue";
import * as echarts from "echarts";
import type {
  EChartsOption,
  CustomSeriesRenderItemParams,
  CustomSeriesRenderItemAPI,
  CustomSeriesRenderItemReturn
} from "echarts";

const props = defineProps<{
  value: number;
}>();

const chartRef = ref<HTMLElement | null>(null);
let chart: echarts.ECharts | null = null;

// 渐变色定义 - 反转顺序
const colorStops = [
  { offset: 0, color: "#fd666d" }, // 红色 - 开始
  { offset: 0.25, color: "#ffdb5c" }, // 黄色
  { offset: 0.5, color: "#9fe6b8" }, // 浅绿色
  { offset: 0.75, color: "#37a2da" }, // 蓝色
  { offset: 1, color: "#67e0e3" } // 浅青色 - 结束
];

// 自定义渲染函数配置
const _valOnRadianMax = 100;
const _outerRadius = 120;
const _innerRadius = 100;
const _pointerInnerRadius = 30;
const _insidePanelRadius = 80;

function renderItem(
  params: CustomSeriesRenderItemParams,
  api: CustomSeriesRenderItemAPI
): CustomSeriesRenderItemReturn {
  // 确保值在0-100之间
  let valOnRadian = Number(api.value(1));
  valOnRadian = Math.max(0, Math.min(100, valOnRadian));

  const coords = api.coord([api.value(0), valOnRadian]);
  const polarEndRadian = coords[3];

  // 创建渐变色
  const gradient = new echarts.graphic.LinearGradient(0, 0, 1, 0, colorStops);

  return {
    type: "group" as const,
    children: [
      {
        type: "sector",
        shape: {
          cx: (params.coordSys as any).cx,
          cy: (params.coordSys as any).cy,
          r: _outerRadius,
          r0: _innerRadius,
          startAngle: 0,
          endAngle: -polarEndRadian,
          transition: "endAngle",
          enterFrom: { endAngle: 0 }
        },
        style: {
          fill: gradient
        }
      },
      {
        type: "polygon",
        shape: {
          points: makePionterPoints(params, polarEndRadian)
        },
        style: {
          fill: "#37a2da"
        },
        extra: {
          polarEndRadian: polarEndRadian,
          transition: "polarEndRadian",
          enterFrom: { polarEndRadian: 0 }
        },
        during: function (apiDuring) {
          apiDuring.setShape(
            "points",
            makePionterPoints(params, apiDuring.getExtra("polarEndRadian"))
          );
        }
      },
      {
        type: "circle",
        shape: {
          cx: (params.coordSys as any).cx,
          cy: (params.coordSys as any).cy,
          r: _insidePanelRadius
        },
        style: {
          fill: "#fff",
          shadowBlur: 25,
          shadowOffsetX: 0,
          shadowOffsetY: 0,
          shadowColor: "rgba(76,107,167,0.4)"
        }
      },
      {
        type: "text",
        extra: {
          valOnRadian: valOnRadian,
          transition: "valOnRadian",
          enterFrom: { valOnRadian: 0 }
        },
        style: {
          text: makeText(valOnRadian),
          fontSize: 32,
          fontWeight: 700,
          x: (params.coordSys as any).cx,
          y: (params.coordSys as any).cy,
          fill: "#37a2da",
          align: "center",
          verticalAlign: "middle",
          enterFrom: { opacity: 0 }
        },
        during: function (apiDuring) {
          apiDuring.setStyle(
            "text",
            makeText(apiDuring.getExtra("valOnRadian"))
          );
        }
      }
    ]
  };
}

function convertToPolarPoint(renderItemParams, radius, radian) {
  return [
    Math.cos(radian) * radius + renderItemParams.coordSys.cx,
    -Math.sin(radian) * radius + renderItemParams.coordSys.cy
  ];
}

function makePionterPoints(renderItemParams, polarEndRadian) {
  return [
    convertToPolarPoint(renderItemParams, _outerRadius, polarEndRadian),
    convertToPolarPoint(
      renderItemParams,
      _outerRadius,
      polarEndRadian + Math.PI * 0.03
    ),
    convertToPolarPoint(renderItemParams, _pointerInnerRadius, polarEndRadian)
  ];
}

function makeText(valOnRadian) {
  // 确保值在0-100之间
  valOnRadian = Math.max(0, Math.min(100, valOnRadian));
  return Math.round(valOnRadian) + "%";
}

const option: EChartsOption = {
  animationEasing: "quarticInOut",
  animationDuration: 1000,
  animationDurationUpdate: 1000,
  animationEasingUpdate: "quarticInOut",
  dataset: {
    source: [[1, Math.max(0, Math.min(100, props.value))]]
  },
  angleAxis: {
    type: "value",
    startAngle: 360,
    endAngle: 0,
    min: 0,
    max: 100,
    show: false
  },
  radiusAxis: {
    type: "value",
    show: false
  },
  polar: {},
  series: [
    {
      type: "custom",
      coordinateSystem: "polar",
      renderItem: renderItem
    }
  ]
};

function initChart() {
  if (chartRef.value) {
    chart = echarts.init(chartRef.value);
    chart.setOption(option);
  }
}

function updateChart() {
  if (chart) {
    const safeValue = Math.max(0, Math.min(100, props.value));
    chart.setOption({
      dataset: {
        source: [[1, safeValue]]
      }
    });
  }
}

function handleResize() {
  chart?.resize();
}

watch(
  () => props.value,
  newValue => {
    updateChart();
  }
);

onMounted(() => {
  initChart();
  window.addEventListener("resize", handleResize);
});

onBeforeUnmount(() => {
  window.removeEventListener("resize", handleResize);
  chart?.dispose();
});
</script>
