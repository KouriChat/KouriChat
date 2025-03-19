<script setup lang="ts">
import CpuGauge from "./gauges/cpu.gauge.vue";
import MemoryGauge from "./gauges/memory.gauge.vue";
import NetworkGauge from "./gauges/network.gauge.vue";
import DiskGauge from "./gauges/disk.gauge.vue";
import IntruduceHead from "./intruduce/intruduce.head.vue";
import IntruduceBody from "./intruduce/intruduce.body.vue";
import { Cpu, Coin, Connection, DataAnalysis } from "@element-plus/icons-vue";

defineOptions({
  name: "Welcome"
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
            <cpu-gauge :value="50" />
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
            <memory-gauge :used="29" :total="63.92" />
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
            <network-gauge :download="280" :upload="50" />
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
            <disk-gauge :used="29" :total="63.92" />
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
