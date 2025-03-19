<script setup lang="ts">
import CpuGauge from "./gauges/cpu.gauge.vue";
import MemoryGauge from "./gauges/memory.gauge.vue";
import NetworkGauge from "./gauges/network.gauge.vue";
import DiskGauge from "./gauges/disk.gauge.vue";
import IntruduceHead from "./intruduce/intruduce.head.vue";
import IntruduceBody from "./intruduce/intruduce.body.vue";
import { Cpu, Coin, Connection, DataAnalysis } from "@element-plus/icons-vue";
import { ref, onMounted, onBeforeUnmount } from "vue";
import { useApiStore } from "@/store/modules/api.js";
import { ElMessage } from "element-plus";
import { getToken } from "@/utils/auth";
import { useRouter } from "vue-router";

defineOptions({
  name: "Welcome"
});

// 定义响应式数据
const cpuUsage = ref(50);
const memoryData = ref({
  used: 29,
  total: 63.92
});
const networkData = ref({
  download: 280,
  upload: 50
});
const diskData = ref({
  used: 29,
  total: 63.92
});

// 定义计时器引用
let timer: number | null = null;

const apiStore = useApiStore();
const router = useRouter();

// 更新数据的函数
const updateData = async () => {
  try {
    const res = await apiStore.get_sys_info();
    if (res.status === "success") {
      // CPU使用率
      cpuUsage.value = res.data.cpu_percent;

      // 内存数据
      memoryData.value = {
        used: res.data.memory.used,
        total: res.data.memory.total
      };

      // 网络数据
      networkData.value = {
        download: res.data.network.download,
        upload: res.data.network.upload
      };

      // 磁盘数据
      diskData.value = {
        used: res.data.disk.used,
        total: res.data.disk.total
      };
    }
  } catch (error) {
    console.error("错误详情:", error);
    if (
      error.message === "未登录或token已失效" ||
      error.response?.status === 401
    ) {
      ElMessage.error("登录已过期，请重新登录");
      router.push("/login");
    } else {
      ElMessage.error("获取系统信息失败");
    }
    if (timer) {
      window.clearInterval(timer);
      timer = null;
    }
  }
};

// 组件挂载时启动计时器
onMounted(async () => {
  // 立即执行一次
  await updateData();
  // 设置定时器，每5秒执行一次
  timer = window.setInterval(updateData, 2000);
});

// 组件卸载前清除计时器
onBeforeUnmount(() => {
  if (timer) {
    window.clearInterval(timer);
    timer = null;
  }
});
</script>

<template>
  <div>
    <el-row>
      <el-col :span="24">
        <el-card>
          <template #header>
            <div>
              <intruduce-head
                title="KouriChat"
                stars="100"
                watches="100"
                issues="100"
              />
            </div>
          </template>
          <intruduce-body />
        </el-card>
      </el-col>
    </el-row>
    <el-row :gutter="20">
      <el-col :span="6">
        <el-card class="gauge-card">
          <template #header>
            <div class="card-header">
              <div class="card-title">
                <el-icon class="card-icon"><Cpu /></el-icon>
                CPU 占用率
              </div>
            </div>
          </template>
          <div class="gauge-container">
            <cpu-gauge :value="cpuUsage" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="gauge-card">
          <template #header>
            <div class="card-header">
              <div class="card-title">
                <el-icon class="card-icon"><Coin /></el-icon>
                内存占用率
              </div>
            </div>
          </template>
          <div class="gauge-container">
            <memory-gauge :used="memoryData.used" :total="memoryData.total" />
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="gauge-card">
          <template #header>
            <div class="card-title">
              <el-icon class="card-icon"><Connection /></el-icon>
              网络使用情况
            </div>
          </template>
          <div class="gauge-container">
            <network-gauge
              :download="networkData.download"
              :upload="networkData.upload"
            />
          </div>
        </el-card>
      </el-col>
      <el-col :span="6">
        <el-card class="gauge-card">
          <template #header>
            <div class="card-title">
              <el-icon class="card-icon"><DataAnalysis /></el-icon>
              磁盘使用情况
            </div>
          </template>
          <div class="gauge-container">
            <disk-gauge :used="diskData.used" :total="diskData.total" />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style lang="css" scoped>
.el-row {
  margin-bottom: 15px;
}

.gauge-card {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.gauge-card :deep(.el-card__body) {
  display: flex;
  flex: 1;
  align-items: center;
  justify-content: center;
  padding: 10px;
}

.gauge-container {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
}

.card-title {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  font-weight: bold;
  text-align: center;
}

.card-icon {
  font-size: 20px;
}
</style>
