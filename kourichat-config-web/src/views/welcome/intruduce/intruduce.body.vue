<script setup lang="ts">
import {
  Check,
  QuestionFilled,
  Document,
  Connection,
  SetUp,
  Download
} from "@element-plus/icons-vue";

const toPath = (path: string) => {
  window.open(path, "_blank");
};

// 使用在线图标代替本地图标集
</script>

<template>
  <div class="intruduce-body-container">
    <!-- 项目介绍部分 -->
    <div class="intruduce-info-container">
      <h2 class="section-title">项目介绍</h2>
      <div class="project-description">
        <p>
          KouriChat
          是一个基于大语言模型的情感陪伴系统，支持微信机器人接入，提供沉浸式角色扮演和多轮对话体验。系统采用
          DeepSeek 等先进的 LLM 模型，通过精心设计的提示词和上下文管理，让 AI
          能够模拟更加自然、真实的情感互动。推荐使用 DeepSeek V3
          模型以获得最佳体验。
        </p>

        <h3 class="feature-title">主要特性:</h3>
        <ul class="feature-list">
          <li>
            <el-icon class="feature-icon"><Check /></el-icon>
            支持微信机器人接入
          </li>
          <li>
            <el-icon class="feature-icon"><Check /></el-icon>
            提供多种 AI 模型选择
          </li>
          <li>
            <el-icon class="feature-icon"><Check /></el-icon>
            支持图片识别和生成
          </li>
          <li>
            <el-icon class="feature-icon"><Check /></el-icon>
            自定义角色和人设
          </li>
          <li>
            <el-icon class="feature-icon"><Check /></el-icon>
            情感化对话和记忆系统
          </li>
        </ul>

        <div class="tags-container">
          <div class="tag tag-blue">WeChat</div>
          <div class="tag tag-green">QQBot</div>
          <div class="tag tag-purple">LLM</div>
          <div class="tag tag-orange">AI 情感陪伴</div>
          <div class="tag tag-cyan">Python</div>
          <div class="tag tag-red">DeepSeek</div>
          <div class="tag tag-blue">角色扮演</div>
          <div class="tag tag-green">多轮对话</div>
        </div>
      </div>
    </div>

    <!-- 快速链接部分 -->
    <div class="quick-links-container">
      <h2 class="section-title">快速链接</h2>
      <ul class="quick-links-list">
        <li class="quick-link-item">
          <a href="#" class="quick-link">
            <el-icon class="link-icon"><QuestionFilled /></el-icon>
            <span
              @click="toPath('https://github.com/KouriChat/KouriChat/issues')"
              >问题反馈</span
            >
          </a>
        </li>
        <li class="quick-link-item">
          <a href="#" class="quick-link">
            <el-icon class="link-icon"><Document /></el-icon>
            <span @click="toPath('https://kourichat.com/docs/')">官方文档</span>
          </a>
        </li>
        <li class="quick-link-item">
          <a href="#" class="quick-link">
            <el-icon class="link-icon"><Connection /></el-icon>
            <span @click="toPath('https://api.kourichat.com/')">API 服务</span>
          </a>
        </li>
        <li class="quick-link-item">
          <a href="#" class="quick-link">
            <el-icon class="link-icon"><SetUp /></el-icon>
            <span
              @click="toPath('https://github.com/KouriChat/KouriChat/pulls')"
              >提交PR</span
            >
          </a>
        </li>
        <li class="quick-link-item">
          <a href="#" class="quick-link">
            <el-icon class="link-icon"><Download /></el-icon>
            <span
              @click="toPath('https://github.com/KouriChat/KouriChat/releases')"
              >下载发布版</span
            >
          </a>
        </li>
      </ul>
    </div>
  </div>
</template>

<style lang="css" scoped>
.intruduce-body-container {
  display: flex;
  gap: 40px;
  justify-content: space-between;
  margin-top: 20px;
}

.intruduce-info-container {
  flex: 3;
}

.quick-links-container {
  flex: 1;
}

.section-title {
  position: relative;
  padding-bottom: 10px;
  margin-bottom: 20px;
  font-size: 20px;
  font-weight: bold;
  color: var(--el-text-color-primary);
}

.section-title::after {
  position: absolute;
  bottom: 0;
  left: 0;
  width: 50px;
  height: 3px;
  content: "";
  background-color: var(--el-color-primary);
}

.project-description {
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.feature-title {
  margin: 20px 0 15px;
  font-size: 18px;
  font-weight: bold;
  color: var(--el-color-primary);
}

.feature-list {
  padding: 0;
  margin: 0 0 20px;
  list-style: none;
}

.feature-list li {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  font-size: 16px;
  font-weight: 500;
}

.feature-icon {
  margin-right: 10px;
  font-size: 20px;
  color: var(--el-color-success);
}

.tags-container {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  margin-top: 20px;
}

.tag {
  padding: 5px 12px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 4px;
}

.tag-blue {
  color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
}

.tag-green {
  color: var(--el-color-success);
  background-color: var(--el-color-success-light-9);
}

.tag-purple {
  color: #722ed1;
  background-color: #f5f0ff;
}

.tag-orange {
  color: var(--el-color-warning);
  background-color: var(--el-color-warning-light-9);
}

.tag-red {
  color: var(--el-color-danger);
  background-color: var(--el-color-danger-light-9);
}

.tag-cyan {
  color: #13c2c2;
  background-color: #e6fffb;
}

.quick-links-list {
  padding: 0;
  margin: 0;
  list-style: none;
}

.quick-link-item {
  margin-bottom: 15px;
}

.quick-link {
  display: flex;
  align-items: center;
  padding: 10px;
  color: var(--el-text-color-primary);
  text-decoration: none;
  border-radius: 4px;
  transition: all 0.3s ease;
}

.quick-link:hover {
  color: var(--el-color-primary);
  background-color: var(--el-color-primary-light-9);
  transform: translateX(5px);
}

.link-icon {
  margin-right: 10px;
  font-size: 20px;
}
</style>
