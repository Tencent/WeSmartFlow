<template>
  <div class="page-wrapper">
    <!-- Page header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">学习历史</h1>
        <p class="page-subtitle">回顾每一次学习会话，追踪知识图谱的成长轨迹</p>
      </div>
      <div class="header-right">
        <div class="search-bar">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input v-model="searchQuery" placeholder="搜索会话..." />
        </div>
        <button class="btn btn-primary" @click="$router.push('/chat')">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <path
              d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
            />
          </svg>
          开始学习
        </button>
      </div>
    </div>

    <!-- Stats bar -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-val text-gradient">{{ sessions.length }}</span>
        <span class="stat-label">总会话数</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-val">{{ totalMinutes }}</span>
        <span class="stat-label">学习总时长（分钟）</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-val" style="color: var(--green)">{{
          totalNewNodes
        }}</span>
        <span class="stat-label">新增节点数</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-val" style="color: var(--yellow)">{{
          totalFileCount
        }}</span>
        <span class="stat-label">生成文档数</span>
      </div>
    </div>

    <!-- Main layout -->
    <div class="main-layout">
      <!-- Session list -->
      <div class="session-list">
        <div
          v-for="(group, date) in groupedSessions"
          :key="date"
          class="session-group"
        >
          <div class="group-date">
            {{ date }}
          </div>
          <div
            v-for="s in group"
            :key="s.id"
            class="session-card"
            :class="{ active: activeSession?.id === s.id }"
            @click="activeSession = s"
          >
            <!-- Mode icon -->
            <div
              class="session-mode"
              :class="s.isImmersive ? 'immersive' : 'chat'"
            >
              <svg
                v-if="s.isImmersive"
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M4 19.5A2.5 2.5 0 016.5 17H20" />
                <path
                  d="M6.5 2H20v20H6.5A2.5 2.5 0 014 19.5v-15A2.5 2.5 0 016.5 2z"
                />
              </svg>
              <svg
                v-else
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path
                  d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
                />
              </svg>
            </div>

            <!-- Info -->
            <div class="session-info">
              <div class="session-title">
                {{ s.displayTitle }}
              </div>
              <div class="session-meta">
                <span class="session-time">{{ formatTime(s.started_at) }}</span>
                <span class="session-dot">·</span>
                <span>{{
                  s.duration_minutes > 0
                    ? s.duration_minutes + " 分钟"
                    : "时长未记录"
                }}</span>
                <span class="session-dot">·</span>
                <span>{{ s.message_count }} 条消息</span>
                <template v-if="s.fileCount > 0">
                  <span class="session-dot">·</span>
                  <span>{{ s.fileCount }} 份文档</span>
                </template>
              </div>
            </div>

            <!-- New nodes badge -->
            <div v-if="s.new_node_ids?.length" class="new-nodes-badge">
              +{{ s.new_node_ids.length }} 节点
            </div>
          </div>
        </div>

        <!-- Empty state -->
        <div v-if="filteredSessions.length === 0" class="empty-state">
          <div class="empty-icon">📚</div>
          <div class="empty-title">还没有学习记录</div>
          <div class="empty-desc">
            开始你的第一次学习之旅<br />每次学习都会记录在这里
          </div>
          <button class="btn btn-primary" @click="$router.push('/chat')">
            开始学习
          </button>
        </div>
      </div>

      <!-- Session detail -->
      <div v-if="activeSession" class="session-detail">
        <!-- Header -->
        <div class="detail-header">
          <div class="detail-title">
            {{ activeSession.displayTitle }}
          </div>
          <div class="detail-meta">
            <span
              class="mode-tag"
              :class="activeSession.isImmersive ? 'immersive' : 'chat'"
              >{{
                activeSession.isImmersive ? "📚 AI主导学习" : "🤝 人机交互学习"
              }}</span
            >
            <span>{{ formatDate(activeSession.started_at) }}</span>
            <span v-if="activeSession.duration_minutes > 0"
              >{{ activeSession.duration_minutes }} 分钟</span
            >
            <span v-else style="color: var(--text-dim)">时长未记录</span>
            <span>{{ activeSession.message_count }} 条消息</span>
          </div>
        </div>

        <!-- New nodes -->
        <div v-if="activeSession.new_node_ids?.length" class="detail-section">
          <div class="section-title">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="16" />
              <line x1="8" y1="12" x2="16" y2="12" />
            </svg>
            新增节点
          </div>
          <div class="new-nodes">
            <div
              v-for="nodeId in activeSession.new_node_ids"
              :key="nodeId"
              class="new-node-chip"
            >
              <span>🆕</span>
              <span>{{ nodeMap[nodeId] || nodeId }}</span>
            </div>
          </div>
        </div>

        <!-- 生成的文档 -->
        <div v-if="activeSession.files?.length" class="detail-section">
          <div class="section-title">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
            生成的文档 ({{ activeSession.files.length }})
          </div>
          <div class="slides-list">
            <div
              v-for="f in activeSession.files"
              :key="f.file_id"
              class="slide-item"
              style="cursor: pointer"
              @click="$router.push('/documents')"
            >
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="var(--red)"
                stroke-width="2"
              >
                <path
                  d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"
                />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              <div class="slide-title">
                {{ f.title || "未命名文档" }}
              </div>
              <svg
                width="11"
                height="11"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                style="flex-shrink: 0"
              >
                <polyline points="9 18 15 12 9 6" />
              </svg>
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="detail-actions">
          <button class="btn btn-ghost" style="flex: 1" @click="resumeSession">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
              />
            </svg>
            继续这个主题
          </button>
          <button
            class="btn btn-ghost"
            style="flex: 1"
            @click="$router.push('/quiz')"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
            </svg>
            出题练习
          </button>
        </div>
      </div>

      <!-- Empty detail -->
      <div v-else class="empty-detail">
        <div class="empty-icon">🕐</div>
        <div class="empty-title">选择一个会话</div>
        <div class="empty-desc">查看学习详情、掌握度变化和生成的卡片</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { useRouter } from "vue-router";
import { sessionApi, nodeApi } from "@/api";

const router = useRouter();
const searchQuery = ref("");

// ── 数据（从后端加载）──────────────────────────────────────────
const sessions = ref([]);
const loading = ref(false);
const nodeMap = ref({}); // { [node_id]: title }

async function loadSessions() {
  loading.value = true;
  try {
    // 并行加载会话列表和节点列表
    const [raw, nodes] = await Promise.all([
      sessionApi.getAll(),
      nodeApi.getAll().catch(() => []),
    ]);
    // 建立节点 id -> title 映射
    nodeMap.value = Object.fromEntries(nodes.map((n) => [n.id, n.title]));
    sessions.value = raw.map((s) => ({
      ...s,
      isImmersive: (s.title || "").startsWith("[AI课程]"),
      displayTitle: (s.title || "").startsWith("[AI课程]")
        ? s.title.replace("[AI课程] ", "")
        : s.topic || s.title || "未命名会话",
      started_at: s.created_at,
      new_node_ids: s.node_ids_covered || [],
      fileCount: (s.files || []).length,
    }));
    if (sessions.value.length > 0) {
      activeSession.value = sessions.value[0];
    }
  } catch (e) {
    console.warn("会话列表加载失败:", e.message);
  } finally {
    loading.value = false;
  }
}

onMounted(loadSessions);

const activeSession = ref(null);

const filteredSessions = computed(() => {
  if (!searchQuery.value) return sessions.value;
  const q = searchQuery.value.toLowerCase();
  return sessions.value.filter((s) =>
    (s.displayTitle || "").toLowerCase().includes(q),
  );
});

const groupedSessions = computed(() => {
  const groups = {};
  filteredSessions.value.forEach((s) => {
    const date = formatGroupDate(s.started_at);
    if (!groups[date]) groups[date] = [];
    groups[date].push(s);
  });
  return groups;
});

const totalMinutes = computed(() =>
  sessions.value.reduce((sum, s) => sum + s.duration_minutes, 0),
);
const totalNewNodes = computed(() => {
  const ids = new Set();
  sessions.value.forEach((s) => s.new_node_ids?.forEach((id) => ids.add(id)));
  return ids.size;
});
const totalFileCount = computed(() =>
  sessions.value.reduce((sum, s) => sum + (s.files?.length || 0), 0),
);

function formatTime(iso) {
  const d = new Date(iso);
  return d.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
}

function formatDate(iso) {
  const d = new Date(iso);
  return d.toLocaleDateString("zh-CN", {
    month: "long",
    day: "numeric",
    weekday: "short",
  });
}

function formatGroupDate(iso) {
  const d = new Date(iso);
  const today = new Date();
  const diff = Math.floor((today - d) / 86400000);
  if (diff === 0) return "今天";
  if (diff === 1) return "昨天";
  return d.toLocaleDateString("zh-CN", { month: "long", day: "numeric" });
}

function resumeSession() {
  if (activeSession.value) {
    router.push({
      path: "/chat",
      query: { session_id: activeSession.value.id },
    });
  }
}
</script>

<style scoped>
@import "@/styles/page-list.css";

/* ===== SessionsView 独有样式 ===== */

/* 顶部搜索框宁愿更窄 */
.search-bar input {
  width: 160px;
}

/* Main layout */
.main-layout {
  display: grid;
  grid-template-columns: 1fr 360px;
  gap: 16px;
  flex: 1;
}

/* Session list */
.session-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.session-group {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.group-date {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-dim);
  letter-spacing: 0.05em;
  text-transform: uppercase;
  padding: 0 4px;
  margin-bottom: 2px;
}

.session-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition);
}
.session-card:hover {
  border-color: var(--border-hover);
  background: var(--bg-card);
}
.session-card.active {
  border-color: var(--brand);
  background: var(--brand-dim);
}

.session-mode {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.session-mode.chat {
  background: rgba(99, 102, 241, 0.1);
  color: var(--brand-light);
}
.session-mode.immersive {
  background: rgba(168, 85, 247, 0.1);
  color: #a855f7;
}
.session-mode.courseware {
  background: rgba(239, 68, 68, 0.1);
  color: var(--red);
}

.session-info {
  flex: 1;
  min-width: 0;
}
.session-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-dim);
}
.session-dot {
  color: var(--text-dim);
}

.session-delta {
  text-align: right;
  flex-shrink: 0;
}
.delta-val {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--green);
}
.delta-label {
  font-size: 10px;
  color: var(--text-dim);
}

.new-nodes-badge {
  padding: 3px 8px;
  background: var(--brand-dim);
  color: var(--brand-light);
  border-radius: var(--radius-full);
  font-size: 10px;
  font-weight: 500;
  flex-shrink: 0;
}

/* Detail panel */
.session-detail {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  height: fit-content;
  position: sticky;
  top: 16px;
}

.detail-header {
}
.detail-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.3px;
  margin-bottom: 8px;
}
.detail-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  color: var(--text-secondary);
}
.mode-tag {
  padding: 2px 8px;
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 500;
}
.mode-tag.chat {
  background: var(--brand-dim);
  color: var(--brand-light);
}
.mode-tag.immersive {
  background: rgba(168, 85, 247, 0.1);
  color: #a855f7;
}
.mode-tag.courseware {
  background: var(--red-dim);
  color: var(--red);
}

.detail-section {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.section-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

/* Mastery bars */
.mastery-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mastery-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mastery-node {
  font-size: 11px;
  color: var(--text-secondary);
  width: 80px;
  flex-shrink: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mastery-bar-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 4px;
}
.mastery-bar-bg {
  flex: 1;
  height: 5px;
  background: var(--bg-hover);
  border-radius: 3px;
  overflow: hidden;
}
.mastery-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}
.mastery-bar-fill.before {
  background: var(--bg-active);
}
.mastery-numbers {
  font-size: 11px;
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  width: 70px;
  justify-content: flex-end;
}

/* New nodes */
.new-nodes {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.new-node-chip {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  background: var(--green-dim);
  color: var(--green);
  border-radius: var(--radius-full);
  font-size: 11px;
  font-weight: 500;
}

/* Slides list */
.slides-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.slide-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 10px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
}
.slide-type-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.slide-type-dot.type-cover {
  background: var(--brand);
}
.slide-type-dot.type-concept {
  background: var(--green);
}
.slide-type-dot.type-code {
  background: var(--yellow);
}
.slide-type-dot.type-quiz {
  background: var(--red);
}
.slide-type-dot.type-summary {
  background: var(--text-muted);
}
.slide-title {
  flex: 1;
  font-size: 12px;
  color: var(--text-primary);
}
.slide-type-label {
  font-size: 10px;
  color: var(--text-dim);
  flex-shrink: 0;
}

/* PDF card */
.pdf-card {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition);
  font-size: 12px;
  color: var(--text-secondary);
}
.pdf-card:hover {
  border-color: var(--border-hover);
  background: var(--bg-card);
}

/* Detail actions */
.detail-actions {
  display: flex;
  gap: 8px;
}

/* Empty states */
.empty-state,
.empty-detail {
  padding: 48px 24px;
  gap: 10px;
}
.empty-icon {
  font-size: 36px;
}
.empty-detail {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  height: fit-content;
  position: sticky;
  top: 16px;
}
</style>
