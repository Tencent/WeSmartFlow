<template>
  <div
    ref="rootRef"
    class="eduviz-wrapper"
    :class="{ 'is-loading': loading, 'has-error': error }"
  >
    <!-- 加载状态 -->
    <div v-if="loading" class="eduviz-loading">
      <div class="eduviz-spinner"></div>
      <span>正在加载交互式可视化...</span>
    </div>

    <!-- 错误状态 -->
    <div v-if="error" class="eduviz-error">
      <svg
        width="14"
        height="14"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <span>{{ error }}</span>
      <button class="eduviz-btn" @click="reload">重试</button>
    </div>

    <!-- 缩放容器：固定原始尺寸，绝对居中 + scale -->
    <div
      class="eduviz-scaler"
      :style="{
        width: naturalW + 'px',
        height: naturalH + 'px',
        transform: `translate(-50%, -50%) scale(${scale})`,
        visibility: loading || !sizeReady ? 'hidden' : 'visible',
      }"
    >
      <!-- 头部信息 -->
      <div v-if="title || description" class="eduviz-header">
        <div class="eduviz-title-row">
          <svg
            class="eduviz-icon"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M12 2L2 7l10 5 10-5-10-5z" />
            <path d="M2 17l10 5 10-5" />
            <path d="M2 12l10 5 10-5" />
          </svg>
          <span class="eduviz-title">{{ title }}</span>
          <div class="eduviz-actions">
            <button class="eduviz-btn" title="重新运行" @click="reload">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M1 4v6h6" />
                <path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
              </svg>
            </button>
            <button class="eduviz-btn" title="全屏" @click="toggleFullscreen">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path
                  d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3m0 18h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3"
                />
              </svg>
            </button>
          </div>
        </div>
        <div v-if="description" class="eduviz-desc">{{ description }}</div>
      </div>

      <!-- iframe 沙箱，撑满缩放层 -->
      <iframe
        ref="iframeRef"
        class="eduviz-iframe"
        :class="{ 'is-fullscreen': isFullscreen }"
        sandbox="allow-scripts allow-same-origin"
        @load="onIframeLoad"
      ></iframe>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch, nextTick } from "vue";
import { useTheme } from "../../composables/useTheme.js";

import sdkSource from "./eduviz-sdk.js?raw";
import { SANDBOX_HTML } from "./sandboxTemplate.js";

const props = defineProps({
  title: { type: String, default: "" },
  description: { type: String, default: "" },
  code: { type: String, required: true },
});

const emit = defineEmits(["ready", "error", "event"]);

const { isDark } = useTheme();

const rootRef = ref(null);
const iframeRef = ref(null);
const loading = ref(true);
const error = ref("");
const isFullscreen = ref(false);
// 是否已收到第一次 resize 上报（收到前保持隐藏，避免跳变）
const sizeReady = ref(false);

// 卡片原始尺寸
const naturalW = ref(900);
const naturalH = ref(600);
// 缩放比
const scale = ref(1);

// ── 缩放计算 ──────────────────────────────────────────────────────
function updateScale() {
  if (!rootRef.value) return;
  const { offsetWidth: cw, offsetHeight: ch } = rootRef.value;
  if (!cw || !ch) return;
  const scaleW = cw / naturalW.value;
  const scaleH = ch / naturalH.value;
  scale.value = Math.min(scaleW, scaleH);
}

// ── 监听容器尺寸变化 ──────────────────────────────────────────────
let resizeObserver = null;

function initResizeObserver() {
  resizeObserver?.disconnect();
  resizeObserver = new ResizeObserver(() => {
    updateScale();
  });
  if (rootRef.value) resizeObserver.observe(rootRef.value);
}

function buildSandboxHtml(theme, code) {
  const sdkScript = "<" + "script>" + sdkSource + "</" + "script>";
  return SANDBOX_HTML.replace("__EDUVIZ_SDK_PLACEHOLDER__", () => sdkScript)
    .replace(/__THEME__/g, theme)
    .replace("__USER_CODE__", () => code);
}

function onIframeLoad() {
  // 不在这里关闭 loading，等 resize 上报后再显示，避免跳变
  error.value = "";
  emit("ready");
}

let resizeTimer = null;

function handleMessage(event) {
  if (!iframeRef.value || event.source !== iframeRef.value.contentWindow)
    return;
  const msg = event.data;
  if (!msg || !msg.type) return;

  switch (msg.type) {
    case "resize":
      if (msg.height > 0 && msg.width > 0) {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
          naturalW.value = msg.width;
          naturalH.value = msg.height;
          updateScale();
          sizeReady.value = true;
          loading.value = false; // 尺寸就绪后才关闭 loading
        }, 100);
      } else if (msg.height > 0) {
        // 兼容只上报高度的情况
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(() => {
          naturalH.value = msg.height;
          updateScale();
          sizeReady.value = true;
          loading.value = false;
        }, 100);
      }
      break;
    case "emit":
      emit("event", { event: msg.event, data: msg.data });
      break;
    case "error":
      error.value = msg.message;
      loading.value = false;
      emit("error", msg.message);
      break;
  }
}

function reload() {
  loading.value = true;
  error.value = "";
  sizeReady.value = false; // 重置，等待新的 resize 上报
  const iframe = iframeRef.value;
  if (iframe) {
    const theme = isDark.value ? "dark" : "light";
    iframe.srcdoc = buildSandboxHtml(theme, props.code);
  }
}

function toggleFullscreen() {
  isFullscreen.value = !isFullscreen.value;
}

function sendEvent(event, data) {
  if (iframeRef.value) {
    iframeRef.value.contentWindow.postMessage(
      { type: "event", event, data },
      "*",
    );
  }
}

watch(isDark, (dark) => {
  if (iframeRef.value) {
    iframeRef.value.contentWindow.postMessage(
      { type: "theme", theme: dark ? "dark" : "light" },
      "*",
    );
  }
});

watch(
  () => props.code,
  () => {
    reload();
  },
);

onMounted(() => {
  window.addEventListener("message", handleMessage);
  initResizeObserver();

  nextTick(() => {
    if (iframeRef.value) {
      const theme = isDark.value ? "dark" : "light";
      iframeRef.value.srcdoc = buildSandboxHtml(theme, props.code);
    }
  });
});

onBeforeUnmount(() => {
  window.removeEventListener("message", handleMessage);
  resizeObserver?.disconnect();
});

defineExpose({ reload, sendEvent });
</script>

<style scoped>
/* 根容器：撑满父级，作为缩放基准 */
.eduviz-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* 缩放层：固定原始尺寸，绝对居中 */
.eduviz-scaler {
  position: absolute;
  top: 50%;
  left: 50%;
  transform-origin: center center;
  display: flex;
  flex-direction: column;
}

/* 头部 */
.eduviz-header {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
  flex-shrink: 0;
}

.eduviz-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.eduviz-icon {
  color: var(--brand);
  flex-shrink: 0;
}

.eduviz-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  flex: 1;
}

.eduviz-actions {
  display: flex;
  gap: 4px;
  margin-left: auto;
}

.eduviz-btn {
  width: 26px;
  height: 26px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
}

.eduviz-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border-hover);
}

.eduviz-desc {
  font-size: 12px;
  color: var(--text-secondary);
  margin-top: 4px;
}

/* 加载状态 */
.eduviz-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted);
  z-index: 1;
}

.eduviz-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--brand);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 错误状态 */
.eduviz-error {
  position: absolute;
  top: 8px;
  left: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--red-dim);
  border: 1px solid rgb(239 68 68 / 25%);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--red);
  z-index: 1;
}

.eduviz-error .eduviz-btn {
  margin-left: auto;
  color: var(--red);
  border-color: rgb(239 68 68 / 30%);
}

/* iframe 撑满缩放层剩余空间 */
.eduviz-iframe {
  flex: 1;
  width: 100%;
  border: none;
  display: block;
  min-height: 0;
}

.eduviz-iframe.is-fullscreen {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh !important;
  z-index: 9999;
  border-radius: 0;
}
</style>
