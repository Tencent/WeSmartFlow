/**
 * 认证状态管理
 *
 * 提供 token 存储、登录/登出、认证状态检查。
 * 全局单例，所有组件共享同一份状态。
 */

import { ref, computed } from "vue";

const TOKEN_KEY = "wesmartflow-token";
const USER_KEY = "wesmartflow-user";

// 全局响应式状态
const token = ref(localStorage.getItem(TOKEN_KEY) || "");
const user = ref(JSON.parse(localStorage.getItem(USER_KEY) || "null"));
// 全局用户档案（完整信息，由 /api/user 返回后填充）
const userProfile = ref(null);

const isAuthenticated = computed(() => !!token.value);
const userName = computed(
  () => userProfile.value?.name || user.value?.user_name || "",
);
const userId = computed(() => user.value?.user_id || "");

/**
 * 保存登录凭据
 */
function setAuth(loginResponse) {
  token.value = loginResponse.access_token;
  user.value = {
    user_id: loginResponse.user_id,
    user_name: loginResponse.user_name,
  };
  localStorage.setItem(TOKEN_KEY, token.value);
  localStorage.setItem(USER_KEY, JSON.stringify(user.value));
}

/**
 * 清除登录状态
 */
function clearAuth() {
  token.value = "";
  user.value = null;
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

/**
 * 更新全局用户档案（供 ProfileView 等修改昵称后同步）
 */
function setUserProfile(profile) {
  userProfile.value = profile;
}

/**
 * 获取当前 token（供 API 请求使用）
 */
function getToken() {
  return token.value;
}

export function useAuth() {
  return {
    token,
    user,
    userProfile,
    isAuthenticated,
    userName,
    userId,
    setAuth,
    clearAuth,
    getToken,
    setUserProfile,
  };
}
