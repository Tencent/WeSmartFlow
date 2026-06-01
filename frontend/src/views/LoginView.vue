<template>
  <div class="login-page">
    <!-- 背景装饰 -->
    <div class="login-bg">
      <div class="bg-orb orb-1"></div>
      <div class="bg-orb orb-2"></div>
      <div class="bg-orb orb-3"></div>
    </div>

    <div class="login-card">
      <!-- Logo -->
      <div class="login-logo">
        <div class="logo-mark">
          <img src="/logo.png" alt="Logo" class="logo-img" />
        </div>
        <h1 class="login-title">WeSmartFlow</h1>
        <p class="login-subtitle">你的专属知识大脑</p>
      </div>

      <!-- ===== 邮箱验证码登录 ===== -->
      <form class="login-form" @submit.prevent="handleEmailLogin">
        <div class="form-group">
          <label class="form-label">邮箱地址</label>
          <input
            v-model="email"
            type="email"
            class="form-input"
            placeholder="请输入邮箱"
            autocomplete="email"
            :disabled="loading"
            autofocus
          />
        </div>

        <!-- 验证码输入（发送后显示） -->
        <div v-if="codeSent" class="form-group">
          <label class="form-label">验证码</label>
          <div class="code-input-wrapper">
            <input
              ref="codeInputRef"
              v-model="verifyCode"
              type="text"
              class="form-input code-input"
              placeholder="请输入 6 位验证码"
              maxlength="6"
              inputmode="numeric"
              autocomplete="one-time-code"
              :disabled="loading"
              @keyup.enter="handleEmailLogin"
            />
            <button
              type="button"
              class="resend-btn"
              :disabled="cooldown > 0 || sendingCode"
              @click="handleSendCode"
            >
              <span v-if="sendingCode" class="spinner-sm"></span>
              <span v-else-if="cooldown > 0">{{ cooldown }}s</span>
              <span v-else>重新发送</span>
            </button>
          </div>
        </div>

        <!-- 错误提示 -->
        <div v-if="errorMsg" class="login-error">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="15" y1="9" x2="9" y2="15" />
            <line x1="9" y1="9" x2="15" y2="15" />
          </svg>
          {{ errorMsg }}
        </div>

        <!-- 成功提示 -->
        <div v-if="successMsg" class="login-success">
          <svg
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="10" />
            <polyline points="16 10 11 15 8 12" />
          </svg>
          {{ successMsg }}
        </div>

        <!-- 发送验证码 / 登录按钮 -->
        <button
          type="submit"
          class="login-btn"
          :disabled="loading || !canSubmitEmail"
        >
          <span v-if="loading" class="spinner"></span>
          <span v-else>{{ codeSent ? "登 录" : "发送验证码" }}</span>
        </button>

        <!-- 提示文字 -->
        <div class="login-hint">
          <span class="hint-text">新用户将自动注册</span>
        </div>
      </form>

      <!-- ===== 第三方登录分割线 ===== -->
      <div class="login-divider">
        <span class="divider-text">或</span>
      </div>

      <!-- GitHub 登录按钮 -->
      <button
        class="github-login-btn"
        :disabled="githubLoading"
        @click="handleGitHubLogin"
      >
        <svg
          class="github-icon"
          width="20"
          height="20"
          viewBox="0 0 24 24"
          fill="currentColor"
        >
          <path
            d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"
          />
        </svg>
        <span v-if="githubLoading" class="spinner-sm"></span>
        <span v-else>使用 GitHub 登录</span>
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onUnmounted } from "vue";
import { useRouter } from "vue-router";
import { authApi } from "../api/auth.js";
import { useAuth } from "../composables/useAuth.js";

const router = useRouter();
const { setAuth } = useAuth();

// ── 通用状态 ──
const loading = ref(false);
const errorMsg = ref("");
const successMsg = ref("");

// ── GitHub 登录状态 ──
const githubLoading = ref(false);

// ── 邮箱验证码状态 ──
const email = ref("");
const verifyCode = ref("");
const codeSent = ref(false);
const sendingCode = ref(false);
const cooldown = ref(0);
const codeInputRef = ref(null);
let cooldownTimer = null;

// ── 计算属性 ──
const canSubmitEmail = computed(() => {
  if (!email.value) return false;
  if (codeSent.value && verifyCode.value.length !== 6) return false;
  return true;
});

// ── 倒计时 ──
function startCooldown(seconds) {
  cooldown.value = seconds;
  if (cooldownTimer) clearInterval(cooldownTimer);
  cooldownTimer = setInterval(() => {
    cooldown.value--;
    if (cooldown.value <= 0) {
      clearInterval(cooldownTimer);
      cooldownTimer = null;
    }
  }, 1000);
}

// ── 发送验证码 ──
async function handleSendCode() {
  if (!email.value) {
    errorMsg.value = "请输入邮箱地址";
    return;
  }

  sendingCode.value = true;
  errorMsg.value = "";
  successMsg.value = "";

  try {
    const res = await authApi.sendCode(email.value);
    codeSent.value = true;
    successMsg.value = res.message || "验证码已发送，请查收邮件";
    startCooldown(res.cooldown || 60);
    // 自动聚焦验证码输入框
    await nextTick();
    codeInputRef.value?.focus();
  } catch (e) {
    errorMsg.value = e.message || "发送验证码失败";
  } finally {
    sendingCode.value = false;
  }
}

// ── 邮箱验证码登录 ──
async function handleEmailLogin() {
  if (!canSubmitEmail.value) return;

  // 如果还没发送验证码，先发送
  if (!codeSent.value) {
    await handleSendCode();
    return;
  }

  loading.value = true;
  errorMsg.value = "";
  successMsg.value = "";

  try {
    const res = await authApi.verifyCode(email.value, verifyCode.value);
    setAuth(res);
    router.replace("/chat");
  } catch (e) {
    errorMsg.value = e.message || "验证失败，请重试";
  } finally {
    loading.value = false;
  }
}

// ── GitHub 登录 ──
async function handleGitHubLogin() {
  githubLoading.value = true;
  errorMsg.value = "";

  try {
    const { authorize_url } = await authApi.getGitHubAuthorizeUrl();
    // 跳转到 GitHub 授权页面
    window.location.href = authorize_url;
  } catch (e) {
    errorMsg.value = e.message || "GitHub 登录失败";
    githubLoading.value = false;
  }
}

// ── 清理 ──
onUnmounted(() => {
  if (cooldownTimer) clearInterval(cooldownTimer);
});
</script>

<style scoped>
.login-page {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg-base);
  overflow: hidden;
}

/* 背景装饰球 */
.login-bg {
  position: absolute;
  inset: 0;
  pointer-events: none;
  overflow: hidden;
}

.bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.35;
}

.orb-1 {
  width: 400px;
  height: 400px;
  background: #6366f1;
  top: -100px;
  right: -80px;
  animation: float 8s ease-in-out infinite;
}

.orb-2 {
  width: 300px;
  height: 300px;
  background: #a855f7;
  bottom: -60px;
  left: -60px;
  animation: float 10s ease-in-out infinite reverse;
}

.orb-3 {
  width: 200px;
  height: 200px;
  background: #8b5cf6;
  top: 40%;
  left: 50%;
  animation: float 12s ease-in-out infinite;
}

@keyframes float {
  0%,
  100% {
    transform: translate(0, 0);
  }

  50% {
    transform: translate(30px, -20px);
  }
}

/* 卡片 */
.login-card {
  position: relative;
  width: 400px;
  padding: 40px 36px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
}

/* Logo */
.login-logo {
  text-align: center;
  margin-bottom: 24px;
}

.login-logo .logo-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 14px;
  margin-bottom: 14px;
  overflow: hidden;
}
.login-logo .logo-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 14px;
}

.login-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}

.login-subtitle {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 4px;
}

/* 表单 */
.login-form {
  display: flex;
  flex-direction: column;
  gap: 18px;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.form-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}

.form-label .optional-hint {
  font-weight: 400;
  color: var(--text-dim);
}

.form-input {
  width: 100%;
  padding: 10px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 14px;
  font-family: inherit;
  outline: none;
  transition: var(--transition);
}

.form-input::placeholder {
  color: var(--text-dim);
}

.form-input:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px var(--brand-glow);
}

.form-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

/* 验证码输入框 */
.code-input-wrapper {
  display: flex;
  gap: 10px;
}

.code-input-wrapper .code-input {
  flex: 1;
  font-size: 16px;
  letter-spacing: 4px;
  text-align: center;
  font-weight: 600;
}

.resend-btn {
  flex-shrink: 0;
  min-width: 90px;
  padding: 10px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--brand);
  font-size: 13px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: var(--transition);
  display: flex;
  align-items: center;
  justify-content: center;
}

.resend-btn:hover:not(:disabled) {
  background: var(--brand-dim);
  border-color: var(--brand);
}

.resend-btn:disabled {
  color: var(--text-dim);
  cursor: not-allowed;
}

/* 错误提示 */
.login-error {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  background: var(--red-dim);
  border: 1px solid rgb(239 68 68 / 18%);
  border-radius: var(--radius-md);
  color: var(--red);
  font-size: 13px;
}

/* 成功提示 */
.login-success {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 14px;
  background: var(--green-dim, rgba(34, 197, 94, 0.08));
  border: 1px solid rgb(34 197 94 / 18%);
  border-radius: var(--radius-md);
  color: var(--green, #22c55e);
  font-size: 13px;
}

/* 登录按钮 */
.login-btn {
  width: 100%;
  padding: 11px;
  background: var(--gradient-brand);
  border: none;
  border-radius: var(--radius-md);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  font-family: inherit;
  cursor: pointer;
  transition: var(--transition);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-top: 4px;
}

.login-btn:hover:not(:disabled) {
  opacity: 0.9;
  box-shadow: var(--shadow-glow);
}

.login-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 登录提示 */
.login-hint {
  text-align: center;
  margin-top: 2px;
}

.hint-text {
  font-size: 13px;
  color: var(--text-muted);
}

/* 加载动画 */
.spinner {
  width: 18px;
  height: 18px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 浅色主题微调 */
[data-theme="light"] .login-card {
  box-shadow: 0 8px 40px rgb(0 0 0 / 8%);
}

[data-theme="light"] .bg-orb {
  opacity: 0.15;
}

/* 分割线 */
.login-divider {
  display: flex;
  align-items: center;
  margin: 20px 0;
}

.login-divider::before,
.login-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: var(--border);
}

.divider-text {
  padding: 0 14px;
  font-size: 12px;
  color: var(--text-dim);
}

/* GitHub 登录按钮 */
.github-login-btn {
  width: 100%;
  padding: 11px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  color: var(--text-primary);
  font-size: 14px;
  font-weight: 500;
  font-family: inherit;
  cursor: pointer;
  transition: var(--transition);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
}

.github-login-btn:hover:not(:disabled) {
  border-color: var(--text-muted);
  background: var(--bg-panel);
}

.github-login-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.github-icon {
  flex-shrink: 0;
}
</style>
