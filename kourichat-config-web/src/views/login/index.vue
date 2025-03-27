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
      useUserStoreHook().SET_ISREMEMBERED(ruleForm.remember);
      useUserStoreHook()
        .login({ password: ruleForm.password })
        .then(res => {
          if (res.status === "success") {
            message("登录成功", { type: "success" });
            setTimeout(() => {
              initRouter();
              const toPath = router.currentRoute.value.query?.redirect || "/";
              router.push(toPath as string);
            }, 100);
          } else {
            message(res.message || "登录失败", { type: "error" });
          }
        })
        .catch(error => {
          console.error("登录错误:", error);
          message("登录失败", { type: "error" });
        })
        .finally(() => {
          loading.value = false;
        });
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

// 蝴蝶控制函数
const handleButterfliesMove = (e: MouseEvent): void => {
  const butterflies: NodeListOf<HTMLElement> = document.querySelectorAll('.butter');
  const mouseX: number = e.clientX;
  const mouseY: number = e.clientY;

  butterflies.forEach((butterfly: HTMLElement) => {
    const rect: DOMRect = butterfly.getBoundingClientRect();
    const centerX: number = rect.left + rect.width / 2;
    const centerY: number = rect.top + rect.height / 2;

    const moveX: number = (mouseX - centerX) * 0.02;
    const moveY: number = (mouseY - centerY) * 0.02;

    butterfly.style.transform = `translate(${moveX}px, ${moveY}px)`;
  });
};



onMounted(() => {
  window.document.addEventListener("keypress", onkeypress);
  window.addEventListener('mousemove', handleButterfliesMove);
});

onBeforeUnmount(() => {
  window.document.removeEventListener("keypress", onkeypress);
  window.removeEventListener('mousemove', handleButterfliesMove);
});
</script>

<template>
  <div class="select-none">
    <img :src="bg" class="wave" />
    <div class="flex-c absolute right-5 top-3">
      <el-switch v-model="dataTheme" inline-prompt :active-icon="dayIcon" :inactive-icon="darkIcon"
        @change="dataThemeChange" />
    </div>
    <div class="login-container">
      <div class="login-box">
        <el-card class="glass-card">
          <div class="login-form">
            <img ref="avatarRef" :src="avatar" class="avatar" @mousemove="handleMouseMove"
              @mouseleave="handleMouseLeave" @mousedown="handleMouseDown" @mouseup="handleMouseUp" />
            <Motion>
              <h2 class="outline-none">{{ title }}</h2>
            </Motion>

            <el-form ref="ruleFormRef" :model="ruleForm" :rules="loginRules" size="large">
              <Motion :delay="150">
                <el-form-item prop="password">
                  <el-input v-model="ruleForm.password" clearable show-password placeholder="密码"
                    :prefix-icon="useRenderIcon(Lock)" />
                </el-form-item>
              </Motion>

              <Motion :delay="200">
                <div class="remember-me">
                  <el-checkbox v-model="ruleForm.remember" label="记住我" size="large" />
                </div>
              </Motion>

              <Motion :delay="250">
                <el-button class="w-full mt-4 login-button" size="default" type="primary" :loading="loading"
                  @click="onLogin(ruleFormRef)">
                  登录
                </el-button>
              </Motion>
            </el-form>
          </div>
        </el-card>
      </div>

      <div class="butterfly">
        <img src="@/assets/login/img/1.png" class="bu1 butter" />
        <img src="@/assets/login/img/2.png" class="bu2 butter" />
        <img src="@/assets/login/img/3.png" class="bu3 butter" />
        <img src="@/assets/login/img/4.png" class="bu4 butter" />
        <img src="@/assets/login/img/5.png" class="bu5 butter" />
      </div>

    </div>
  </div>
</template>


<style lang="scss" scoped>
@import url("@/style/login.css");

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
  width: 600px;
  height: auto;
  min-height: 460px;
  overflow: hidden;
  background: url('@/assets/login/card.png') !important;
  backdrop-filter: blur(12px) saturate(160%);
  border: 1px solid rgb(255 255 255 / 10%);
  border-radius: 24px !important;
  box-shadow: 4px 8px 16px rgb(0 0 0 / 15%);
  transform: translateY(-20%)
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

  &.is-checked {
    .el-checkbox__input.is-checked .el-checkbox__inner {
      background-color: #ec8302 !important;
      border-color: #ec8302 !important;
    }
  }

  .el-checkbox__inner {
    border-color: #ec8302 !important;

    &:hover {
      border-color: #ec8302 !important;
    }
  }
}

.login-button {
  height: 45px;
  font-size: 16px;
  transition: all 0.3s ease;
  background: url('@/assets/login/button.png') !important;
  border: rgb(236 170 85 / 100%)
}

.login-button:hover {
  box-shadow: 0 0 15px rgba(236, 131, 2, 0.6);
  transform: translateY(-2px);
}

.butterfly {
  position: absolute;
  right: 0;
  bottom: 0;
  width: 30%;
  height: 60vh;

  .butter {
    position: absolute;
    background-size: cover;
    width: 2vw;  /* 改用 vw 单位，2.5vw 约等于在1920px宽度下的40px */
    height: 2vw; /* 保持宽高相等，使用相同的 vw 值 */
    min-width: 25px;  /* 设置最小尺寸，防止太小 */
    min-height: 25px; /* 设置最小尺寸，防止太小 */
    transition: transform 0.3s ease;
  }

  .bu1 {
    left: 15%;
    top: 60%;
  }
  .bu2 {
    left: 88%;
    top: 50%;
  }
  .bu3 {
    left: 48%;
    top: 38%;
  }
  .bu4{
    left: 93%;
    top: 30%;
  }
  .bu5{
    left: 94%;
    top: 5%;
  }
}
</style>
