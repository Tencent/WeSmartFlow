<template>
  <div
    class="msb-think"
    :class="{ done: think.status === 'done', collapsed: localCollapsed }"
  >
    <div class="msb-think-header" @click="localCollapsed = !localCollapsed">
      <span class="msb-think-icon">
        <span v-if="think.status === 'running'" class="ms-spin" />
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
      <span class="msb-think-title">
        {{ think.status === "running" ? "思考中…" : "思考过程" }}
      </span>
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
    <div class="msb-think-body">
      <div :ref="(el) => $emit('set-ref', el)" class="msb-scroll-area">
        {{ think.content }}
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from "vue";
const props = defineProps({
  think: {
    type: Object,
    required: true,
    // { status: 'running'|'done', content: string, collapsed: boolean }
  },
});
defineEmits(["set-ref"]);
const localCollapsed = ref(props.think.collapsed ?? true);
watch(
  () => props.think.collapsed,
  (v) => {
    localCollapsed.value = v;
  },
);
</script>

<style scoped>
.msb-think {
  border-radius: 7px;
  border: 1px solid rgba(139, 92, 246, 0.2);
  background: rgba(139, 92, 246, 0.04);
  overflow: hidden;
  transition: border-color 0.2s;
}
.msb-think.done {
  border-color: rgba(139, 92, 246, 0.12);
  background: rgba(139, 92, 246, 0.02);
}
.msb-think-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 9px;
  cursor: pointer;
  user-select: none;
}
.msb-think-header:hover {
  background: rgba(139, 92, 246, 0.06);
}
.msb-think-icon {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #a78bfa;
  flex-shrink: 0;
}
.msb-think-title {
  flex: 1;
  font-size: 11px;
  color: #a78bfa;
  font-weight: 500;
}
.msb-think.done .msb-think-title {
  color: var(--text-dim);
}
.msb-think-body {
  padding: 0 9px 7px;
  max-height: 400px;
  overflow: hidden;
  transition:
    max-height 0.3s cubic-bezier(0.4, 0, 0.2, 1),
    padding 0.3s cubic-bezier(0.4, 0, 0.2, 1),
    opacity 0.25s ease;
  opacity: 1;
}
.msb-think.collapsed .msb-think-body {
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
.msb-think.collapsed .msb-chevron {
  transform: rotate(-90deg);
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
.ms-spin {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid var(--brand-light);
  border-top-color: transparent;
  animation: spin 0.7s linear infinite;
  display: inline-block;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
