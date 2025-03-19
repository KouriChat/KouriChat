<script setup lang="ts">
import avatar from "@/assets/introduce/avatar.png";
import { IconifyIconOffline } from "@/components/ReIcon";

// 导入需要的图标集
import GithubIcon from "@iconify-icons/ri/github-fill";
import StarIcon from "@iconify-icons/ri/star-fill";
import EyeIcon from "@iconify-icons/ri/eye-line";
import InfoIcon from "@iconify-icons/ri/information-line";
import GitBranchIcon from "@iconify-icons/ri/git-branch-line";

defineProps<{
  title?: string;
  stars?: number | string;
  watches?: number | string;
  issues?: number | string;
  githubUrl?: string;
  forkUrl?: string;
}>();
</script>

<template>
  <div class="intruduce-head-container">
    <div class="content-wrapper">
      <div class="intruduce-logo">
        <img :src="avatar" alt="项目图标" class="logo-image" />
      </div>
      <div class="intruduce-info">
        <div class="intruduce-title">
          <h1>{{ title || "KouriChat" }}</h1>
          <p>Dev by <a>KouriTeam</a></p>
        </div>
        <div class="intruduce-stats">
          <a :href="githubUrl" target="_blank" class="stat-item">
            <IconifyIconOffline :icon="GithubIcon" />
            <span>GitHub</span>
          </a>
          <div v-if="stars" class="stat-item">
            <IconifyIconOffline :icon="StarIcon" />
            <span>{{ stars }}</span>
          </div>
          <div v-if="watches" class="stat-item">
            <IconifyIconOffline :icon="EyeIcon" />
            <span>{{ watches }}</span>
          </div>
          <div v-if="issues" class="stat-item">
            <IconifyIconOffline :icon="InfoIcon" />
            <span>{{ issues }}</span>
          </div>
        </div>
      </div>
    </div>
    <div class="button-container">
      <div>
        <el-button
          type="primary"
          class="project-button"
          :href="githubUrl"
          target="_blank"
        >
          <IconifyIconOffline :icon="GithubIcon" class="button-icon" />
          <span>访问项目仓库</span>
        </el-button>
      </div>
      <div>
        <el-button
          type="default"
          class="project-button"
          :href="forkUrl"
          target="_blank"
        >
          <IconifyIconOffline :icon="GitBranchIcon" class="button-icon" />
          <span>Fork项目仓库</span>
        </el-button>
      </div>
    </div>
  </div>
</template>

<style lang="css" scoped>
.intruduce-head-container {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
}

.content-wrapper {
  display: flex;
  align-items: center;
  width: 100%;
}

.button-container {
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.intruduce-logo {
  margin-right: 24px;
}

.logo-image {
  width: 80px;
  height: 80px;
  object-fit: cover;
  border-radius: 8px;
}

.intruduce-info {
  display: flex;
  flex: 1;
  flex-direction: column;
  justify-content: center;
}

.intruduce-title {
  margin-bottom: 8px;
}

.intruduce-title h1 {
  margin: 0;
  font-size: 24px;
  font-weight: bold;
  color: var(--el-text-color-primary);
}

.intruduce-title p {
  margin: 4px 0 0;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}

.intruduce-stats {
  display: flex;
  gap: 16px;
  align-items: center;
}

.stat-item {
  display: flex;
  gap: 4px;
  align-items: center;
  font-size: 14px;
  color: var(--el-text-color-secondary);
  text-decoration: none;
}

.stat-item:hover {
  color: var(--el-color-primary);
}

.project-button {
  display: flex;
  gap: 8px;
  align-items: center;
  width: 200px;
  padding: 10px 20px;
  margin-right: 10px;
  margin-bottom: 10px;
  font-size: 16px;
  font-weight: bold;
}

.button-icon {
  margin-right: 10px;
  font-size: 24px;
}
</style>
