<template>
  <div class="github-callback-page">
    <div class="callback-card">
      <div v-if="loading" class="callback-loading">
        <div class="spinner-lg"></div>
        <p class="callback-text">正在通过 GitHub 登录...</p>
      </div>
      <div v-else-if="errorMsg" class="callback-error">
        <svg
          width="48"
          height="48"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="1.5"
        >
          <circle cx="12" cy="12" r="10" />
          <line x1="15" y1="9" x2="9" y2="15" />
          <line x1="9" y1="9" x2="15" y2="15" />
        </svg>
        <p class="error-title">登录失败</p>
        <p class="error-detail">{{ errorMsg }}</p>
        <button class="retry-btn" @click="goLogin">返回登录页</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from "vue";
import { useRouter, useRoute } from "vue-router";
import { authApi } from "../api/auth.js";
import { useAuth } from "../composables/useAuth.js";

const router = useRouter();
const route = useRoute();
const { setAuth } = useAuth();

const loading = ref(true);
const errorMsg = ref("");

function goLogin() {
  router.replace("/login");
}

onMounted(async () => {
  const code = route.query.code;

  if (!code) {
    errorMsg.value = "缺少授权码参数";
    loading.value = false;
    return;
  }

  try {
    const res = await authApi.githubCallback(code);
    setAuth(res);
    router.replace("/dashboard");
  } catch (e) {
    errorMsg.value = e.message || "GitHub 登录失败，请重试";
    loading.value = false;
  }
});
</script>

<style scoped>
.github-callback-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg-base);
}

.callback-card {
  width: 360px;
  padding: 48px 36px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  text-align: center;
}

.callback-loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.callback-text {
  color: var(--text-secondary);
  font-size: 14px;
}

.callback-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  color: var(--red, #ef4444);
}

.error-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text-primary);
}

.error-detail {
  font-size: 13px;
  color: var(--text-muted);
}

.retry-btn {
  margin-top: 12px;
  padding: 10px 24px;
  background: var(--gradient-brand);
  border: none;
  border-radius: var(--radius-md);
  color: #fff;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
}

.retry-btn:hover {
  opacity: 0.9;
}

.spinner-lg {
  width: 36px;
  height: 36px;
  border: 3px solid var(--border);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
