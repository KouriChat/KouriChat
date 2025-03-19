<script setup lang="ts">
import Motion from "./utils/motion";
import { useRouter } from "vue-router";
import { message } from "@/utils/message";
import { loginRules } from "./utils/rule";
import { useNav } from "@/layout/hooks/useNav";
import type { FormInstance } from "element-plus";
import { useLayout } from "@/layout/hooks/useLayout";
import { useUserStoreHook } from "@/store/modules/user";
import { initRouter, getTopMenu } from "@/router/utils";
import { bg, avatar } from "./utils/static";
import { useRenderIcon } from "@/components/ReIcon/src/hooks";
import { ref, reactive, onMounted, onBeforeUnmount } from "vue";
import { useDataThemeChange } from "@/layout/hooks/useDataThemeChange";

import dayIcon from "@/assets/svg/day.svg?component";
import darkIcon from "@/assets/svg/dark.svg?component";
import Lock from "@iconify-icons/ri/lock-fill";

defineOptions({
  name: "Login"
});
const router = useRouter();
const loading = ref(false);
const ruleFormRef = ref<FormInstance>();

const { initStorage } = useLayout();
initStorage();

const { dataTheme, overallStyle, dataThemeChange } = useDataThemeChange();
dataThemeChange(overallStyle.value);
const { title } = useNav();

const ruleForm = reactive({
  password: "admin123",
  remember: false
});

const avatarRef = ref(null);
const isPressed = ref(false);

const onLogin = async (formEl: FormInstance | undefined) => {
  if (!formEl) return;
  await formEl.validate((valid, fields) => {
    if (valid) {
      loading.value = true;
      useUserStoreHook()
        .loginByUsername({ username: "admin", password: ruleForm.password })
        .then(res => {
          if (res.success) {
            return initRouter().then(() => {
              router.push(getTopMenu(true).path).then(() => {
                message("登录成功", { type: "success" });
              });
            });
          } else {
            message("登录失败", { type: "error" });
          }
        })
        .finally(() => (loading.value = false));
    }
  });
};

function onkeypress({ code }: KeyboardEvent) {
  if (["Enter", "NumpadEnter"].includes(code)) {
    onLogin(ruleFormRef.value);
  }
}

const handleMouseMove = e => {
  if (!avatarRef.value) return;

  const rect = avatarRef.value.getBoundingClientRect();
  const centerX = rect.left + rect.width / 2;
  const centerY = rect.top + rect.height / 2;

  const mouseX = e.clientX;
  const mouseY = e.clientY;

  const rotateX = ((mouseY - centerY) / (rect.height / 2)) * 15;
  const rotateY = ((mouseX - centerX) / (rect.width / 2)) * 15;

  const multiplier = isPressed.value ? 2 : 1;

  avatarRef.value.style.transform = `
    perspective(1000px)
    rotateX(${-rotateX * multiplier}deg)
    rotateY(${rotateY * multiplier}deg)
  `;
};

const handleMouseLeave = () => {
  if (!avatarRef.value) return;
  avatarRef.value.style.transform = "perspective(1000px) rotateX(0) rotateY(0)";
};

const handleMouseDown = () => {
  isPressed.value = true;
};

const handleMouseUp = () => {
  isPressed.value = false;
};

onMounted(() => {
  window.document.addEventListener("keypress", onkeypress);
});

onBeforeUnmount(() => {
  window.document.removeEventListener("keypress", onkeypress);
});
</script>

<template>
  <div class="select-none">
    <img :src="bg" class="wave" />
    <div class="flex-c absolute right-5 top-3">
      <el-switch
        v-model="dataTheme"
        inline-prompt
        :active-icon="dayIcon"
        :inactive-icon="darkIcon"
        @change="dataThemeChange"
      />
    </div>
    <div class="login-container">
      <div class="login-box">
        <el-card class="glass-card">
          <div class="login-form">
            <img
              ref="avatarRef"
              :src="avatar"
              class="avatar"
              @mousemove="handleMouseMove"
              @mouseleave="handleMouseLeave"
              @mousedown="handleMouseDown"
              @mouseup="handleMouseUp"
            />
            <Motion>
              <h2 class="outline-none">{{ title }}</h2>
            </Motion>

            <el-form
              ref="ruleFormRef"
              :model="ruleForm"
              :rules="loginRules"
              size="large"
            >
              <Motion :delay="150">
                <el-form-item prop="password">
                  <el-input
                    v-model="ruleForm.password"
                    clearable
                    show-password
                    placeholder="密码"
                    :prefix-icon="useRenderIcon(Lock)"
                  />
                </el-form-item>
              </Motion>

              <Motion :delay="200">
                <div class="remember-me">
                  <el-checkbox
                    v-model="ruleForm.remember"
                    label="记住我"
                    size="large"
                    border
                  />
                </div>
              </Motion>

              <Motion :delay="250">
                <el-button
                  class="w-full mt-4 login-button"
                  size="default"
                  type="primary"
                  :loading="loading"
                  @click="onLogin(ruleFormRef)"
                >
                  登录
                </el-button>
              </Motion>
            </el-form>
          </div>
        </el-card>
      </div>
    </div>
  </div>
</template>

<style scoped>
@import url("@/style/login.css");

.wave {
  position: fixed;
  top: 0;
  left: 0;
  z-index: -1;
  width: 100vw;
  height: 100vh;
  object-fit: cover;
}

.login-container {
  position: relative;
  z-index: 1;
}
</style>

<style lang="scss" scoped>
:deep(.el-input-group__append, .el-input-group__prepend) {
  padding: 0;
}

.el-button {
  width: 100%;
  color: #fff;
  background-color: #000;
  transition:
    background-color 0.3s,
    color 0.3s;
}

.glass-card {
  width: 550px;
  height: auto;
  min-height: 460px;
  overflow: hidden;
  background: rgb(124 124 124 / 60%) !important;
  backdrop-filter: blur(12px) saturate(160%);
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 24px !important;
  box-shadow: 4px 8px 16px rgb(0 0 0 / 15%);
}

.glass-card :deep(.el-card__body) {
  padding: 40px;
}

.login-form {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
}

.login-form :deep(.el-form) {
  width: 100%;
}

.login-form :deep(.el-form-item) {
  width: 100%;
}

.login-form :deep(.el-input) {
  width: 100%;
  transition: none;
}

.login-form :deep(.el-input__wrapper) {
  width: 100%;
  transition: box-shadow 0.3s;
}

.remember-me {
  display: flex;
  justify-content: flex-start;
  width: 100%;
  margin: 15px 0;
}

.remember-me :deep(.el-checkbox__label) {
  font-size: 16px;
  font-weight: 600;
  color: #fff;
}

.remember-me :deep(.el-checkbox__inner) {
  width: 18px;
  height: 18px;
}

.remember-me :deep(.el-checkbox) {
  display: flex;
  align-items: center;
}

.login-button {
  height: 45px;
  font-size: 16px;
  transition: all 0.3s ease;
}

.login-button:hover {
  box-shadow: 0 0 15px rgb(64 158 255 / 60%);
  transform: translateY(-2px);
}
</style>
