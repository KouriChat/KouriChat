import { api, authUsername } from "../api";

/** 管理员身份辅助：JWT `sub` 显示名 + 登出。 */
export function useAuth() {
  const username = authUsername();

  async function logout() {
    try {
      await api.authLogout();
    } catch {
      /* 登出失败也清本地 token，由 AuthGate 处理过期事件 */
    }
  }

  return { username, logout };
}
