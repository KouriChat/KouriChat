<template>
  <el-card class="re-log-viewer" :style="{ width, height }">
    <template #header>
      <slot name="title">
        <span class="card-title">日志查看器</span>
      </slot>
    </template>

    <div class="controls">
      <el-row :gutter="10">
        <el-col :span="24">
          <el-input
            v-model="searchPattern"
            placeholder="输入正则表达式搜索"
            clearable
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
            <template #append>
              <el-button @click="search">搜索</el-button>
            </template>
          </el-input>
        </el-col>
      </el-row>

      <el-row :gutter="10" class="mt-2">
        <el-col :xs="24" :sm="8">
          <div class="filter-group">
            <span class="filter-label">
              <el-text size="large">日志级别:</el-text>
            </span>
            <el-checkbox-group v-model="selectedLevels">
              <el-checkbox label="debug" size="large" border>Debug</el-checkbox>
              <el-checkbox label="info" size="large" border>Info</el-checkbox>
              <el-checkbox label="warning" size="large" border
                >Warning</el-checkbox
              >
              <el-checkbox label="error" size="large" border>Error</el-checkbox>
            </el-checkbox-group>
          </div>
        </el-col>

        <el-col :xs="24" :sm="16">
          <div class="filter-group">
            <span class="filter-label">
              <el-text size="large"> 时间范围: </el-text>
            </span>
            <el-time-picker
              v-model="startTime"
              placeholder="开始时间"
              format="HH:mm:ss"
              value-format="HH:mm:ss"
              clearable
              class="time-picker"
            />
            <span class="divider-text">
              <el-text size="large">至</el-text>
            </span>
            <el-time-picker
              v-model="endTime"
              placeholder="结束时间"
              format="HH:mm:ss"
              value-format="HH:mm:ss"
              clearable
              class="time-picker"
            />
          </div>
        </el-col>
      </el-row>

      <el-row :gutter="10" class="mt-2">
        <el-col :span="24">
          <div class="filter-actions">
            <el-switch
              v-model="showLineNumbers"
              class="mr-2"
              inline-prompt
              active-text="行号开"
              inactive-text="行号关"
              size="large"
            />
            <el-switch
              v-model="autoScroll"
              class="mr-2"
              inline-prompt
              active-text="自动滚动"
              inactive-text="手动滚动"
              size="large"
            />
            <el-switch
              v-model="searchExactMatch"
              class="mr-2"
              inline-prompt
              active-text="显示搜索结果"
              inactive-text="显示全部内容"
              size="large"
            />
            <el-button type="danger" class="ml-auto" @click="clearLogs"
              >清空日志</el-button
            >
          </div>
        </el-col>
      </el-row>
    </div>

    <div ref="logContainer" class="log-container">
      <div v-for="(line, index) in filteredLogs" :key="index" class="log-line">
        <span v-if="showLineNumbers" class="line-number">{{ index + 1 }}</span>
        <span class="log-content" v-html="highlightLog(line)" />
      </div>
      <div v-if="filteredLogs.length === 0" class="empty-log">
        <el-empty description="暂无日志" />
      </div>
    </div>

    <div class="actions">
      <el-button
        v-if="!autoScroll"
        circle
        type="primary"
        @click="scrollToBottom"
        class="scroll-bottom-btn"
      >
        <el-icon><i-ep-bottom /></el-icon>
      </el-button>
    </div>
  </el-card>
</template>

<script lang="ts" setup>
import { ref, computed, watch, nextTick, onMounted } from "vue";
import { ElMessage } from "element-plus";

const props = defineProps({
  // 日志数据
  logs: {
    type: Array<string>,
    default: () => []
  },
  // 是否自动滚动到底部
  defaultAutoScroll: {
    type: Boolean,
    default: true
  },
  // 宽度
  width: {
    type: String,
    default: "100%"
  },
  // 高度
  height: {
    type: String,
    default: "400px"
  },
  // 默认是否显示行号
  defaultShowLineNumbers: {
    type: Boolean,
    default: true
  }
});

// 状态
const logContainer = ref<HTMLElement | null>(null);
const searchPattern = ref("");
const selectedLevels = ref(["debug", "info", "warning", "error"]);
const showLineNumbers = ref(props.defaultShowLineNumbers);
const autoScroll = ref(props.defaultAutoScroll);
const searchResults = ref<number[]>([]);
const currentSearchIndex = ref(-1);
const startTime = ref("");
const endTime = ref("");
const searchExactMatch = ref(false);

// 解析日志格式：[Level][Time]Message
const parseLog = (log: string) => {
  const regex = /\[(Debug|Info|Warning|Error)\]\[([0-9:]+)\](.*)/i;
  const match = log.match(regex);

  if (match) {
    return {
      level: match[1].toLowerCase(),
      time: match[2],
      message: match[3]
    };
  }

  return { level: "debug", time: "", message: log };
};

// 过滤日志基于级别和时间
const filteredLogs = computed(() => {
  return props.logs.filter(log => {
    const parsedLog = parseLog(log);
    let shouldInclude = true;

    if (!selectedLevels.value.includes(parsedLog.level)) {
      return false;
    }

    if (startTime.value && endTime.value && parsedLog.time) {
      if (parsedLog.time < startTime.value || parsedLog.time > endTime.value) {
        return false;
      }
    } else if (startTime.value && parsedLog.time) {
      if (parsedLog.time < startTime.value) {
        return false;
      }
    } else if (endTime.value && parsedLog.time) {
      if (parsedLog.time > endTime.value) {
        return false;
      }
    }

    if (searchPattern.value && searchExactMatch.value) {
      try {
        const regex = new RegExp(searchPattern.value, "i");
        shouldInclude = regex.test(log);
      } catch (e) {
        shouldInclude = true;
      }
    }

    return shouldInclude;
  });
});

// 高亮日志
const highlightLog = (log: string): string => {
  const parsedLog = parseLog(log);

  let result = log
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

  const levelClass = parsedLog.level;
  result = `<span class="${levelClass}">${result}</span>`;

  if (searchPattern.value) {
    try {
      const regex = new RegExp(`(${searchPattern.value})`, "gi");
      result = result.replace(
        regex,
        '<span class="search-highlight">$1</span>'
      );
    } catch (e) {}
  }

  return result;
};

// 搜索
const search = () => {
  if (!searchPattern.value) {
    searchResults.value = [];
    currentSearchIndex.value = -1;

    if (searchExactMatch.value) {
      ElMessage.info("已清除搜索条件，显示全部日志");
    }
    return;
  }

  try {
    if (searchExactMatch.value) {
      return;
    }

    const regex = new RegExp(searchPattern.value, "i");
    searchResults.value = filteredLogs.value
      .map((log, index) => (regex.test(log) ? index : -1))
      .filter(index => index !== -1);

    currentSearchIndex.value = searchResults.value.length > 0 ? 0 : -1;

    if (searchResults.value.length > 0) {
      scrollToSearchResult();
      ElMessage.success(`找到 ${searchResults.value.length} 个匹配结果`);
    } else {
      ElMessage.warning("未找到匹配结果");
    }
  } catch (e) {
    ElMessage.error("无效的正则表达式");
  }
};

// 滚动到搜索结果
const scrollToSearchResult = () => {
  if (currentSearchIndex.value === -1 || !logContainer.value) return;

  const targetIndex = searchResults.value[currentSearchIndex.value];
  const logLines = logContainer.value.querySelectorAll(".log-line");

  if (targetIndex >= 0 && targetIndex < logLines.length) {
    logLines[targetIndex].scrollIntoView({
      behavior: "smooth",
      block: "center"
    });
  }
};

// 清空日志
const clearLogs = () => {
  emit("clear");
  resetFilters();
};

// 重置筛选条件
const resetFilters = () => {
  selectedLevels.value = ["debug", "info", "warning", "error"];
  startTime.value = "";
  endTime.value = "";
  searchPattern.value = "";
  searchExactMatch.value = false;
};

// 滚动到底部
const scrollToBottom = () => {
  if (logContainer.value) {
    logContainer.value.scrollTop = logContainer.value.scrollHeight;
  }
};

// 监听日志变化，自动滚动到底部
watch(
  () => props.logs.length,
  async () => {
    if (autoScroll.value) {
      await nextTick();
      scrollToBottom();
    }
  }
);

// 监听搜索模式的变化
watch([selectedLevels, startTime, endTime], () => {
  if (filteredLogs.value.length === 0) {
    ElMessage.warning("筛选后没有符合条件的日志");
  }
});

watch(searchExactMatch, () => {
  if (searchPattern.value) {
    search();
  }
});

// 事件
const emit = defineEmits(["clear"]);

// 挂载后初始化
onMounted(() => {
  if (autoScroll.value) {
    scrollToBottom();
  }
});
</script>

<style lang="scss" scoped>
.re-log-viewer {
  display: flex;
  flex-direction: column;
  height: 100%;

  :deep(.el-card__header) {
    padding: 12px 20px;
    border-bottom: 1px solid var(--el-border-color-light);
  }

  :deep(.el-card__body) {
    flex: 1;
    padding: 0;
    height: calc(100% - 55px);
    display: flex;
    flex-direction: column;
  }

  .card-title {
    font-size: 16px;
    font-weight: 500;
  }

  .controls {
    padding: 16px;
    border-bottom: 1px solid var(--el-border-color-light);
    background-color: var(--el-bg-color-overlay);
  }

  .filter-group {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 8px;
  }

  .filter-label {
    font-weight: 500;
    font-size: 14px;
    color: var(--el-text-color-regular);
  }

  .divider-text {
    font-weight: 500;
    font-size: 14px;
    color: var(--el-text-color-regular);
  }

  .filter-actions {
    display: flex;
    align-items: center;
    gap: 16px;
  }

  .time-picker {
    width: 140px;
  }

  .log-container {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    font-family: var(--el-font-family);
    font-size: 14px;
    line-height: 1.5;
    background-color: var(--el-bg-color-page);
  }

  .log-line {
    display: flex;
    white-space: pre-wrap;
    margin-bottom: 4px;
  }

  .line-number {
    min-width: 40px;
    color: var(--el-text-color-secondary);
    text-align: right;
    padding-right: 12px;
    user-select: none;
  }

  .log-content {
    flex: 1;
    word-break: break-all;
  }

  .error {
    color: var(--el-color-danger);
  }

  .warning {
    color: var(--el-color-warning);
  }

  .info {
    color: var(--el-color-primary);
  }

  .debug {
    color: var(--el-text-color-secondary);
  }

  .search-highlight {
    background-color: var(--el-color-warning);
    color: var(--el-color-white);
    border-radius: 2px;
    padding: 0 2px;
  }

  .empty-log {
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
  }

  .actions {
    position: absolute;
    right: 20px;
    bottom: 20px;
    z-index: 10;
  }

  .scroll-bottom-btn {
    box-shadow: var(--el-box-shadow-light);
  }

  .mt-2 {
    margin-top: 8px;
  }

  .mr-2 {
    margin-right: 8px;
  }

  .ml-auto {
    margin-left: auto;
  }
}
</style>
