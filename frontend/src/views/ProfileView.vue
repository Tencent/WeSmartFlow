<template>
  <div class="profile-page">
    <!-- Hero section -->
    <div class="profile-hero">
      <div class="hero-bg" />
      <div class="hero-content">
        <div class="avatar-wrap">
          <div class="avatar-ring" />
          <div
            class="avatar"
            style="width: 80px; height: 80px; font-size: 28px; font-weight: 700"
          >
            {{ avatarChar }}
          </div>
          <div class="avatar-badge">
            <svg
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="white"
              stroke-width="3"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
          </div>
        </div>
        <div class="hero-info">
          <h1 class="hero-name">
            {{ userName }}
          </h1>
          <div class="hero-badges">
            <span v-if="dashboard?.streak_days" class="badge badge-yellow"
              >🔥 {{ dashboard.streak_days }}天连续</span
            >
          </div>
        </div>
        <div class="hero-actions">
          <button class="btn-icon-edit" title="编辑档案" @click="openEdit">
            <svg
              width="15"
              height="15"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"
              />
              <path
                d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"
              />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Edit modal -->
    <div v-if="showEdit" class="modal-mask" @click.self="showEdit = false">
      <div class="modal-box">
        <div class="modal-header">
          <span class="modal-title">编辑档案</span>
          <button class="modal-close" @click="showEdit = false">✕</button>
        </div>
        <div class="modal-body">
          <div class="edit-avatar-preview">
            <div
              class="avatar"
              style="
                width: 64px;
                height: 64px;
                font-size: 24px;
                font-weight: 700;
              "
            >
              {{ editName.charAt(0).toUpperCase() || "?" }}
            </div>
          </div>
          <div class="form-item">
            <label class="form-label">显示名称</label>
            <input
              v-model="editName"
              class="form-input"
              placeholder="输入你的名字"
              maxlength="20"
              @keyup.enter="saveEdit"
            />
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn-ghost" @click="showEdit = false">取消</button>
          <button
            class="btn btn-primary"
            :disabled="editSaving"
            @click="saveEdit"
          >
            {{ editSaving ? "保存中…" : "保存" }}
          </button>
        </div>
      </div>
    </div>

    <!-- Tab nav -->
    <div class="profile-tabs">
      <button
        v-for="t in tabs"
        :key="t"
        class="p-tab"
        :class="{ active: activeTab === t }"
        @click="activeTab = t"
      >
        {{ t }}
      </button>
    </div>

    <!-- Overview tab -->
    <div v-if="activeTab === '概览'" class="tab-content">
      <!-- Loading -->
      <div v-if="loading" class="loading-row">
        <div class="loading-dot" />
        <div class="loading-dot" />
        <div class="loading-dot" />
      </div>

      <template v-else>
        <!-- Big stats row -->
        <div class="big-stats">
          <div v-for="s in bigStats" :key="s.label" class="big-stat">
            <div class="bs-val text-gradient">
              {{ s.val }}
            </div>
            <div class="bs-label">
              {{ s.label }}
            </div>
            <div class="bs-sub">
              {{ s.sub }}
            </div>
          </div>
        </div>

        <div class="overview-grid">
          <!-- Weekly chart -->
          <div class="card ov-card">
            <div class="section-header">
              <h3 class="section-title">本周学习时长</h3>
            </div>
            <div class="bar-chart">
              <div class="bc-bars">
                <div v-for="(day, i) in weekData" :key="i" class="bc-bar-group">
                  <div class="bc-bar-wrap">
                    <div
                      class="bc-bar"
                      :style="{
                        height: (day.hours / maxHours) * 100 + '%',
                        background: day.today
                          ? 'var(--gradient-brand)'
                          : 'rgba(99,102,241,0.3)',
                      }"
                    >
                      <div
                        v-if="day.hours > 0"
                        class="bc-duration"
                        :class="{ 'bc-duration-today': day.today }"
                      >
                        {{
                          day.hours >= 1
                            ? Math.floor(day.hours) +
                              "h" +
                              (Math.round((day.hours % 1) * 60) > 0
                                ? Math.round((day.hours % 1) * 60) + "m"
                                : "")
                            : Math.round(day.hours * 60) + "m"
                        }}
                      </div>
                    </div>
                  </div>
                  <div class="bc-label" :class="{ today: day.today }">
                    {{ day.day }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Knowledge graph overview -->
          <div class="card ov-card">
            <div class="section-header">
              <h3 class="section-title">知识图谱概览</h3>
              <button class="link-btn" @click="$router.push('/graph')">
                查看图谱 →
              </button>
            </div>
            <!-- 无节点提示 -->
            <div v-if="!subjects.length" class="empty-tip">
              暂无知识节点，去学习吧 🚀
            </div>
            <!-- Subject rows -->
            <div v-else class="mastery-list">
              <div v-for="s in subjects" :key="s.name" class="mastery-row">
                <div class="mr-label">
                  <span class="mr-dot" :style="{ background: s.color }" />
                  <span>{{ s.name }}</span>
                  <span class="mr-nodes">{{ s.nodes }}个节点</span>
                </div>
                <div class="mr-bar">
                  <div class="progress-bar" style="flex: 1">
                    <div
                      class="progress-fill"
                      :style="{ width: s.mastery + '%', background: s.color }"
                    />
                  </div>
                  <span class="mr-val" :style="{ color: s.color }"
                    >{{ s.mastery }}%</span
                  >
                </div>
              </div>
            </div>
            <!-- Total stats -->
            <div class="graph-totals">
              <div class="gt-item">
                <div class="gt-val text-gradient">
                  {{ graphTotals.total }}
                </div>
                <div class="gt-label">知识节点</div>
              </div>
              <div class="gt-divider" />
              <div class="gt-item">
                <div class="gt-val text-gradient">
                  {{ graphTotals.edges }}
                </div>
                <div class="gt-label">关联边</div>
              </div>
              <div class="gt-divider" />
              <div class="gt-item">
                <div class="gt-val text-gradient">
                  {{ graphTotals.weak }}
                </div>
                <div class="gt-label">待突破</div>
              </div>
            </div>
          </div>
        </div>
      </template>
    </div>

    <!-- About Me tab -->
    <div v-if="activeTab === '关于我'" class="tab-content">
      <div class="about-form">
        <div class="about-header">
          <div class="about-header-text">
            <h3 class="about-title">关于我</h3>
            <p class="about-desc">
              这些信息会作为背景上下文提供给 AI，帮助它更好地了解你
            </p>
          </div>
          <button
            class="btn btn-primary about-save-btn"
            :disabled="aboutSaving"
            @click="saveAbout"
          >
            {{ aboutSaving ? "保存中…" : "保存" }}
          </button>
        </div>

        <div class="about-fields">
          <div v-for="f in aboutFields" :key="f.key" class="about-field">
            <label class="about-label">
              <span class="about-label-icon">{{ f.icon }}</span>
              <span>{{ f.label }}</span>
            </label>
            <p class="about-hint">
              {{ f.hint }}
            </p>
            <textarea
              v-model="aboutData[f.key]"
              class="about-textarea"
              :placeholder="f.placeholder"
              :rows="f.rows || 3"
            />
          </div>
        </div>

        <div v-if="aboutSaved" class="about-saved-tip">✓ 已保存</div>
      </div>
    </div>

    <!-- Achievements tab -->
    <div v-if="activeTab === '成就'" class="tab-content">
      <div class="achievements-grid">
        <div
          v-for="a in achievements"
          :key="a.id"
          class="ach-card card"
          :class="{ locked: !a.earned }"
        >
          <div class="ach-icon">
            {{ a.emoji }}
          </div>
          <div class="ach-info">
            <div class="ach-name">
              {{ a.name }}
            </div>
            <div class="ach-desc">
              {{ a.desc }}
            </div>
          </div>
          <div class="ach-status">
            <span v-if="a.earned" class="badge badge-green">已获得</span>
            <div v-else class="ach-progress-wrap">
              <div class="progress-bar" style="width: 80px">
                <div
                  class="progress-fill"
                  :style="{ width: a.progress + '%' }"
                />
              </div>
              <span class="ach-prog-val">{{ a.progress }}%</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";

const activeTab = ref("概览");
const tabs = ["概览", "成就", "关于我"];

// ── 用户信息（后端） ──────────────────────────────────────
const userInfo = ref(null); // UserSchema
const userName = computed(() => userInfo.value?.name || "User");
const avatarChar = computed(() => {
  const name = userInfo.value?.name || "U";
  return name.charAt(0).toUpperCase();
});

// 编辑弹窗
const showEdit = ref(false);
const editName = ref("");
const editSaving = ref(false);

function openEdit() {
  editName.value = userName.value;
  showEdit.value = true;
}

async function saveEdit() {
  if (!editName.value.trim()) return;
  editSaving.value = true;
  try {
    const res = await fetch("/api/user", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: editName.value.trim() }),
    });
    userInfo.value = await res.json();
    showEdit.value = false;
  } finally {
    editSaving.value = false;
  }
}

// ── 后端数据 ──────────────────────────────────────────────
const loading = ref(true);
const dashboard = ref(null); // DashboardStats
const allNodes = ref([]); // NodeBrief[]

async function fetchData() {
  try {
    const [userRes, dashRes, nodesRes] = await Promise.all([
      fetch("/api/user"),
      fetch("/api/user/dashboard"),
      fetch("/api/nodes"),
    ]);
    userInfo.value = await userRes.json();
    dashboard.value = await dashRes.json();
    allNodes.value = await nodesRes.json();
    // 同步 about 数据
    if (userInfo.value?.about) {
      Object.assign(aboutData.value, userInfo.value.about);
    }
  } catch (e) {
    console.error("Profile 数据加载失败", e);
  } finally {
    loading.value = false;
  }
}

onMounted(fetchData);

// ── 大统计卡片 ────────────────────────────────────────────
const bigStats = computed(() => {
  if (!dashboard.value)
    return [
      { val: "--", label: "累计学习", sub: "" },
      { val: "--", label: "掌握知识点", sub: "" },
      { val: "--", label: "连续打卡", sub: "" },
      { val: "--", label: "今日待复习", sub: "" },
    ];
  const d = dashboard.value;
  const totalMin = (d.study_logs || []).reduce((s, l) => s + l.minutes, 0);
  const totalH = (totalMin / 60).toFixed(1);
  return [
    {
      val: totalH + "h",
      label: "累计学习",
      sub: `共 ${d.study_logs?.length || 0} 天有记录`,
    },
    {
      val: String(d.mastered_nodes ?? "--"),
      label: "掌握知识点",
      sub: `共 ${d.total_nodes ?? "--"} 个节点`,
    },
    {
      val: (d.streak_days ?? "--") + "天",
      label: "连续打卡",
      sub: "保持学习习惯",
    },
    {
      val: String(d.due_today ?? "--"),
      label: "今日待复习",
      sub: "SM-2 到期节点",
    },
  ];
});

// ── 本周学习时长柱状图 ────────────────────────────────────
const weekData = computed(() => {
  const days = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  const today = new Date();
  const todayStr = today.toISOString().slice(0, 10);
  const logsMap = {};
  (dashboard.value?.study_logs || []).forEach((l) => {
    logsMap[l.date] = (logsMap[l.date] || 0) + l.minutes; // 同一天多条记录累加
  });

  const dayOfWeek = today.getDay() === 0 ? 6 : today.getDay() - 1; // 0=周一
  return days.map((label, i) => {
    const d = new Date(today);
    d.setDate(today.getDate() - dayOfWeek + i);
    const dateStr = d.toISOString().slice(0, 10);
    const isToday = dateStr === todayStr;
    const isFuture = dateStr > todayStr; // 字符串比较，避免时区问题
    return {
      day: isToday ? "今天" : label,
      hours: isFuture ? 0 : (logsMap[dateStr] || 0) / 60,
      today: isToday,
    };
  });
});
const maxHours = computed(() =>
  Math.max(...weekData.value.map((d) => d.hours), 0.1),
);

// ── 知识图谱学科概览 ──────────────────────────────────────
const TAG_COLORS = [
  "#6366f1",
  "#10b981",
  "#a855f7",
  "#f59e0b",
  "#3b82f6",
  "#ef4444",
  "#14b8a6",
];

const subjects = computed(() => {
  const nodes = allNodes.value;
  if (!nodes.length) return [];
  const map = {}; // tag -> { total, sumMastery }
  nodes.forEach((n) => {
    const tag = (n.tags && n.tags[0]) || "其他";
    if (!map[tag]) map[tag] = { total: 0, sumMastery: 0 };
    map[tag].total++;
    map[tag].sumMastery += n.mastery_level || 0;
  });
  return Object.entries(map)
    .sort((a, b) => b[1].total - a[1].total)
    .slice(0, 6)
    .map(([name, v], i) => ({
      name,
      nodes: v.total,
      mastery: Math.round((v.sumMastery / v.total) * 100),
      color: TAG_COLORS[i % TAG_COLORS.length],
    }));
});

const graphTotals = computed(() => {
  const nodes = allNodes.value;
  const total = nodes.length;
  const edges = nodes.reduce((s, n) => s + (n.relations?.length || 0), 0);
  const weak = nodes.filter((n) => (n.mastery_level || 0) < 0.4).length;
  return { total, edges, weak };
});

// ── 关于我 ───────────────────────────────────────────────
const aboutFields = [
  {
    key: "background",
    icon: "🎓",
    label: "学习背景",
    hint: "你的教育经历、专业方向等",
    placeholder:
      "例如：计算机科学本科在读，主修算法与数据结构，对机器学习感兴趣…",
    rows: 3,
  },
  {
    key: "goals",
    icon: "🎯",
    label: "学习目标",
    hint: "你希望通过学习达成什么",
    placeholder: "例如：备战秋招，希望掌握系统设计和 LeetCode 中高难度题目…",
    rows: 3,
  },
  {
    key: "style",
    icon: "💡",
    label: "学习偏好",
    hint: "你喜欢什么样的讲解方式",
    placeholder:
      "例如：喜欢先看例子再看理论，不喜欢太多数学推导，希望有代码示例…",
    rows: 3,
  },
  {
    key: "other",
    icon: "📝",
    label: "其他补充",
    hint: "任何你觉得 AI 应该知道的事",
    placeholder:
      "例如：英语不太好，尽量用中文；时间有限，每次学习不超过 30 分钟…",
    rows: 2,
  },
];

const aboutData = ref({
  background: "",
  goals: "",
  style: "",
  other: "",
});

const aboutSaved = ref(false);
const aboutSaving = ref(false);
let aboutSavedTimer = null;

async function saveAbout() {
  aboutSaving.value = true;
  try {
    const res = await fetch("/api/user", {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ about: aboutData.value }),
    });
    userInfo.value = await res.json();
    aboutSaved.value = true;
    clearTimeout(aboutSavedTimer);
    aboutSavedTimer = setTimeout(() => {
      aboutSaved.value = false;
    }, 2000);
  } finally {
    aboutSaving.value = false;
  }
}

// ── 成就（基于真实数据动态计算） ─────────────────────────
const achievements = computed(() => {
  const d = dashboard.value;
  const streak = d?.streak_days || 0;
  const totalNodes = d?.total_nodes || 0;
  const mastered = d?.mastered_nodes || 0;
  const maxDayMin = Math.max(...(d?.study_logs || []).map((l) => l.minutes), 0);

  return [
    {
      id: 1,
      emoji: "🚀",
      name: "起飞",
      desc: "完成第一个学习节点",
      earned: totalNodes >= 1,
      progress: Math.min(100, totalNodes >= 1 ? 100 : 0),
    },
    {
      id: 2,
      emoji: "🔥",
      name: "持之以恒",
      desc: "连续打卡 7 天",
      earned: streak >= 7,
      progress: Math.min(100, Math.round((streak / 7) * 100)),
    },
    {
      id: 3,
      emoji: "⚡",
      name: "学习机器",
      desc: "单日学习超过 4 小时",
      earned: maxDayMin >= 240,
      progress: Math.min(100, Math.round((maxDayMin / 240) * 100)),
    },
    {
      id: 4,
      emoji: "📚",
      name: "博览群书",
      desc: "掌握 10 个知识点",
      earned: mastered >= 10,
      progress: Math.min(100, Math.round((mastered / 10) * 100)),
    },
    {
      id: 5,
      emoji: "🏆",
      name: "知识达人",
      desc: "掌握 50 个知识点",
      earned: mastered >= 50,
      progress: Math.min(100, Math.round((mastered / 50) * 100)),
    },
    {
      id: 6,
      emoji: "💎",
      name: "百日坚持",
      desc: "连续打卡 100 天",
      earned: streak >= 100,
      progress: Math.min(100, Math.round((streak / 100) * 100)),
    },
    {
      id: 7,
      emoji: "🌟",
      name: "知识海洋",
      desc: "掌握 500 个知识点",
      earned: mastered >= 500,
      progress: Math.min(100, Math.round((mastered / 500) * 100)),
    },
    {
      id: 8,
      emoji: "🗺️",
      name: "图谱探索者",
      desc: "创建 20 个知识节点",
      earned: totalNodes >= 20,
      progress: Math.min(100, Math.round((totalNodes / 20) * 100)),
    },
  ];
});
</script>

<style scoped>
.profile-page {
}

/* Hero */
.profile-hero {
  position: relative;
  overflow: hidden;
  background: var(--bg-card);
  border-bottom: 1px solid var(--border);
  padding: 36px 32px 28px;
}
.hero-bg {
  position: absolute;
  inset: 0;
  background:
    radial-gradient(
      ellipse at 20% 50%,
      rgba(99, 102, 241, 0.1) 0%,
      transparent 60%
    ),
    radial-gradient(
      ellipse at 80% 50%,
      rgba(168, 85, 247, 0.08) 0%,
      transparent 60%
    );
  pointer-events: none;
}
.hero-content {
  position: relative;
  display: flex;
  align-items: center;
  gap: 24px;
}
.avatar-wrap {
  position: relative;
  flex-shrink: 0;
}
.avatar-ring {
  position: absolute;
  inset: -4px;
  border-radius: 50%;
  background: var(--gradient-brand);
  opacity: 0.4;
  animation: spin 6s linear infinite;
}
.avatar {
  position: relative;
  box-shadow: 0 0 30px rgba(99, 102, 241, 0.4);
}
.avatar-badge {
  position: absolute;
  bottom: 2px;
  right: 2px;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  background: var(--green);
  border: 2px solid var(--bg-card);
  display: flex;
  align-items: center;
  justify-content: center;
}
.hero-info {
  flex: 1;
}
.hero-name {
  font-size: 24px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
  margin-bottom: 4px;
}

.hero-badges {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* Tabs */
.profile-tabs {
  display: flex;
  gap: 2px;
  padding: 12px 32px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
}
.p-tab {
  padding: 7px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: var(--transition);
}
.p-tab:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}
.p-tab.active {
  color: var(--brand-light);
  background: var(--brand-dim);
}

.tab-content {
  padding: 24px 32px;
}

/* Big stats */
.big-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  overflow: hidden;
  margin-bottom: 20px;
}
.big-stat {
  padding: 22px 20px;
  border-right: 1px solid var(--border);
  text-align: center;
}
.big-stat:last-child {
  border-right: none;
}
.bs-val {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -1px;
  margin-bottom: 4px;
}
.bs-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.bs-sub {
  font-size: 10px;
  color: var(--text-muted);
}

/* Overview grid */
.overview-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  align-items: stretch;
}
.ov-card {
  padding: 20px;
  display: flex;
  flex-direction: column;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  flex-shrink: 0;
}
.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

/* Bar chart */
.bar-chart {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 100px;
}
.bc-bars {
  flex: 1;
  display: flex;
  gap: 8px;
  align-items: flex-end;
}
.bc-bar-group {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex: 1;
  height: 100%;
}
.bc-bar-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  justify-content: flex-end;
  width: 100%;
}
.bc-bar {
  position: relative;
  width: 100%;
  border-radius: 4px 4px 0 0;
  min-height: 4px;
  transition: height 0.6s cubic-bezier(0.4, 0, 0.2, 1);
}
.bc-duration {
  position: absolute;
  top: -16px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 9px;
  color: var(--text-dim);
  white-space: nowrap;
  line-height: 1;
}
.bc-duration-today {
  color: var(--brand-light);
  font-weight: 600;
}
.bc-label {
  flex-shrink: 0;
  margin-top: 6px;
  font-size: 10px;
  color: var(--text-dim);
}
.bc-label.today {
  color: var(--brand-light);
  font-weight: 600;
}

/* Mastery */
.mastery-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mastery-row {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.mr-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}
.mr-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
}
.mr-bar {
  display: flex;
  align-items: center;
  gap: 8px;
}
.mr-val {
  font-size: 11px;
  font-weight: 700;
  width: 30px;
  text-align: right;
}
.mr-nodes {
  font-size: 10px;
  color: var(--text-dim);
  margin-left: auto;
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
.graph-totals {
  display: flex;
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 12px;
  margin-top: 14px;
}
.gt-item {
  flex: 1;
  text-align: center;
}
.gt-val {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.5px;
}
.gt-label {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 2px;
}
.gt-divider {
  width: 1px;
  background: var(--border);
}

/* Achievements */
.achievements-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
}
.ach-card {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
}
.ach-card.locked {
  opacity: 0.45;
  filter: grayscale(0.5);
}
.ach-icon {
  font-size: 28px;
  flex-shrink: 0;
}
.ach-info {
  flex: 1;
}
.ach-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.ach-desc {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}
.ach-progress-wrap {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ach-prog-val {
  font-size: 10px;
  color: var(--text-muted);
  white-space: nowrap;
}

/* Loading */
.loading-row {
  display: flex;
  justify-content: center;
  align-items: center;
  gap: 6px;
  padding: 60px 0;
}
.loading-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--brand);
  animation: bounce 1.2s infinite ease-in-out;
}
.loading-dot:nth-child(2) {
  animation-delay: 0.2s;
}
.loading-dot:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes bounce {
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

/* Empty tip */
.empty-tip {
  font-size: 12px;
  color: var(--text-dim);
  text-align: center;
  padding: 20px 0;
}

/* About Me */
.about-form {
  max-width: 640px;
}
.about-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 24px;
  gap: 16px;
}
.about-header-text {
  flex: 1;
}
.about-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}
.about-desc {
  font-size: 12px;
  color: var(--text-muted);
}
.about-save-btn {
  flex-shrink: 0;
}
.about-fields {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.about-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.about-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.about-label-icon {
  font-size: 15px;
}
.about-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin: 0;
}
.about-textarea {
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 10px 12px;
  font-size: 13px;
  color: var(--text-primary);
  outline: none;
  resize: vertical;
  line-height: 1.6;
  font-family: inherit;
  transition: var(--transition);
}
.about-textarea:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--brand-dim);
}
.about-textarea::placeholder {
  color: var(--text-dim);
}
.about-saved-tip {
  margin-top: 12px;
  font-size: 12px;
  color: var(--green);
  font-weight: 500;
}

/* Hero edit button */
.hero-actions {
  margin-left: auto;
}
.btn-icon-edit {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition);
}
.btn-icon-edit:hover {
  color: var(--brand-light);
  border-color: var(--brand);
  background: var(--brand-dim);
}

/* Modal */
.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
}
.modal-box {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  width: 360px;
  box-shadow: 0 24px 60px rgba(0, 0, 0, 0.4);
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border);
}
.modal-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}
.modal-close {
  background: none;
  border: none;
  color: var(--text-dim);
  font-size: 14px;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
}
.modal-close:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}
.modal-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.edit-avatar-preview {
  display: flex;
  justify-content: center;
  margin-bottom: 4px;
}
.form-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.form-label {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
}
.form-input {
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 8px 12px;
  font-size: 13px;
  color: var(--text-primary);
  outline: none;
  transition: var(--transition);
}
.form-input:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px var(--brand-dim);
}
.form-input::placeholder {
  color: var(--text-dim);
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px 18px;
  border-top: 1px solid var(--border);
}
.btn-ghost {
  padding: 7px 16px;
  border-radius: var(--radius-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid var(--border);
  cursor: pointer;
  transition: var(--transition);
}
.btn-ghost:hover {
  color: var(--text-primary);
  background: var(--bg-hover);
}
</style>
