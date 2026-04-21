<template>
  <div class="path-page">
    <div class="page-header">
      <div>
        <h1 class="page-title">学习路径</h1>
        <p class="page-subtitle">Agent 为你规划的个性化学习路线图</p>
      </div>
      <div class="header-right">
        <button class="btn btn-ghost">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <polyline points="23 4 23 10 17 10" />
            <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
          </svg>
          重新规划
        </button>
        <button class="btn btn-primary">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
            <polyline points="7 10 12 15 17 10" />
            <line x1="12" y1="15" x2="12" y2="3" />
          </svg>
          导出路径
        </button>
      </div>
    </div>

    <!-- Course selector tabs -->
    <div class="course-tabs">
      <button
        v-for="c in courses"
        :key="c.id"
        class="course-tab"
        :class="{ active: activeCourse === c.id }"
        @click="activeCourse = c.id"
      >
        <div class="ct-dot" :style="{ background: c.color }" />
        {{ c.name }}
        <span class="ct-progress">{{ c.done }}/{{ c.total }}</span>
      </button>
    </div>

    <div class="path-layout">
      <!-- Main path visualization -->
      <div class="path-main">
        <div class="path-overall">
          <div class="po-label">整体进度</div>
          <div class="po-val text-gradient">{{ currentCourse.percent }}%</div>
          <div class="progress-bar" style="width: 200px">
            <div
              class="progress-fill"
              :style="{ width: currentCourse.percent + '%' }"
            />
          </div>
          <div class="po-eta">
            预计还需 <strong>{{ currentCourse.eta }}</strong> 完成
          </div>
        </div>

        <!-- Path nodes -->
        <div class="path-nodes">
          <div
            v-for="(chapter, ci) in currentCourse.chapters"
            :key="ci"
            class="path-chapter"
          >
            <!-- Chapter header -->
            <div class="chapter-header" @click="toggleChapter(ci)">
              <div class="ch-icon" :style="getChapterStyle(chapter.status)">
                <svg
                  v-if="chapter.status === 'done'"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="3"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
                <svg
                  v-else-if="chapter.status === 'active'"
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <polygon points="5 3 19 12 5 21 5 3" />
                </svg>
                <span v-else style="font-size: 11px; font-weight: 700">{{
                  ci + 1
                }}</span>
              </div>
              <div
                v-if="ci < currentCourse.chapters.length - 1"
                class="ch-connector"
                :class="chapter.status"
              />
              <div class="ch-info">
                <div class="ch-title">
                  {{ chapter.title }}
                </div>
                <div class="ch-meta">
                  <span class="badge" :class="getStatusBadge(chapter.status)">{{
                    getStatusText(chapter.status)
                  }}</span>
                  <span class="ch-stats"
                    >{{ chapter.done }}/{{ chapter.total }} 节 ·
                    {{ chapter.time }}</span
                  >
                </div>
              </div>
              <div
                class="ch-chevron"
                :class="{ open: expandedChapters.includes(ci) }"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </div>
            </div>

            <!-- Lessons inside chapter -->
            <transition name="expand">
              <div v-if="expandedChapters.includes(ci)" class="lessons-list">
                <div
                  v-for="(lesson, li) in chapter.lessons"
                  :key="li"
                  class="lesson-item"
                  :class="lesson.status"
                >
                  <div class="li-dot" :class="lesson.status" />
                  <div class="li-content">
                    <div class="li-name">
                      {{ lesson.name }}
                    </div>
                    <div class="li-meta">
                      <span class="li-type">{{ lesson.type }}</span>
                      <span class="li-time">{{ lesson.time }}</span>
                    </div>
                  </div>
                  <button class="li-action" :class="lesson.status">
                    <svg
                      v-if="lesson.status === 'done'"
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                    >
                      <polyline points="20 6 9 17 4 12" />
                    </svg>
                    <svg
                      v-else-if="lesson.status === 'active'"
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <polygon points="5 3 19 12 5 21 5 3" />
                    </svg>
                    <svg
                      v-else
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <circle cx="12" cy="12" r="10" />
                      <line x1="12" y1="8" x2="12" y2="12" />
                      <line x1="12" y1="16" x2="12.01" y2="16" />
                    </svg>
                  </button>
                </div>
              </div>
            </transition>
          </div>
        </div>
      </div>

      <!-- Right panel -->
      <div class="path-sidebar">
        <!-- Agent insight -->
        <div class="card insight-card">
          <div class="ic-header">
            <div class="agent-avatar" style="width: 28px; height: 28px">
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                stroke-width="2"
              >
                <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </div>
            <div>
              <div class="ic-title">Agent 洞察</div>
              <div class="ic-time">刚刚分析</div>
            </div>
          </div>
          <p class="ic-text">
            你在 <strong>第4章·图论</strong> 卡了 3
            天，建议先复习第3章的递归基础，再继续前进。预计2天可以突破。
          </p>
        </div>

        <!-- Stats -->
        <div class="card path-stats-card">
          <div class="panel-title" style="margin-bottom: 12px">学习统计</div>
          <div class="ps-list">
            <div v-for="s in pathStats" :key="s.label" class="ps-item">
              <div class="ps-icon" :style="{ color: s.color }">
                <span v-html="s.icon" />
              </div>
              <div class="ps-info">
                <div class="ps-val">
                  {{ s.value }}
                </div>
                <div class="ps-label">
                  {{ s.label }}
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Milestones -->
        <div class="card milestone-card">
          <div class="panel-title" style="margin-bottom: 12px">里程碑</div>
          <div class="milestone-list">
            <div
              v-for="m in milestones"
              :key="m.id"
              class="milestone-item"
              :class="{ achieved: m.done }"
            >
              <div class="mi-icon">
                {{ m.emoji }}
              </div>
              <div class="mi-info">
                <div class="mi-name">
                  {{ m.name }}
                </div>
                <div class="mi-desc">
                  {{ m.desc }}
                </div>
              </div>
              <div v-if="m.done" class="mi-check">
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="3"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";

const activeCourse = ref(1);
const expandedChapters = ref([1]);

const courses = [
  {
    id: 1,
    name: "数据结构与算法",
    color: "#6366f1",
    done: 7,
    total: 12,
    percent: 58,
    eta: "3周",
  },
  {
    id: 2,
    name: "高等数学",
    color: "#f59e0b",
    done: 5,
    total: 11,
    percent: 45,
    eta: "4周",
  },
  {
    id: 3,
    name: "机器学习",
    color: "#10b981",
    done: 2,
    total: 10,
    percent: 20,
    eta: "8周",
  },
];

const currentCourse = computed(() =>
  courses.find((c) => c.id === activeCourse.value),
);

function toggleChapter(ci) {
  const idx = expandedChapters.value.indexOf(ci);
  if (idx === -1) expandedChapters.value.push(ci);
  else expandedChapters.value.splice(idx, 1);
}

function getChapterStyle(status) {
  if (status === "done")
    return { background: "#10b981", color: "white", border: "none" };
  if (status === "active")
    return {
      background: "var(--gradient-brand)",
      color: "white",
      border: "none",
    };
  return {
    background: "var(--bg-hover)",
    color: "var(--text-dim)",
    border: "1px solid var(--border)",
  };
}

function getStatusBadge(s) {
  return s === "done" ? "badge-green" : s === "active" ? "badge-brand" : "";
}
function getStatusText(s) {
  return s === "done" ? "已完成" : s === "active" ? "进行中" : "未解锁";
}

const pathStats = [
  {
    label: "已学习时长",
    value: "46.5h",
    color: "#6366f1",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  },
  {
    label: "完成节点数",
    value: "28",
    color: "#10b981",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`,
  },
  {
    label: "练习正确率",
    value: "84%",
    color: "#f59e0b",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2"/></svg>`,
  },
  {
    label: "连续打卡",
    value: "47天",
    color: "#a855f7",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/></svg>`,
  },
];

const milestones = [
  { id: 1, emoji: "🚀", name: "起步", desc: "完成第一个学习节点", done: true },
  { id: 2, emoji: "🔥", name: "连续一周", desc: "坚持学习 7 天", done: true },
  { id: 3, emoji: "⚡", name: "算法入门", desc: "完成前3章学习", done: true },
  { id: 4, emoji: "🎯", name: "过半进度", desc: "完成课程 50%", done: false },
  {
    id: 5,
    emoji: "🏆",
    name: "课程完结",
    desc: "完成全部学习路径",
    done: false,
  },
];
</script>

<style scoped>
.path-page {
  padding: 28px 32px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 24px;
}
.page-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
  margin-bottom: 4px;
}
.page-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
}
.header-right {
  display: flex;
  gap: 8px;
}

/* Course tabs */
.course-tabs {
  display: flex;
  gap: 8px;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.course-tab {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: var(--radius-full);
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
}
.course-tab:hover {
  border-color: var(--border-hover);
  color: var(--text-primary);
}
.course-tab.active {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}
.ct-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}
.ct-progress {
  font-size: 10px;
  opacity: 0.6;
  margin-left: 2px;
}

/* Layout */
.path-layout {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 16px;
  align-items: start;
}

/* Overall progress */
.path-overall {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px 20px;
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 16px;
}
.po-label {
  font-size: 12px;
  color: var(--text-muted);
}
.po-val {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -1px;
}
.po-eta {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: auto;
}
.po-eta strong {
  color: var(--text-primary);
}

/* Chapters */
.path-chapter {
  margin-bottom: 4px;
}

.chapter-header {
  display: flex;
  align-items: center;
  gap: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  cursor: pointer;
  transition: var(--transition);
  position: relative;
}
.chapter-header:hover {
  border-color: var(--border-hover);
}

.ch-icon {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  margin-right: 12px;
}
.ch-connector {
  display: none;
}

.ch-info {
  flex: 1;
}
.ch-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}
.ch-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}
.ch-stats {
  font-size: 11px;
  color: var(--text-muted);
}

.ch-chevron {
  color: var(--text-dim);
  transition: transform 0.2s ease;
}
.ch-chevron.open {
  transform: rotate(180deg);
}

/* Lessons */
.lessons-list {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-top: none;
  border-radius: 0 0 var(--radius-md) var(--radius-md);
  overflow: hidden;
  margin-bottom: 4px;
}

.lesson-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 16px 10px 24px;
  border-bottom: 1px solid var(--border);
  transition: var(--transition);
}
.lesson-item:last-child {
  border-bottom: none;
}
.lesson-item:hover {
  background: var(--bg-hover);
}
.lesson-item.locked {
  opacity: 0.4;
}

.li-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.li-dot.done {
  background: var(--green);
}
.li-dot.active {
  background: var(--brand);
}
.li-dot.locked {
  background: var(--text-dim);
}

.li-content {
  flex: 1;
}
.li-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}
.li-meta {
  display: flex;
  gap: 8px;
  margin-top: 2px;
}
.li-type {
  font-size: 10px;
  color: var(--brand-light);
  background: var(--brand-dim);
  padding: 1px 6px;
  border-radius: 3px;
}
.li-time {
  font-size: 10px;
  color: var(--text-muted);
}

.li-action {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  cursor: pointer;
  flex-shrink: 0;
  transition: var(--transition);
}
.li-action.done {
  background: var(--green-dim);
  color: var(--green);
}
.li-action.active {
  background: var(--gradient-brand);
  color: white;
}
.li-action.locked {
  background: var(--bg-hover);
  color: var(--text-dim);
}

/* Expand transition */
.expand-enter-active,
.expand-leave-active {
  transition: all 0.25s ease;
  max-height: 600px;
}
.expand-enter-from,
.expand-leave-to {
  opacity: 0;
  max-height: 0;
}

/* Sidebar cards */
.path-sidebar {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.insight-card {
  padding: 16px;
  background: linear-gradient(
    135deg,
    rgba(99, 102, 241, 0.08),
    rgba(168, 85, 247, 0.08)
  );
  border-color: rgba(99, 102, 241, 0.2);
}
.ic-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.ic-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--brand-light);
}
.ic-time {
  font-size: 10px;
  color: var(--text-dim);
}
.ic-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.7;
}
.ic-text strong {
  color: var(--brand-light);
}

.path-stats-card {
  padding: 16px;
}
.ps-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ps-item {
  display: flex;
  align-items: center;
  gap: 10px;
}
.ps-icon {
  display: flex;
  align-items: center;
}
.ps-val {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}
.ps-label {
  font-size: 10px;
  color: var(--text-muted);
}

.milestone-card {
  padding: 16px;
}
.milestone-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.milestone-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  opacity: 0.5;
  transition: var(--transition);
}
.milestone-item.achieved {
  opacity: 1;
  background: var(--brand-dim);
}
.mi-icon {
  font-size: 18px;
}
.mi-info {
  flex: 1;
}
.mi-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}
.mi-desc {
  font-size: 10px;
  color: var(--text-muted);
}
.mi-check {
  color: var(--green);
}

.panel-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
</style>
