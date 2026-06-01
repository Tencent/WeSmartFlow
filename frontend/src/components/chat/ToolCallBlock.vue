<template>
  <div class="msb-tool" :class="[tc.status, { collapsed: localCollapsed }]">
    <!-- 标题栏 -->
    <div class="msb-tool-header" @click="localCollapsed = !localCollapsed">
      <span class="msb-tool-icon">
        <span v-if="tc.status === 'calling'" class="ms-spin" />
        <span
          v-else-if="tc.status === 'running'"
          class="ms-spin ms-spin-green"
        />
        <svg
          v-else
          width="10"
          height="10"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="3"
        >
          <polyline points="20 6 9 17 4 12" />
        </svg>
      </span>
      <span class="msb-tool-title">{{ tc.title }}</span>
      <svg
        class="msb-chevron"
        width="10"
        height="10"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        stroke-width="2.5"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </div>
    <!-- 详情区（可折叠） -->
    <div class="msb-tool-body">
      <!-- 参数区 -->
      <div v-if="tc.argsBuf" class="msb-section">
        <div class="msb-section-label">参数</div>
        <div
          :ref="(el) => $emit('set-args-ref', el)"
          class="msb-scroll-area msb-args"
        >
          {{ tc.argsBuf }}
        </div>
      </div>
      <!-- 运行日志区 -->
      <div v-if="tc.runLogs && tc.runLogs.length" class="msb-section">
        <div class="msb-section-label">执行过程</div>
        <div
          :ref="(el) => $emit('set-logs-ref', el)"
          class="msb-scroll-area msb-logs"
        >
          <div
            v-for="(log, li) in tc.runLogs"
            :key="li"
            class="msb-log-item"
            :class="log.type"
          >
            <template v-if="log.type === 'agent_think'">
              <span class="msb-log-prefix">💭</span>
              <span class="msb-log-text">{{ log.text }}</span>
            </template>
            <template v-else-if="log.type === 'agent_tool'">
              <span class="msb-log-prefix">🔧</span>
              <span class="msb-log-text">{{ log.text }}</span>
            </template>
            <template v-else>
              <span class="msb-log-text">{{ log.text }}</span>
            </template>
          </div>
        </div>
      </div>
      <!-- 结果摘要 -->
      <div v-if="tc.resultSummary" class="msb-section">
        <div class="msb-section-label">结果</div>
        <div class="msb-result-text">{{ tc.resultSummary }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
const props = defineProps({
  tc: {
    type: Object,
    required: true,
    // { id, status: 'calling'|'running'|'done', title, collapsed, argsBuf, runLogs, resultSummary }
  },
});
defineEmits(["set-args-ref", "set-logs-ref"]);
const localCollapsed = ref(props.tc.collapsed ?? true);
watch(
  () => props.tc.collapsed,
  (v) => {
    localCollapsed.value = v;
  },
);
</script>

<style scoped>
.msb-tool {
  border-radius: 7px;
  border: 1px solid rgba(56, 189, 248, 0.25);
  background: rgba(56, 189, 248, 0.03);
  overflow: hidden;
  transition:
    border-color 0.2s,
    background 0.2s;
}
.msb-tool.calling {
  border-color: rgba(251, 191, 36, 0.45);
  background: rgba(251, 191, 36, 0.04);
}
.msb-tool.running {
  border-color: rgba(52, 211, 153, 0.45);
  background: rgba(52, 211, 153, 0.04);
}
.msb-tool.done {
  border-color: rgba(100, 116, 139, 0.2);
  background: transparent;
}

.msb-tool-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  cursor: pointer;
  user-select: none;
}
.msb-tool-header:hover {
  background: rgba(255, 255, 255, 0.04);
}
.msb-tool-icon {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-dim);
  flex-shrink: 0;
}
.msb-tool.calling .msb-tool-icon {
  color: #fbbf24;
}
.msb-tool.running .msb-tool-icon {
  color: #34d399;
}
.msb-tool.done .msb-tool-icon {
  color: #34d399;
}

.msb-tool-title {
  flex: 1;
  font-size: 11px;
  color: var(--text-secondary);
  font-weight: 500;
}
.msb-tool.calling .msb-tool-title {
  color: #fbbf24;
}
.msb-tool.running .msb-tool-title {
  color: #34d399;
}

.msb-tool-body {
  padding: 0 9px 7px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 600px;
  overflow: hidden;
  transition:
    max-height 0.3s cubic-bezier(0.4, 0, 0.2, 1),
    padding 0.3s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 0.25s ease;
  opacity: 1;
}
.msb-tool.collapsed .msb-tool-body {
  max-height: 0;
  padding-top: 0;
  padding-bottom: 0;
  opacity: 0;
}
.msb-chevron {
  color: var(--text-dim);
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  flex-shrink: 0;
}
.msb-tool.collapsed .msb-chevron {
  transform: rotate(-90deg);
}
.msb-section {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.msb-section-label {
  font-size: 10px;
  color: var(--text-dim);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.msb-scroll-area {
  max-height: 56px;
  overflow-y: auto;
  font-size: 11px;
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
  color: var(--text-secondary);
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  padding: 4px 6px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.1) transparent;
}
.msb-scroll-area::-webkit-scrollbar {
  width: 3px;
}
.msb-scroll-area::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 2px;
}
.msb-args {
  color: #93c5fd;
}
.msb-logs {
  max-height: 80px;
}
.msb-log-item {
  display: flex;
  gap: 4px;
  padding: 1px 0;
  font-size: 10.5px;
}
.msb-log-prefix {
  flex-shrink: 0;
}
.msb-log-text {
  color: var(--text-secondary);
}
.msb-log-item.agent_think .msb-log-text {
  color: #c4b5fd;
}
.msb-log-item.agent_tool .msb-log-text {
  color: #6ee7b7;
}
.msb-result-text {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.5;
  padding: 4px 6px;
  background: rgba(0, 0, 0, 0.1);
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-word;
}
.ms-spin {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid #fbbf24;
  border-top-color: transparent;
  animation: spin 0.7s linear infinite;
  display: inline-block;
}
.ms-spin-green {
  border-color: #34d399;
  border-top-color: transparent;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
