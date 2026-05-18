<template>
  <div class="dashboard page-std">
    <!-- Header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">{{ greeting }}，{{ userName }} 👋</h1>
        <p class="page-subtitle">
          连续打卡
          <strong style="color: var(--brand-light)"
            >{{ stats.streak_days }} 天</strong
          >
          · 今天继续保持
        </p>
      </div>
      <div class="header-actions">
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

    <!-- 快捷入口 -->
    <div class="quick-entries">
      <div
        v-for="entry in quickEntries"
        :key="entry.path"
        class="qe-card"
        :style="{ '--accent': entry.color }"
        @click="$router.push(entry.path)"
      >
        <div class="qe-icon">
          {{ entry.icon }}
        </div>
        <div class="qe-info">
          <div class="qe-title">
            {{ entry.title }}
          </div>
          <div class="qe-desc">
            {{ entry.desc }}
          </div>
        </div>
        <svg
          class="qe-arrow"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <polyline points="9 18 15 12 9 6" />
        </svg>
      </div>
    </div>

    <!-- 主内容区：三列 -->
    <div class="content-grid">
      <!-- 左列：AI推荐 + 今日任务 -->
      <div class="col-left">
        <!-- AI 推荐 -->
        <div class="ai-rec-card card">
          <div class="arc-header">
            <div class="arc-agent">
              <div class="agent-avatar" style="width: 32px; height: 32px">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="white"
                  stroke-width="2"
                >
                  <path d="M12 2a10 10 0 100 20A10 10 0 0012 2z" />
                  <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </div>
              <div>
                <div class="arc-name">Agent 推荐</div>
                <div class="arc-time">
                  {{ aiRec.focus ? "今日个性化" : "加载中..." }}
                </div>
              </div>
            </div>
            <span class="badge badge-brand">个性化</span>
          </div>
          <!-- 加载中骨架 -->
          <div v-if="briefLoading" class="arc-skeleton">
            <div class="skeleton-line" style="width: 90%" />
            <div class="skeleton-line" style="width: 70%; margin-top: 6px" />
          </div>
          <!-- 真实内容 -->
          <p
            v-else-if="aiRec.text"
            class="arc-text"
            v-html="
              aiRec.text.replace(aiRec.focus, `<strong>${aiRec.focus}</strong>`)
            "
          />
          <p v-else class="arc-text" style="color: var(--text-dim)">
            你还没有学习记录，去
            <strong
              style="color: var(--brand-light); cursor: pointer"
              @click="$router.push('/chat')"
              >人机交互学习</strong
            >
            开始第一次学习，Agent 将根据你的知识图谱为你生成个性化建议。
          </p>
          <div v-if="aiRec.focus" class="arc-meta">
            <span class="arc-focus">🎯 {{ aiRec.focus }}</span>
            <span v-if="aiRec.minutes" class="arc-minutes"
              >⏱ 约 {{ aiRec.minutes }} 分钟</span
            >
          </div>
          <div class="arc-actions">
            <button
              class="btn btn-primary btn-sm"
              @click="$router.push('/chat')"
            >
              立即学习
            </button>
            <button
              class="btn btn-ghost btn-sm"
              @click="$router.push('/graph')"
            >
              查看图谱
            </button>
          </div>
        </div>
        <!-- 今日任务 -->
        <div class="card section-card">
          <div class="section-header">
            <h2 class="section-title">今日任务</h2>
            <span class="badge badge-brand">Agent 生成</span>
          </div>
          <!-- 加载中骨架 -->
          <div v-if="briefLoading" class="task-list">
            <div v-for="i in 3" :key="i" class="task-skeleton">
              <div class="skeleton-circle" />
              <div style="flex: 1">
                <div class="skeleton-line" style="width: 80%" />
                <div
                  class="skeleton-line"
                  style="width: 50%; margin-top: 5px"
                />
              </div>
            </div>
          </div>
          <!-- 空状态 -->
          <div v-else-if="tasks.length === 0" class="task-empty">
            <span>📚</span>
            <span
              >先去
              <a class="task-empty-link" @click.stop="$router.push('/chat')"
                >人机交互学习</a
              >
              学习或上传文档，Agent 将为你生成今日任务</span
            >
          </div>
          <!-- 任务列表 -->
          <div v-else class="task-list">
            <div
              v-for="task in tasks"
              :key="task._id"
              class="task-item"
              :class="{ done: task.done }"
              @click="task.done = !task.done"
            >
              <div class="task-check" :class="{ checked: task.done }">
                <svg
                  v-if="task.done"
                  width="9"
                  height="9"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="white"
                  stroke-width="3"
                >
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </div>
              <div class="task-content">
                <div class="task-name">
                  {{ task.name }}
                </div>
                <div class="task-meta">
                  <span
                    class="badge"
                    :class="
                      task.type === 'review' ? 'badge-yellow' : 'badge-brand'
                    "
                    style="font-size: 10px; padding: 1px 6px"
                    >{{ task.tag }}</span
                  >
                  <span style="font-size: 11px; color: var(--text-dim)"
                    >约 {{ task.estimated_minutes }} 分钟</span
                  >
                </div>
              </div>
              <div v-if="!task.done" class="task-right">
                <span class="task-type-icon">{{
                  task.type === "review" ? "🔄" : "📖"
                }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 中列：知识图谱概览 + 遗忘提醒 -->
      <div class="col-mid">
        <!-- 知识图谱概览 -->
        <div class="card section-card">
          <div class="section-header">
            <h2 class="section-title">知识图谱概览</h2>
            <button class="link-btn" @click="$router.push('/graph')">
              查看全图 →
            </button>
          </div>
          <div class="graph-preview">
            <div v-for="s in subjectStats" :key="s.name" class="gp-subject">
              <div class="gps-header">
                <span class="gps-dot" :style="{ background: s.color }" />
                <span class="gps-name">{{ s.name }}</span>
                <span class="gps-count">{{ s.count }} 个概念</span>
                <span class="gps-avg" :style="{ color: s.color }"
                  >{{ s.avg }}%</span
                >
              </div>
              <div class="progress-bar">
                <div
                  class="progress-fill"
                  :style="{ width: s.avg + '%', background: s.color }"
                />
              </div>
            </div>
          </div>
          <div class="gp-total">
            <div class="gpt-item">
              <div class="gpt-val text-gradient">
                {{ stats.total_nodes }}
              </div>
              <div class="gpt-label">已解锁概念</div>
            </div>
            <div class="gpt-divider" />
            <div class="gpt-item">
              <div class="gpt-val text-gradient">
                {{
                  stats.total_nodes
                    ? Math.round(
                        (stats.mastered_nodes / stats.total_nodes) * 100,
                      )
                    : 0
                }}%
              </div>
              <div class="gpt-label">已掌握比例</div>
            </div>
            <div class="gpt-divider" />
            <div class="gpt-item">
              <div class="gpt-val text-gradient">
                {{ stats.due_today }}
              </div>
              <div class="gpt-label">待复习今日</div>
            </div>
          </div>
        </div>

        <!-- 遗忘曲线提醒 -->
        <div class="card section-card review-card">
          <div class="section-header">
            <h2 class="section-title">遗忘曲线提醒</h2>
            <span class="badge badge-yellow">{{ reviewItems.length }} 个</span>
          </div>
          <div class="review-list">
            <div v-for="r in reviewItems" :key="r.id" class="review-item">
              <span class="review-emoji">{{ r.emoji }}</span>
              <div class="review-info">
                <div class="review-name">
                  {{ r.name }}
                </div>
                <div class="review-urgency" :class="r.urgency">
                  {{ r.urgencyText }}
                </div>
              </div>
              <button class="review-btn" @click="$router.push('/chat')">
                复习
              </button>
            </div>
          </div>
        </div>
      </div>

      <!-- 右列：热力图 + 最近会话 -->
      <div class="col-right">
        <!-- 学习热力图 -->
        <div class="card section-card">
          <div class="section-header">
            <h2 class="section-title">学习热力图</h2>
            <span style="font-size: 11px; color: var(--text-dim)"
              >最近 3 个月</span
            >
          </div>
          <div class="heatmap-wrap">
            <div class="heatmap-weekdays">
              <span>Sun</span><span /><span>Tue</span> <span /><span>Thu</span
              ><span /><span>Sat</span>
            </div>
            <div class="heatmap-grid">
              <div v-for="(week, wi) in heatmapWeeks" :key="wi" class="hm-col">
                <div
                  v-for="(cell, di) in week"
                  :key="di"
                  class="hm-cell"
                  :class="{
                    'hm-empty': !cell,
                    'hm-today': cell?.isToday,
                    'hm-lv0': cell && cell.minutes === 0,
                    'hm-lv1': cell && cell.minutes > 0 && cell.minutes <= 30,
                    'hm-lv2': cell && cell.minutes > 30 && cell.minutes <= 60,
                    'hm-lv3': cell && cell.minutes > 60 && cell.minutes <= 120,
                    'hm-lv4': cell && cell.minutes > 120,
                  }"
                  :title="
                    cell
                      ? cell.isToday
                        ? `今天 · ${cell.minutes}min`
                        : `${cell.month}/${cell.day} · ${cell.minutes}min`
                      : ''
                  "
                />
              </div>
            </div>
          </div>
          <div class="hm-legend">
            <span>少</span>
            <div class="hml-cells">
              <div class="hml-cell hm-lv0" />
              <div class="hml-cell hm-lv1" />
              <div class="hml-cell hm-lv2" />
              <div class="hml-cell hm-lv3" />
              <div class="hml-cell hm-lv4" />
            </div>
            <span>多</span>
          </div>
        </div>

        <!-- 最近会话 -->
        <div class="card section-card">
          <div class="section-header">
            <h2 class="section-title">最近学习会话</h2>
            <button class="link-btn" @click="$router.push('/sessions')">
              查看全部 →
            </button>
          </div>
          <div class="session-list">
            <div
              v-for="s in sessions"
              :key="s.id"
              class="session-item"
              @click="$router.push('/sessions')"
            >
              <div
                class="si-icon"
                :style="{ background: s.color + '18', color: s.color }"
              >
                {{ s.emoji }}
              </div>
              <div class="si-info">
                <div class="si-title">
                  {{ s.title }}
                </div>
                <div class="si-meta">{{ s.duration }}分钟 · {{ s.time }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from "vue";
import { useRoute } from "vue-router";
import { userApi, nodeApi } from "@/api";

// ── 静态数据 ───────────────────────────────────────────────────────────────
const quickEntries = [
  {
    path: "/chat",
    icon: "🤝",
    title: "人机交互学习",
    desc: "开启新的学习会话",
    color: "#6366f1",
  },
  {
    path: "/immersive",
    icon: "📚",
    title: "AI主导学习",
    desc: "自动生成完整课件",
    color: "#8b5cf6",
  },
  {
    path: "/graph",
    icon: "🕸️",
    title: "知识图谱",
    desc: "查看你的知识版图",
    color: "#a855f7",
  },
  {
    path: "/quiz",
    icon: "✅",
    title: "智能出题",
    desc: "针对薄弱点练习",
    color: "#10b981",
  },
];

// 今日任务（来自后端 AI 生成，前端维护 done 状态）
const tasks = ref([]);
// AI 推荐
const aiRec = ref({});
// 简报加载状态
const briefLoading = ref(true);

// ── 后端数据 ───────────────────────────────────────────────────────────────
const userName = ref("");
const stats = ref({
  total_nodes: 0,
  mastered_nodes: 0,
  due_today: 0,
  streak_days: 0,
});
const studyLogs = ref([]); // [{ date: 'YYYY-MM-DD', minutes: N }]
const recentSessions = ref([]);
const dueNodes = ref([]); // 今日待复习节点

// ── Dashboard 数据加载 ──────────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const [data, userInfo] = await Promise.all([
      userApi.getDashboard(),
      userApi.getMe(),
    ]);
    userName.value = userInfo.name || "User";
    stats.value = data;
    studyLogs.value = data.study_logs || [];
    recentSessions.value = data.recent_sessions || [];
    // AI 生成的任务和推荐
    tasks.value = (data.tasks || []).map((t, i) => ({
      ...t,
      _id: i,
      done: false,
    }));
    aiRec.value = data.ai_recommendation || {};
  } catch (e) {
    console.warn("Dashboard 数据加载失败:", e.message);
  } finally {
    briefLoading.value = false;
  }
}

async function loadDueNodes() {
  try {
    dueNodes.value = await nodeApi.getDue();
  } catch (e) {
    console.warn("待复习节点加载失败:", e.message);
  }
}

onMounted(() => {
  loadDashboard();
  loadDueNodes();
});

// 每次路由切换回 Dashboard 时重新加载数据（确保拿到最新的学习时长）
const route = useRoute();
watch(
  () => route.path,
  (newPath) => {
    if (newPath === "/") {
      // 稍作延迟，等 Chat 页面的 recordDuration 请求写入完成
      setTimeout(() => {
        loadDashboard();
      }, 500);
    }
  },
);

// ── 热力图计算 ─────────────────────────────────────────────────────────────
const today = new Date();
today.setHours(0, 0, 0, 0);

const startDay = new Date(today);
startDay.setDate(today.getDate() - 12 * 7 + 1);

function getWeekSunday(date) {
  const d = new Date(date);
  d.setDate(d.getDate() - d.getDay()); // 往前找周日
  return d;
}

const firstSunday = getWeekSunday(startDay);
const COLS = 13;

// studyLogs → Map<date, minutes>
const logMap = computed(() => {
  const m = {};
  for (const log of studyLogs.value) m[log.date] = log.minutes;
  return m;
});

// 用本地时间格式化日期，避免 toISOString() 转 UTC 导致日期偏移
function toLocalDateStr(date) {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

const heatmapWeeks = computed(() =>
  Array.from({ length: COLS }, (_, w) =>
    Array.from({ length: 7 }, (_, d) => {
      const date = new Date(firstSunday);
      date.setDate(firstSunday.getDate() + w * 7 + d);
      if (date < startDay || date > today) return null;
      const key = toLocalDateStr(date);
      return {
        minutes: logMap.value[key] ?? 0,
        month: date.getMonth() + 1,
        day: date.getDate(),
        isToday: date.getTime() === today.getTime(),
      };
    }),
  ),
);

// ── 知识图谱概览（从节点数据中计算） ──────────────────────────────────────
// 目前 tags 只有一级，按第一个 tag 聚合
const tagColors = {
  算法: "#6366f1",
  数据结构: "#10b981",
  AI: "#a855f7",
  ML: "#a855f7",
  数学: "#f59e0b",
  英语: "#3b82f6",
};
const defaultColors = [
  "#6366f1",
  "#10b981",
  "#a855f7",
  "#f59e0b",
  "#3b82f6",
  "#ef4444",
];

// 从 dueNodes 推断 subjectStats（轻量版）
const subjectStats = computed(() => {
  // 用后端 recent_sessions 的 tag 摘要，或直接取 due 节点的 tag 分组
  const groups = {};
  for (const node of dueNodes.value) {
    const tag = node.tags?.[0] || "其他";
    if (!groups[tag]) groups[tag] = { name: tag, count: 0, totalMastery: 0 };
    groups[tag].count++;
    groups[tag].totalMastery += node.mastery_level || 0;
  }

  return Object.values(groups)
    .slice(0, 5)
    .map((g, i) => ({
      name: g.name,
      color: tagColors[g.name] || defaultColors[i % defaultColors.length],
      count: g.count,
      avg: Math.round((g.totalMastery / g.count) * 100),
    }));
});

// ── 遗忘曲线提醒（从 dueNodes 提取） ──────────────────────────────────────
const REVIEW_EMOJIS = ["📊", "🕸️", "🧠", "📐", "📝", "🔬", "💡", "🎯"];
const reviewItems = computed(() =>
  dueNodes.value.slice(0, 5).map((node, i) => {
    const daysAgo = node.last_review_at
      ? Math.floor((Date.now() - new Date(node.last_review_at)) / 86400000)
      : null;
    let urgency = "normal",
      urgencyText = "建议今日复习";
    if (daysAgo === null) {
      urgency = "urgent";
      urgencyText = "⚠️ 从未复习";
    } else if (daysAgo >= 5) {
      urgency = "urgent";
      urgencyText = `⚠️ ${daysAgo}天未复习`;
    } else if (daysAgo >= 3) {
      urgency = "warn";
      urgencyText = `${daysAgo}天未复习`;
    }
    return {
      id: node.id,
      emoji: REVIEW_EMOJIS[i % REVIEW_EMOJIS.length],
      name: node.title,
      urgency,
      urgencyText,
    };
  }),
);

// ── 最近会话列表格式化 ──────────────────────────────────────────────────────
const SESSION_COLORS = ["#6366f1", "#10b981", "#a855f7", "#3b82f6", "#f59e0b"];
const SESSION_EMOJIS = ["🔄", "🌳", "✍️", "🧮", "🎯"];
const sessions = computed(() =>
  recentSessions.value.map((s, i) => ({
    id: s.id,
    emoji: SESSION_EMOJIS[i % SESSION_EMOJIS.length],
    title: s.title || `${s.mode === "tutoring" ? "人机交互学习" : "学习"}会话`,
    time: formatRelTime(s.created_at),
    color: s.title?.startsWith("[AI课程]")
      ? "#8b5cf6"
      : SESSION_COLORS[i % SESSION_COLORS.length],
    duration: s.duration_minutes,
  })),
);

function formatRelTime(isoStr) {
  if (!isoStr) return "";
  const d = new Date(isoStr);
  const diff = Math.floor((Date.now() - d) / 86400000);
  if (diff === 0)
    return `今天 ${d.getHours().toString().padStart(2, "0")}:${d.getMinutes().toString().padStart(2, "0")}`;
  if (diff === 1) return "昨天";
  return `${diff}天前`;
}

// ── 问候语 ─────────────────────────────────────────────────────────────────
const greeting = computed(() => {
  const h = new Date().getHours();
  if (h < 6) return "夜深了";
  if (h < 12) return "早上好";
  if (h < 18) return "下午好";
  return "晚上好";
});
</script>

<style scoped>
.dashboard {
}

/* Quick entries */
.quick-entries {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 20px;
}
.qe-card {
  display: flex;
  align-items: center;
  gap: 10px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 14px 16px;
  cursor: pointer;
  transition: var(--transition);
}
.qe-card:hover {
  border-color: var(--accent, var(--border-active));
  background: color-mix(
    in srgb,
    var(--accent, var(--brand)) 6%,
    var(--bg-card)
  );
  transform: translateY(-1px);
  box-shadow: var(--shadow-md);
}
.qe-icon {
  font-size: 22px;
  flex-shrink: 0;
}
.qe-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.qe-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 1px;
}
.qe-arrow {
  color: var(--text-dim);
  margin-left: auto;
  flex-shrink: 0;
  transition: var(--transition);
}
.qe-card:hover .qe-arrow {
  color: var(--accent, var(--brand-light));
  transform: translateX(2px);
}

/* Content grid - 3列 */
.content-grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 16px;
  align-items: start;
}
.col-left,
.col-mid,
.col-right {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Heatmap */
.heatmap-wrap {
  display: flex;
  gap: 4px;
  align-items: stretch;
  width: 100%;
}
.heatmap-weekdays {
  display: flex;
  flex-direction: column;
  font-size: 9px;
  color: var(--text-dim);
  flex-shrink: 0;
  text-align: right;
  justify-content: space-around;
  padding: 1px 0;
}
.heatmap-weekdays span {
  line-height: 1;
}
.heatmap-grid {
  display: flex;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.hm-col {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
  min-width: 0;
}
.hm-cell {
  flex: 1;
  aspect-ratio: 1;
  border-radius: 2px;
  cursor: pointer;
  transition: transform 0.12s;
  min-height: 0;
}
.hm-cell:hover:not(.hm-empty) {
  transform: scale(1.2);
}
.hm-empty {
  visibility: hidden;
}
.hm-lv0 {
  background: var(--bg-active);
}
.hm-lv1 {
  background: rgba(99, 102, 241, 0.25);
}
.hm-lv2 {
  background: rgba(99, 102, 241, 0.5);
}
.hm-lv3 {
  background: rgba(99, 102, 241, 0.75);
}
.hm-lv4 {
  background: #6366f1;
}
.hm-today {
  outline: 1.5px solid var(--text-primary);
  outline-offset: 1px;
}
.hm-legend {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 8px;
  justify-content: flex-end;
  font-size: 10px;
  color: var(--text-dim);
}
.hml-cells {
  display: flex;
  gap: 2px;
}
.hml-cell {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

/* AI Rec card */
.ai-rec-card {
  padding: 18px;
  background: linear-gradient(
    135deg,
    rgba(99, 102, 241, 0.07),
    rgba(168, 85, 247, 0.07)
  );
  border-color: rgba(99, 102, 241, 0.18);
}
.arc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.arc-agent {
  display: flex;
  align-items: center;
  gap: 8px;
}
.arc-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.arc-time {
  font-size: 10px;
  color: var(--text-dim);
}
.arc-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.75;
  margin-bottom: 14px;
}
.arc-text strong {
  color: var(--brand-light);
}
.arc-actions {
  display: flex;
  gap: 7px;
}

/* Section card */
.section-card {
  padding: 18px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.link-btn {
  font-size: 12px;
  color: var(--brand-light);
  background: none;
  border: none;
  cursor: pointer;
  opacity: 0.8;
}
.link-btn:hover {
  opacity: 1;
}

/* Tasks */
.task-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 0;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: var(--transition);
}
.task-item:last-child {
  border-bottom: none;
}
.task-item.done {
  opacity: 0.38;
}
.task-check {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  border: 1.5px solid var(--border-hover);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: var(--transition);
}
.task-check.checked {
  background: var(--gradient-brand);
  border-color: transparent;
}
.task-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 3px;
}
.task-item.done .task-name {
  text-decoration: line-through;
}
.task-meta {
  display: flex;
  align-items: center;
  gap: 6px;
}
.task-right {
  margin-left: auto;
}

/* Graph preview */
.graph-preview {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
}
.gp-subject {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gps-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}
.gps-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.gps-name {
  flex: 1;
  color: var(--text-secondary);
  font-weight: 500;
}
.gps-count {
  color: var(--text-dim);
  font-size: 11px;
}
.gps-avg {
  font-weight: 700;
  font-size: 12px;
}

.gp-total {
  display: flex;
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 12px;
  margin-top: 4px;
}
.gpt-item {
  flex: 1;
  text-align: center;
}
.gpt-val {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.5px;
}
.gpt-label {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 1px;
}
.gpt-divider {
  width: 1px;
  background: var(--border);
}

/* Sessions */
.session-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.session-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition);
}
.session-item:hover {
  background: var(--bg-hover);
}
.si-icon {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  flex-shrink: 0;
}
.si-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}
.si-meta {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 1px;
}
.si-mastery {
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}

/* 骨架屏 */
@keyframes shimmer {
  0% {
    background-position: -400px 0;
  }
  100% {
    background-position: 400px 0;
  }
}
.skeleton-line {
  height: 12px;
  border-radius: 4px;
  background: linear-gradient(
    90deg,
    var(--bg-active) 25%,
    var(--bg-hover) 50%,
    var(--bg-active) 75%
  );
  background-size: 400px 100%;
  animation: shimmer 1.4s infinite;
}
.arc-skeleton {
  padding: 4px 0 8px;
}
.task-skeleton {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 0;
  border-bottom: 1px solid var(--border);
}
.skeleton-circle {
  width: 16px;
  height: 16px;
  border-radius: 4px;
  flex-shrink: 0;
  background: var(--bg-active);
}

/* 任务空状态 */
.task-empty {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 0;
  color: var(--text-dim);
  font-size: 13px;
  justify-content: center;
}
.task-empty-link {
  color: var(--brand-light);
  cursor: pointer;
  text-decoration: underline;
}

/* 任务类型图标 */
.task-type-icon {
  font-size: 14px;
  flex-shrink: 0;
}

/* AI 推荐新字段 */
.arc-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.arc-focus {
  font-size: 12px;
  font-weight: 600;
  color: var(--brand-light);
  background: var(--brand-dim);
  padding: 2px 8px;
  border-radius: var(--radius-full);
}
.arc-minutes {
  font-size: 11px;
  color: var(--text-dim);
}

/* Review */
.review-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.review-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
}
.review-emoji {
  font-size: 16px;
  flex-shrink: 0;
}
.review-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}
.review-urgency {
  font-size: 10px;
  margin-top: 1px;
}
.review-urgency.urgent {
  color: var(--red);
}
.review-urgency.warn {
  color: var(--yellow);
}
.review-urgency.normal {
  color: var(--text-muted);
}
.review-btn {
  margin-left: auto;
  padding: 3px 10px;
  border-radius: var(--radius-full);
  background: var(--brand-dim);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: var(--brand-light);
  font-size: 11px;
  cursor: pointer;
  transition: var(--transition);
  flex-shrink: 0;
}
.review-btn:hover {
  background: var(--brand);
  color: white;
}
</style>
