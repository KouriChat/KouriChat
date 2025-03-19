<template>
  <div class="log-viewer-demo">
    <el-card class="box-card">
      <template #header>
        <div class="card-header">
          <span>日志查看器示例</span>
          <div class="operations">
            <el-button type="primary" @click="addRandomLog"
              >添加随机日志</el-button
            >
            <el-button type="success" @click="addInfoLog"
              >添加 Info 日志</el-button
            >
            <el-button type="warning" @click="addWarningLog"
              >添加 Warning 日志</el-button
            >
            <el-button type="danger" @click="addErrorLog"
              >添加 Error 日志</el-button
            >
          </div>
        </div>
      </template>

      <ReLogViewer
        :logs="logs"
        :default-auto-scroll="true"
        :default-show-line-numbers="true"
        width="100%"
        height="500px"
        @clear="clearLogs"
      />

      <div class="log-format-info">
        <h4>日志格式说明</h4>
        <p>标准格式: [Level][Time]Message</p>
        <p>示例: [Debug][18:31:47]正在关闭监听线程...</p>
      </div>
    </el-card>
  </div>
</template>

<script lang="ts" setup>
import { ref } from "vue";
import ReLogViewer from "@/components/ReLogViewer";

// 获取当前时间的函数
const getCurrentTime = () => {
  const now = new Date();
  const hours = now.getHours().toString().padStart(2, '0');
  const minutes = now.getMinutes().toString().padStart(2, '0');
  const seconds = now.getSeconds().toString().padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
};

// 示例日志数据 - 使用新格式
const logs = ref<string[]>([
  `[Debug][${getCurrentTime()}]应用程序启动中...`,
  `[Info][${getCurrentTime()}]连接到服务器成功`,
  `[Debug][${getCurrentTime()}]初始化核心模块`,
  `[Info][${getCurrentTime()}]用户登录: admin`,
  `[Warning][${getCurrentTime()}]磁盘空间不足，剩余 10%`,
  `[Error][${getCurrentTime()}]无法访问数据库: 连接超时`,
  `[Debug][${getCurrentTime()}]正在加载配置文件`,
  `[Info][${getCurrentTime()}]配置加载完成，初始化服务...`,
  `[Debug][${getCurrentTime()}]初始化完成`,
  `[Info][${getCurrentTime()}]应用程序准备就绪`,
  // 添加一些带特定时间的示例（用于时间过滤测试）
  "[Debug][08:00:00]系统启动时间 - 早晨8点",
  "[Info][12:00:00]系统正常运行 - 中午12点",
  "[Warning][18:00:00]系统负载增高 - 晚上6点",
  "[Error][23:59:59]系统异常 - 午夜"
]);

// 添加随机日志
const addRandomLog = () => {
  const levels = ["Debug", "Info", "Warning", "Error"];
  const level = levels[Math.floor(Math.random() * levels.length)];
  const time = getCurrentTime();

  const messages = [
    "处理请求中...",
    "用户操作执行成功",
    "网络延迟较高",
    "数据验证失败",
    "正在同步数据",
    "文件读取成功",
    "缓存更新",
    "服务器响应时间较长",
    "内存使用率增高",
    "线程池扩展"
  ];
  const message = messages[Math.floor(Math.random() * messages.length)];
  logs.value.push(`[${level}][${time}]${message}`);
};

// 添加 Info 日志
const addInfoLog = () => {
  const time = getCurrentTime();
  logs.value.push(`[Info][${time}]这是一条信息日志`);
};

// 添加 Warning 日志
const addWarningLog = () => {
  const time = getCurrentTime();
  logs.value.push(`[Warning][${time}]这是一条警告日志`);
};

// 添加 Error 日志
const addErrorLog = () => {
  const time = getCurrentTime();
  logs.value.push(`[Error][${time}]这是一条错误日志`);
};

// 清空日志
const clearLogs = () => {
  logs.value = [];
};
</script>

<style lang="scss" scoped>
.log-viewer-demo {
  padding: 20px;

  .card-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
  }

  .operations {
    display: flex;
    gap: 10px;
  }

  .log-format-info {
    margin-top: 20px;
    padding: 10px;
    background-color: var(--el-bg-color-page);
    border-radius: 4px;

    h4 {
      margin-top: 0;
      margin-bottom: 10px;
      color: var(--el-text-color-primary);
    }

    p {
      margin: 5px 0;
      color: var(--el-text-color-regular);
      font-family: monospace;
    }
  }
}
</style>
