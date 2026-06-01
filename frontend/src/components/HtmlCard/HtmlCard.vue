<template>
  <div ref="rootRef" class="html-card-root">
    <!-- 加载中 -->
    <div v-if="loading" class="html-card-loading">
      <div class="html-card-spinner"></div>
      <span>正在加载卡片...</span>
    </div>

    <!-- 错误 -->
    <div v-if="error" class="html-card-error">
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
      <button class="html-card-btn" @click="load">重试</button>
    </div>

    <!-- 缩放容器：固定原始尺寸，通过 transform scale 适配，绝对居中 -->
    <div
      class="html-card-scaler"
      :style="{
        width: naturalW + 'px',
        height: naturalH + 'px',
        transform: `translate(-50%, -50%) scale(${scale})`,
        visibility: loading || !sizeReady ? 'hidden' : 'visible',
      }"
    >
      <iframe
        ref="iframeRef"
        class="html-card-iframe"
        sandbox="allow-scripts allow-same-origin"
        @load="onIframeLoad"
      ></iframe>
    </div>

    <!-- 选中文本气泡 -->
    <Transition name="bubble">
      <div
        v-if="selectionBubble.visible"
        class="ask-ai-bubble"
        :style="{
          left: selectionBubble.x + 'px',
          top: selectionBubble.y + 'px',
        }"
        @mousedown.prevent
        @click="openAskPanel"
      >
        <svg
          width="12"
          height="12"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2.5"
        >
          <path
            d="M12 2a10 10 0 0 1 10 10c0 5.52-4.48 10-10 10S2 17.52 2 12 6.48 2 12 2z"
          />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        问AI
      </div>
    </Transition>

    <!-- AI 解释浮窗 -->
    <Transition name="panel">
      <div v-if="askPanel.visible" class="ask-ai-panel" @mousedown.stop>
        <!-- 浮窗头部 -->
        <div class="aap-header">
          <div class="aap-title">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            AI 解释
          </div>
          <button class="aap-close" @click="closeAskPanel">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>

        <!-- 选中内容预览 -->
        <div class="aap-selected-text">
          <span class="aap-selected-label">选中内容</span>
          <span class="aap-selected-content">{{ askPanel.selectedText }}</span>
        </div>

        <!-- 回复区域 -->
        <div ref="askBodyRef" class="aap-body">
          <!-- 加载中 -->
          <div v-if="askPanel.loading && !askPanel.reply" class="aap-thinking">
            <div class="aap-dots"><span /><span /><span /></div>
            <span>正在思考...</span>
          </div>
          <!-- 流式回复 -->
          <div
            v-else-if="askPanel.reply"
            class="aap-reply"
            v-html="renderMd(askPanel.reply)"
          ></div>
          <!-- 错误 -->
          <div v-else-if="askPanel.error" class="aap-error">
            {{ askPanel.error }}
          </div>
        </div>

        <!-- 底部操作 -->
        <div class="aap-footer">
          <button v-if="!askPanel.loading" class="aap-btn-retry" @click="doAsk">
            <svg
              width="11"
              height="11"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <polyline points="1 4 1 10 7 10" />
              <path d="M3.51 15a9 9 0 1 0 .49-3.5" />
            </svg>
            重新解释
          </button>
          <span v-else class="aap-loading-hint">生成中...</span>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from "vue";
import { marked } from "marked";
import DOMPurify from "dompurify";
import katex from "katex";
import "katex/dist/katex.min.css";
import { llmApi } from "../../api/llm.js";

marked.setOptions({ breaks: true, gfm: true });

// ── LaTeX + Markdown 渲染 ─────────────────────────────────────────
function renderLatex(text) {
  if (!text) return "";
  const placeholders = [];
  function hold(html) {
    const id = `%%KATEX_${placeholders.length}%%`;
    placeholders.push(html);
    return id;
  }
  let result = text.replace(/\$\$(\s*[\s\S]+?\s*)\$\$/g, (_, expr) => {
    try {
      return hold(
        katex.renderToString(expr.trim(), {
          displayMode: true,
          throwOnError: false,
        }),
      );
    } catch {
      return _;
    }
  });
  result = result.replace(/\\\[([\s\S]+?)\\\]/g, (_, expr) => {
    try {
      return hold(
        katex.renderToString(expr.trim(), {
          displayMode: true,
          throwOnError: false,
        }),
      );
    } catch {
      return _;
    }
  });
  result = result.replace(/\\\((.+?)\\\)/g, (_, expr) => {
    try {
      return hold(
        katex.renderToString(expr.trim(), {
          displayMode: false,
          throwOnError: false,
        }),
      );
    } catch {
      return _;
    }
  });
  result = result.replace(
    /(?<!\$)\$(?!\$)([^\n$]+?)(?<!\$)\$(?!\$)/g,
    (_, expr) => {
      try {
        return hold(
          katex.renderToString(expr.trim(), {
            displayMode: false,
            throwOnError: false,
          }),
        );
      } catch {
        return _;
      }
    },
  );
  for (let i = 0; i < placeholders.length; i++) {
    result = result.replace(`%%KATEX_${i}%%`, placeholders[i]);
  }
  return result;
}

function renderMd(text) {
  if (!text) return "";
  const withLatex = renderLatex(text);
  return DOMPurify.sanitize(marked.parse(withLatex), {
    ADD_TAGS: [
      "span",
      "math",
      "semantics",
      "mrow",
      "mi",
      "mo",
      "mn",
      "msup",
      "msub",
      "mfrac",
      "mtext",
      "annotation",
      "mover",
      "munder",
      "mtable",
      "mtr",
      "mtd",
      "mspace",
      "msqrt",
      "mroot",
      "menclose",
    ],
    ADD_ATTR: [
      "class",
      "style",
      "mathvariant",
      "encoding",
      "displaystyle",
      "scriptlevel",
      "xmlns",
      "aria-hidden",
      "role",
    ],
  });
}

const props = defineProps({
  fileId: { type: String, required: true },
  title: { type: String, default: "" },
  script: { type: String, default: "" },
  showHeader: { type: Boolean, default: true },
  /** 传入当前会话 ID，用于「问AI」功能；不传则不显示气泡 */
  sessionId: { type: String, default: "" },
});

const emit = defineEmits(["loaded", "error"]);

const rootRef = ref(null);
const iframeRef = ref(null);
const loading = ref(true);
const error = ref("");
const sizeReady = ref(false);

const naturalW = ref(900);
const naturalH = ref(600);
const scale = ref(1);

// ── 选中文本气泡 ──────────────────────────────────────────────────
const selectionBubble = ref({ visible: false, x: 0, y: 0, text: "" });

// ── AI 解释浮窗 ───────────────────────────────────────────────────
const askPanel = ref({
  visible: false,
  selectedText: "",
  reply: "",
  loading: false,
  error: "",
});
const askBodyRef = ref(null);
let askAbortController = null;

function openAskPanel() {
  selectionBubble.value.visible = false;
  askPanel.value = {
    visible: true,
    selectedText: selectionBubble.value.text,
    reply: "",
    loading: false,
    error: "",
  };
  nextTick(() => doAsk());
}

function closeAskPanel() {
  askPanel.value.visible = false;
  askAbortController?.abort();
  askAbortController = null;
}

async function doAsk() {
  if (!askPanel.value.selectedText) return;
  askAbortController?.abort();
  askPanel.value.reply = "";
  askPanel.value.error = "";
  askPanel.value.loading = true;

  askAbortController = llmApi.quickAsk(
    {
      question: `请解释以下内容：\n\n"${askPanel.value.selectedText}"`,
      context: "",
    },
    {
      onTextChunk: (delta) => {
        askPanel.value.reply += delta;
        nextTick(() => {
          if (askBodyRef.value)
            askBodyRef.value.scrollTop = askBodyRef.value.scrollHeight;
        });
      },
      onDone: () => {
        askPanel.value.loading = false;
      },
      onError: (err) => {
        askPanel.value.loading = false;
        askPanel.value.error = err.message || "请求失败，请重试";
      },
    },
  );
}

// ── 缩放计算 ──────────────────────────────────────────────────────
function updateScale() {
  if (!rootRef.value) return;
  const { offsetWidth: cw, offsetHeight: ch } = rootRef.value;
  if (!cw || !ch) return;
  const scaleW = cw / naturalW.value;
  const scaleH = ch / naturalH.value;
  scale.value = Math.min(scaleW, scaleH);
}

let resizeObserver = null;

function initResizeObserver() {
  resizeObserver?.disconnect();
  resizeObserver = new ResizeObserver(() => {
    updateScale();
  });
  if (rootRef.value) resizeObserver.observe(rootRef.value);
}

let resizeTimer = null;

function handleMessage(event) {
  if (!iframeRef.value || event.source !== iframeRef.value.contentWindow)
    return;
  const msg = event.data;

  // 尺寸上报
  if (msg?.type === "resize" && msg.height > 0 && msg.width > 0) {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      naturalW.value = msg.width;
      naturalH.value = msg.height;
      updateScale();
      sizeReady.value = true;
      loading.value = false;
    }, 100);
    return;
  }

  // 选中文本上报
  if (msg?.type === "text_selected") {
    const text = (msg.text || "").trim();
    if (text.length < 2) {
      selectionBubble.value.visible = false;
      return;
    }
    // 将 iframe 内坐标转换为卡片容器坐标
    // msg.x / msg.y 是相对 iframe 内容的坐标，需要乘以 scale 再加上 scaler 的偏移
    const root = rootRef.value;
    if (!root) return;
    const cw = root.offsetWidth;
    const ch = root.offsetHeight;
    const scalerLeft = cw / 2;
    const scalerTop = ch / 2;
    // scaler 的 transform: translate(-50%,-50%) scale(scale)
    // 所以 iframe 内 (x, y) 对应容器坐标：scalerLeft + (x - naturalW/2) * scale
    const bx = scalerLeft + (msg.x - naturalW.value / 2) * scale.value;
    const by = scalerTop + (msg.y - naturalH.value / 2) * scale.value - 32; // 气泡在选区上方

    selectionBubble.value = {
      visible: true,
      x: Math.max(4, Math.min(bx, cw - 80)),
      y: Math.max(4, by),
      text,
    };
    return;
  }

  // 点击空白处，隐藏气泡
  if (msg?.type === "selection_cleared") {
    selectionBubble.value.visible = false;
  }
}

// ── 注入脚本：尺寸上报 + 选中文本上报 ───────────────────────────
function injectResizeScript(html) {
  const scriptOpen = "<" + "script>";
  const scriptClose = "<" + "/script>";
  const script = `
${scriptOpen}
(function() {
  // 尺寸上报
  function report() {
    var w = document.documentElement.scrollWidth || document.body.scrollWidth;
    var h = document.documentElement.scrollHeight || document.body.scrollHeight;
    window.parent.postMessage({ type: 'resize', width: w, height: h }, '*');
  }
  window.addEventListener('load', function() { setTimeout(report, 300); });
  window.addEventListener('message', function(e) { if (e.data?.type === 'requestResize') report(); });
  var t;
  new MutationObserver(function() { clearTimeout(t); t = setTimeout(report, 200); })
    .observe(document.body, { childList: true, subtree: true, attributes: true });

  // 选中文本上报
  document.addEventListener('mouseup', function(e) {
    var sel = window.getSelection();
    var text = sel ? sel.toString().trim() : '';
    if (text.length >= 2) {
      var range = sel.getRangeAt(0);
      var rect = range.getBoundingClientRect();
      window.parent.postMessage({
        type: 'text_selected',
        text: text,
        x: rect.left + rect.width / 2,
        y: rect.top + window.scrollY,
      }, '*');
    } else {
      window.parent.postMessage({ type: 'selection_cleared' }, '*');
    }
  });

  // 点击空白处清除
  document.addEventListener('mousedown', function(e) {
    var sel = window.getSelection();
    if (sel && sel.toString().trim().length === 0) {
      window.parent.postMessage({ type: 'selection_cleared' }, '*');
    }
  });
})();
${scriptClose}`;
  if (html.includes("</body>"))
    return html.replace("</body>", script + "</body>");
  return html + script;
}

// ── 加载卡片 ──────────────────────────────────────────────────────
async function load() {
  if (!props.fileId) return;
  loading.value = true;
  error.value = "";
  sizeReady.value = false;

  try {
    const { api } = await import("../../api/base.js");
    const res = await api.getRaw(`/files/cards/${props.fileId}`);
    if (!res.ok) throw new Error(`加载失败 (${res.status})`);
    let html = await res.text();

    const imgPaths = [
      ...new Set(
        [
          ...html.matchAll(
            /src="(\/files\/cards\/[^"]+\.(png|jpg|jpeg|webp))"/gi,
          ),
        ].map((m) => m[1]),
      ),
    ];
    await Promise.all(
      imgPaths.map(async (imgPath) => {
        try {
          const r = await api.getRaw(imgPath);
          if (!r.ok) return;
          const blob = await r.blob();
          const dataUrl = await new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => resolve(reader.result);
            reader.onerror = reject;
            reader.readAsDataURL(blob);
          });
          html = html.replaceAll(`src="${imgPath}"`, `src="${dataUrl}"`);
        } catch {
          /* 图片失败不影响整体 */
        }
      }),
    );

    if (iframeRef.value) {
      iframeRef.value.srcdoc = injectResizeScript(html);
    }
  } catch (e) {
    loading.value = false;
    error.value = e.message || "加载失败";
    emit("error", error.value);
  }
}

function onIframeLoad() {
  error.value = "";
  emit("loaded");
}

watch(
  () => props.fileId,
  () => {
    load();
  },
);

let visibilityObserver = null;

onMounted(() => {
  window.addEventListener("message", handleMessage);
  initResizeObserver();
  load();

  visibilityObserver = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && iframeRef.value?.contentWindow) {
          setTimeout(() => {
            iframeRef.value?.contentWindow?.postMessage(
              { type: "requestResize" },
              "*",
            );
            updateScale();
          }, 50);
        }
      }
    },
    { threshold: 0.01 },
  );

  setTimeout(() => {
    if (iframeRef.value) visibilityObserver.observe(iframeRef.value);
  }, 0);
});

onBeforeUnmount(() => {
  window.removeEventListener("message", handleMessage);
  resizeObserver?.disconnect();
  visibilityObserver?.disconnect();
  askAbortController?.abort();
});

defineExpose({ reload: load });
</script>

<style scoped>
/* 根容器：撑满父级，作为缩放基准 */
.html-card-root {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* 固定原始尺寸的缩放层，绝对居中 */
.html-card-scaler {
  flex-shrink: 0;
  position: absolute;
  top: 50%;
  left: 50%;
  transform-origin: center center;
}

/* iframe 撑满缩放层 */
.html-card-iframe {
  width: 100%;
  height: 100%;
  border: none;
  display: block;
}

/* 加载 */
.html-card-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  font-size: 12px;
  color: var(--text-muted, #9ca3af);
  z-index: 1;
}

.html-card-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border, #e5e7eb);
  border-top-color: var(--brand, #4f46e5);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

/* 错误 */
.html-card-error {
  position: absolute;
  top: 8px;
  left: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: var(--red-dim, #fef2f2);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  color: var(--red, #ef4444);
  z-index: 1;
}

.html-card-error .html-card-btn {
  margin-left: auto;
  color: var(--red, #ef4444);
  border-color: rgba(239, 68, 68, 0.3);
}

.html-card-btn {
  padding: 2px 8px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border, #e5e7eb);
  background: transparent;
  cursor: pointer;
  font-size: 12px;
}

/* ── 选中文本气泡 ─────────────────────────────────────────────── */
.ask-ai-bubble {
  position: absolute;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: var(--brand, #4f46e5);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  border-radius: 20px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.35);
  white-space: nowrap;
  user-select: none;
  transform: translateX(-50%);
  transition:
    opacity 0.15s,
    transform 0.15s;
}

.ask-ai-bubble:hover {
  opacity: 0.9;
  transform: translateX(-50%) scale(1.04);
}

/* 气泡小箭头 */
.ask-ai-bubble::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: var(--brand, #4f46e5);
}

.bubble-enter-active,
.bubble-leave-active {
  transition:
    opacity 0.15s,
    transform 0.15s;
}
.bubble-enter-from,
.bubble-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}

/* ── AI 解释浮窗 ──────────────────────────────────────────────── */
.ask-ai-panel {
  position: absolute;
  bottom: 12px;
  right: 12px;
  z-index: 30;
  width: 320px;
  max-width: calc(100% - 24px);
  background: var(--bg-card, #fff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: var(--radius-lg, 10px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-enter-active,
.panel-leave-active {
  transition:
    opacity 0.2s,
    transform 0.2s;
}
.panel-enter-from,
.panel-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.97);
}

.aap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--border, #e5e7eb);
}

.aap-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--brand, #4f46e5);
}

.aap-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--text-muted, #9ca3af);
  border-radius: 4px;
  transition:
    background 0.15s,
    color 0.15s;
}

.aap-close:hover {
  background: var(--bg-subtle, #f3f4f6);
  color: var(--text-primary, #111);
}

.aap-selected-text {
  padding: 8px 12px;
  background: var(--bg-subtle, #f8fafc);
  border-bottom: 1px solid var(--border, #e5e7eb);
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.aap-selected-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted, #9ca3af);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.aap-selected-content {
  font-size: 12px;
  color: var(--text-secondary, #6b7280);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.aap-body {
  padding: 12px;
  max-height: 260px;
  overflow-y: auto;
  flex: 1;
}

.aap-thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted, #9ca3af);
  font-size: 12px;
}

.aap-dots {
  display: flex;
  gap: 3px;
}

.aap-dots span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand, #4f46e5);
  animation: dot-bounce 1.2s infinite ease-in-out;
}

.aap-dots span:nth-child(2) {
  animation-delay: 0.2s;
}
.aap-dots span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes dot-bounce {
  0%,
  80%,
  100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.aap-reply {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary, #111);
}

.aap-reply :deep(p) {
  margin: 0 0 8px;
}
.aap-reply :deep(p:last-child) {
  margin-bottom: 0;
}
.aap-reply :deep(code) {
  background: var(--bg-subtle, #f3f4f6);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
}
.aap-reply :deep(pre) {
  background: var(--bg-subtle, #f3f4f6);
  padding: 8px 10px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 12px;
}
.aap-reply :deep(.katex-display) {
  margin: 6px 0;
}

.aap-error {
  font-size: 12px;
  color: var(--red, #ef4444);
}

.aap-footer {
  padding: 8px 12px;
  border-top: 1px solid var(--border, #e5e7eb);
  display: flex;
  align-items: center;
}

.aap-btn-retry {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border, #e5e7eb);
  background: transparent;
  cursor: pointer;
  font-size: 11px;
  color: var(--text-secondary, #6b7280);
  transition:
    border-color 0.15s,
    color 0.15s;
}

.aap-btn-retry:hover {
  border-color: var(--brand, #4f46e5);
  color: var(--brand, #4f46e5);
}

.aap-loading-hint {
  font-size: 11px;
  color: var(--text-muted, #9ca3af);
}
</style>
