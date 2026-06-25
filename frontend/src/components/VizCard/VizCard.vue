<template>
  <div class="viz-card-wrapper">
    <!-- 拉取代码中 -->
    <div v-if="fetching" class="viz-card-loading">
      <div class="viz-card-spinner"></div>
      <span>正在加载可视化...</span>
    </div>

    <!-- 拉取失败 -->
    <div v-else-if="fetchError" class="viz-card-error">
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
      <span>{{ fetchError }}</span>
      <button class="viz-card-btn" @click="fetchCode">重试</button>
    </div>

    <!-- 代码就绪，交给 EduVizSandbox 渲染（不传 title/description，避免内部 header 占用缩放空间） -->
    <EduVizSandbox
      v-else-if="code"
      :code="code"
      @ready="emit('ready')"
      @error="emit('error', $event)"
    />
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from "vue";
import EduVizSandbox from "../EduViz/EduVizSandbox.vue";

const props = defineProps({
  /** 可视化 ID（viz_id），格式为 UUID 字符串 */
  vizId: { type: String, required: true },
  /** 标题（可选，不传则从 meta 接口获取） */
  title: { type: String, default: "" },
  /** 描述（可选） */
  description: { type: String, default: "" },
});

const emit = defineEmits(["ready", "error"]);

const fetching = ref(true);
const fetchError = ref("");
const code = ref("");
const metaTitle = ref("");

async function fetchCode() {
  if (!props.vizId) return;
  fetching.value = true;
  fetchError.value = "";
  code.value = "";

  try {
    const { api } = await import("../../api/base.js");

    // 并行拉取代码和 meta（meta 用于获取标题）
    const [codeRes, metaRes] = await Promise.all([
      api.getRaw(`/api/documents/${props.vizId}/raw`),
      props.title
        ? Promise.resolve(null)
        : api.get(`/api/viz/${props.vizId}/meta`).catch(() => null),
    ]);

    if (!codeRes.ok) {
      throw new Error(`加载失败 (${codeRes.status})`);
    }

    code.value = await codeRes.text();

    if (metaRes && metaRes.title) {
      metaTitle.value = metaRes.title;
    }
  } catch (e) {
    fetchError.value = e.message || "加载失败";
    emit("error", fetchError.value);
  } finally {
    fetching.value = false;
  }
}

watch(
  () => props.vizId,
  () => {
    fetchCode();
  },
);
onMounted(() => {
  fetchCode();
});

defineExpose({ reload: fetchCode });
</script>

<style scoped>
.viz-card-wrapper {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

/* 加载 */
.viz-card-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 28px;
  font-size: 12px;
  color: var(--text-muted, #9ca3af);
}

.viz-card-spinner {
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
.viz-card-error {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  margin: 8px;
  background: var(--red-dim, #fef2f2);
  border: 1px solid rgba(239, 68, 68, 0.25);
  border-radius: var(--radius-sm, 6px);
  font-size: 12px;
  color: var(--red, #ef4444);
}

.viz-card-btn {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid rgba(239, 68, 68, 0.3);
  background: transparent;
  color: var(--red, #ef4444);
  font-size: 12px;
  cursor: pointer;
}
</style>
