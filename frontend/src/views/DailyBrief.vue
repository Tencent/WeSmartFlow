<template>
  <div class="brief-page">
    <!-- ══ Page Header ══════════════════════════════════════════ -->
    <div class="page-header">
      <div>
        <h1 class="page-title">每日学习简报</h1>
        <p class="page-subtitle">
          {{ todayLabel }} · Agent 智能推送今日最值得关注的知识动态
        </p>
      </div>
    </div>

    <!-- ══ Main layout ══════════════════════════════════════════ -->
    <div class="main-layout">
      <!-- Left: Calendar panel -->
      <div class="calendar-panel card">
        <div class="cal-title">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <rect x="3" y="4" width="18" height="18" rx="2" />
            <line x1="16" y1="2" x2="16" y2="6" />
            <line x1="8" y1="2" x2="8" y2="6" />
            <line x1="3" y1="10" x2="21" y2="10" />
          </svg>
          历史简报
        </div>

        <div class="month-nav">
          <button class="month-btn" @click="prevMonth">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <polyline points="15 18 9 12 15 6" />
            </svg>
          </button>
          <span class="month-label">{{ currentMonthLabel }}</span>
          <button class="month-btn" :disabled="!canGoNext" @click="nextMonth">
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <polyline points="9 18 15 12 9 6" />
            </svg>
          </button>
        </div>

        <div class="cal-grid">
          <div v-for="d in weekDays" :key="d" class="cal-week-header">
            {{ d }}
          </div>
          <div
            v-for="cell in calendarCells"
            :key="cell.key"
            class="cal-cell"
            :class="{
              'other-month': !cell.inMonth,
              'has-data': cell.inMonth && hasData(cell.dateStr),
              'is-today': cell.dateStr === todayStr,
              'is-selected': cell.dateStr === selectedDate,
              'is-future': cell.dateStr > todayStr,
            }"
            @click="
              cell.inMonth &&
              cell.dateStr <= todayStr &&
              selectDate(cell.dateStr)
            "
          >
            <span class="cal-day-num">{{ cell.day }}</span>
            <span
              v-if="cell.inMonth && hasData(cell.dateStr)"
              class="cal-dot"
            />
          </div>
        </div>

        <div class="cal-legend">
          <div class="leg-item"><span class="leg-dot has" /> 有简报</div>
          <div class="leg-item"><span class="leg-dot today" /> 今天</div>
        </div>

        <!-- 本月统计 -->
        <div class="cal-stats">
          <div class="cs-item">
            <div class="cs-val">
              {{ monthCount }}
            </div>
            <div class="cs-label">本月简报</div>
          </div>
          <div class="cs-divider" />
          <div class="cs-item">
            <div class="cs-val">
              {{ streakDays }}
            </div>
            <div class="cs-label">连续天数</div>
          </div>
        </div>
      </div>

      <!-- Right: Content panel -->
      <div class="content-panel">
        <!-- Keywords bar -->
        <div class="keywords-bar">
          <span class="kb-label">关键词</span>
          <span v-for="tag in interests" :key="tag" class="kw-tag">{{
            tag
          }}</span>
          <span v-if="!interests.length" class="kw-empty">暂无关键词</span>
          <button
            class="kw-edit-btn"
            title="编辑关键词"
            @click="openInterestEditor"
          >
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
            </svg>
          </button>
        </div>

        <!-- Content header -->
        <div class="content-header">
          <div class="content-date-title">
            <span class="cdt-emoji">{{
              selectedDate === todayStr ? "📬" : "📁"
            }}</span>
            {{
              selectedDate === todayStr ? "今日简报" : `${selectedDate} 简报`
            }}
          </div>
          <div class="content-actions">
            <button
              class="act-btn"
              :class="{ loading: isLoading }"
              @click="refreshData"
            >
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                :class="{ spinning: isLoading }"
              >
                <path d="M23 4v6h-6" />
                <path d="M1 20v-6h6" />
                <path
                  d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"
                />
              </svg>
              刷新
            </button>
            <button
              v-if="selectedDate === todayStr"
              class="act-btn act-btn-danger"
              @click="regenerate"
            >
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
              重新生成
            </button>
          </div>
        </div>

        <!-- Loading skeleton -->
        <div v-if="isLoading" class="loading-area">
          <div v-for="i in 3" :key="i" class="skeleton-group card">
            <!-- 分组 header 骨架 -->
            <div class="sg-header">
              <div class="sk-icon" />
              <div class="sg-info">
                <div class="sk-line w40" />
                <div class="sk-line w20" style="margin-top: 6px" />
              </div>
              <div class="sg-right">
                <div class="sk-bar" />
                <div class="sk-line w30" />
              </div>
            </div>
            <!-- 新闻卡片骨架 -->
            <div class="sg-items">
              <div v-for="j in 2" :key="j" class="sk-news-card">
                <div class="sk-rank" />
                <div class="sk-news-body">
                  <div class="sk-line w70" />
                  <div class="sk-line w90" style="margin-top: 8px" />
                  <div class="sk-line w55" style="margin-top: 6px" />
                  <div class="sk-tags" style="margin-top: 10px">
                    <div class="sk-tag" />
                    <div class="sk-tag" />
                    <div class="sk-tag" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Generating state -->
        <div v-else-if="isGenerating" class="generating-card card">
          <div class="gen-spinner">
            <div class="agent-avatar" style="width: 52px; height: 52px">
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="white"
                stroke-width="1.8"
              >
                <path d="M12 2a10 10 0 100 20A10 10 0 0012 2z" />
                <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
                <line x1="12" y1="17" x2="12.01" y2="17" />
              </svg>
            </div>
            <div class="gen-ring" />
          </div>
          <div class="gen-title">Agent 正在搜集今日学习动态...</div>
          <div class="gen-sub">
            正在抓取最新资讯、整理知识要点，通常需要 30 秒
          </div>
          <div class="gen-tags">
            <span v-for="t in interests" :key="t" class="badge badge-brand">{{
              t
            }}</span>
          </div>
          <button class="act-btn" style="margin-top: 8px" @click="refreshData">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M23 4v6h-6" />
              <path d="M1 20v-6h6" />
              <path
                d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"
              />
            </svg>
            手动刷新
          </button>
        </div>

        <!-- Empty state -->
        <div v-else-if="!currentData" class="empty-card card">
          <div class="empty-emoji">📭</div>
          <div class="empty-title">该日期暂无简报</div>
          <div class="empty-sub">
            {{
              selectedDate === todayStr
                ? "Agent 将在你开始学习后自动生成"
                : "仅在登录当天自动生成简报"
            }}
          </div>
        </div>

        <!-- Content -->
        <template v-else>
          <!-- Groups -->
          <div class="news-groups">
            <div
              v-for="group in currentData.groups"
              :key="group.topic"
              class="news-group"
            >
              <div class="group-header" @click="toggleGroup(group.topic)">
                <div class="group-left">
                  <div
                    class="group-icon"
                    :style="{
                      background: group.color + '22',
                      color: group.color,
                    }"
                  >
                    {{ group.icon }}
                  </div>
                  <div class="group-info">
                    <div class="group-name">
                      {{ group.topic }}
                    </div>
                    <div class="group-count">
                      {{ group.items.length }} 条资讯
                    </div>
                  </div>
                </div>
                <div class="group-right">
                  <div class="group-bar">
                    <div
                      class="gb-fill"
                      :style="{
                        width: group.relevance + '%',
                        background: group.color,
                      }"
                    />
                  </div>
                  <span class="group-rel" :style="{ color: group.color }"
                    >{{ group.relevance }}% 相关</span
                  >
                  <svg
                    class="group-chevron"
                    :class="{ open: !collapsedGroups.has(group.topic) }"
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

              <transition name="group-collapse">
                <div v-if="!collapsedGroups.has(group.topic)" class="news-list">
                  <div
                    v-for="(item, idx) in group.items"
                    :key="idx"
                    class="news-card"
                    :style="{ '--gc': group.color }"
                    @click="openDetail(item, group)"
                  >
                    <div class="nc-accent" />
                    <div class="nc-rank">
                      {{ rankIcon(idx) }}
                    </div>
                    <div class="nc-body">
                      <div class="nc-title">
                        {{ item.title }}
                      </div>
                      <div class="nc-summary">
                        {{ item.summary }}
                      </div>
                      <div class="nc-footer">
                        <div class="nc-tags">
                          <span
                            v-for="tag in item.tags.slice(0, 3)"
                            :key="tag"
                            class="ntag"
                            >{{ tag }}</span
                          >
                        </div>
                        <div class="nc-meta">
                          <span v-if="item.source" class="meta-source">
                            <svg
                              width="10"
                              height="10"
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
                            {{ item.source }}
                          </span>
                          <span v-if="item.relevance" class="meta-relevance">
                            <svg
                              width="10"
                              height="10"
                              viewBox="0 0 24 24"
                              fill="none"
                              stroke="currentColor"
                              stroke-width="2"
                            >
                              <path
                                d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"
                              />
                            </svg>
                            与你相关
                          </span>
                          <span class="meta-read">查看详情 →</span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </transition>
            </div>
          </div>
        </template>
      </div>
    </div>

    <!-- ══ Detail modal ══════════════════════════════════════════ -->
    <transition name="modal">
      <div
        v-if="detailItem"
        class="modal-overlay"
        @click.self="detailItem = null"
      >
        <div class="modal-card card">
          <div
            class="modal-accent"
            :style="{ background: detailGroup?.color }"
          />
          <div class="modal-header">
            <div class="modal-tags">
              <span class="badge badge-brand">{{ detailGroup?.topic }}</span>
              <span v-if="detailItem.source" class="badge badge-yellow">{{
                detailItem.source
              }}</span>
              <span v-for="t in detailItem.tags" :key="t" class="ntag">{{
                t
              }}</span>
            </div>
            <button class="modal-close" @click="detailItem = null">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          <h2 class="modal-title">
            {{ detailItem.title }}
          </h2>

          <div class="modal-section">
            <div class="ms-label">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path
                  d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"
                />
                <polyline points="14 2 14 8 20 8" />
              </svg>
              摘要
            </div>
            <p class="ms-text">
              {{ detailItem.summary }}
            </p>
          </div>

          <div v-if="detailItem.content" class="modal-section">
            <div class="ms-label">
              <svg
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
              详细内容
            </div>
            <p class="ms-text">
              {{ detailItem.content }}
            </p>
          </div>

          <div
            v-if="detailItem.relevance"
            class="modal-section relevance-section"
          >
            <div class="ms-label" style="color: var(--brand-light)">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path
                  d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"
                />
              </svg>
              与你的关联
            </div>
            <p class="ms-text">
              {{ detailItem.relevance }}
            </p>
          </div>

          <div class="modal-footer">
            <button class="btn btn-ghost" @click="detailItem = null">
              关闭
            </button>
            <button
              v-if="detailItem.url"
              class="btn btn-primary"
              @click="openUrl(detailItem.url)"
            >
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path
                  d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"
                />
                <polyline points="15 3 21 3 21 9" />
                <line x1="10" y1="14" x2="21" y2="3" />
              </svg>
              查看原文
            </button>
            <button
              v-else
              class="btn btn-primary"
              @click="$router.push('/chat')"
            >
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
              问 Agent
            </button>
          </div>
        </div>
      </div>
    </transition>

    <!-- ══ Interest Editor Modal ════════════════════════════════ -->
    <transition name="modal">
      <div
        v-if="showInterestEditor"
        class="modal-overlay"
        @click.self="showInterestEditor = false"
      >
        <div class="ie-modal card">
          <!-- Header -->
          <div class="ie-header">
            <div class="ie-header-left">
              <div class="ie-icon">🏷️</div>
              <div>
                <div class="ie-title">我的关键词</div>
                <div class="ie-subtitle">简报将围绕这些方向为你推送内容</div>
              </div>
            </div>
            <button class="modal-close" @click="showInterestEditor = false">
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>

          <!-- 输入区 -->
          <div class="ie-input-wrap">
            <svg
              class="ie-input-icon"
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="11" cy="11" r="8" />
              <line x1="21" y1="21" x2="16.65" y2="16.65" />
            </svg>
            <input
              v-model="newTagInput"
              class="ie-input"
              placeholder="输入关键词，按回车添加…"
              maxlength="20"
              autofocus
              @keydown.enter.prevent="addTag"
            />
            <button
              class="ie-add-btn"
              :disabled="!newTagInput.trim()"
              @click="addTag"
            >
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
              >
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              添加
            </button>
          </div>

          <!-- 已有标签 -->
          <div class="ie-body">
            <div v-if="editingInterests.length" class="ie-section-label">
              已添加 {{ editingInterests.length }} 个关键词
            </div>
            <div v-if="editingInterests.length" class="ie-tags">
              <span v-for="tag in editingInterests" :key="tag" class="ie-tag">
                {{ tag }}
                <button class="ie-tag-del" @click="removeTag(tag)">
                  <svg
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                  >
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                </button>
              </span>
            </div>
            <div v-else class="ie-empty">
              <div class="ie-empty-icon">✨</div>
              <div>还没有关键词，在上方输入你感兴趣的方向</div>
            </div>
          </div>

          <!-- Footer -->
          <div class="ie-footer">
            <button class="btn btn-ghost" @click="showInterestEditor = false">
              取消
            </button>
            <button class="btn btn-primary" @click="saveInterests">
              <svg
                width="13"
                height="13"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="20 6 9 17 4 12" />
              </svg>
              保存
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from "vue";
import { userApi, briefApi } from "@/api";

// ── 日期工具 ────────────────────────────────────────────────────
function getTodayStr() {
  const now = new Date();
  return now.toISOString().slice(0, 10);
}

const todayStr = getTodayStr();
const todayLabel = computed(() => {
  const [y, m, d] = todayStr.split("-");
  return `${y}年${parseInt(m)}月${parseInt(d)}日 · 星期${"日一二三四五六"[new Date().getDay()]}`;
});

// ── 日历状态 ────────────────────────────────────────────────────
const viewYear = ref(new Date().getFullYear());
const viewMonth = ref(new Date().getMonth());
const selectedDate = ref(todayStr);
const weekDays = ["日", "一", "二", "三", "四", "五", "六"];

const currentMonthLabel = computed(
  () => `${viewYear.value}年 ${viewMonth.value + 1}月`,
);

const canGoNext = computed(() => {
  const now = new Date();
  return (
    viewYear.value < now.getFullYear() ||
    (viewYear.value === now.getFullYear() && viewMonth.value < now.getMonth())
  );
});

function prevMonth() {
  if (viewMonth.value === 0) {
    viewMonth.value = 11;
    viewYear.value--;
  } else viewMonth.value--;
}
function nextMonth() {
  if (!canGoNext.value) return;
  if (viewMonth.value === 11) {
    viewMonth.value = 0;
    viewYear.value++;
  } else viewMonth.value++;
}

const calendarCells = computed(() => {
  const firstDay = new Date(viewYear.value, viewMonth.value, 1).getDay();
  const daysInMonth = new Date(
    viewYear.value,
    viewMonth.value + 1,
    0,
  ).getDate();
  const daysInPrev = new Date(viewYear.value, viewMonth.value, 0).getDate();
  const cells = [];
  for (let i = firstDay - 1; i >= 0; i--) {
    const d = daysInPrev - i;
    const m = viewMonth.value === 0 ? 12 : viewMonth.value;
    const y = viewMonth.value === 0 ? viewYear.value - 1 : viewYear.value;
    cells.push({
      day: d,
      inMonth: false,
      dateStr: `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`,
      key: `prev-${d}`,
    });
  }
  for (let d = 1; d <= daysInMonth; d++) {
    const ds = `${viewYear.value}-${String(viewMonth.value + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
    cells.push({ day: d, inMonth: true, dateStr: ds, key: ds });
  }
  const remaining = 42 - cells.length;
  for (let d = 1; d <= remaining; d++) {
    const m = viewMonth.value === 11 ? 1 : viewMonth.value + 2;
    const y = viewMonth.value === 11 ? viewYear.value + 1 : viewYear.value;
    cells.push({
      day: d,
      inMonth: false,
      dateStr: `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`,
      key: `next-${d}`,
    });
  }
  return cells;
});

// 有简报数据的日期集合（从后端加载）
const dateDots = ref(new Set([todayStr]));

function hasData(ds) {
  return dateDots.value.has(ds);
}
function selectDate(ds) {
  selectedDate.value = ds;
  loadBriefForDate(ds);
}

const monthCount = computed(() => {
  return [...dateDots.value].filter((d) =>
    d.startsWith(
      `${viewYear.value}-${String(viewMonth.value + 1).padStart(2, "0")}`,
    ),
  ).length;
});

// 从今天往前数连续有简报的天数
const streakDays = computed(() => {
  let count = 0;
  const d = new Date(todayStr);
  while (true) {
    const ds = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    if (!dateDots.value.has(ds)) break;
    count++;
    d.setDate(d.getDate() - 1);
  }
  return count;
});

async function loadBriefDates() {
  try {
    const data = await briefApi.getDates();
    dateDots.value = new Set([todayStr, ...(data.dates || [])]);
  } catch (e) {
    console.error("加载简报日期失败", e);
  }
}

// ── 用户兴趣方向 ────────────────────────────────────────────────
const interests = ref([]);

// 编辑弹窗
const showInterestEditor = ref(false);
const editingInterests = ref([]);
const newTagInput = ref("");

async function loadInterests() {
  try {
    const user = await userApi.getMe();
    interests.value = user.preferences?.interests || [];
  } catch (e) {
    console.error("加载兴趣失败", e);
  }
}

function openInterestEditor() {
  editingInterests.value = [...interests.value];
  newTagInput.value = "";
  showInterestEditor.value = true;
}

function addTag() {
  const tag = newTagInput.value.trim();
  if (tag && !editingInterests.value.includes(tag)) {
    editingInterests.value.push(tag);
  }
  newTagInput.value = "";
}

function removeTag(tag) {
  editingInterests.value = editingInterests.value.filter((t) => t !== tag);
}

async function saveInterests() {
  try {
    await userApi.updateMe({
      preferences: { interests: editingInterests.value },
    });
    interests.value = [...editingInterests.value];
    showInterestEditor.value = false;
  } catch (e) {
    console.error("保存兴趣失败", e);
  }
}

onMounted(() => {
  loadInterests();
  loadBriefDates();
  loadBriefForDate(todayStr);
});

// ── 分组折叠 ────────────────────────────────────────────────────
const collapsedGroups = ref(new Set());
function toggleGroup(topic) {
  const s = new Set(collapsedGroups.value);
  if (s.has(topic)) s.delete(topic);
  else s.add(topic);
  collapsedGroups.value = s;
}

// ── 内容状态 ────────────────────────────────────────────────
const isLoading = ref(false);
const isGenerating = ref(false);
const briefCache = ref({}); // { [date]: { groups, has_data } }

const currentData = computed(() => {
  if (isLoading.value || isGenerating.value) return null;
  return briefCache.value[selectedDate.value] || null;
});

async function loadBriefForDate(date) {
  // 已有缓存不重复请求
  if (briefCache.value[date] !== undefined) return;

  isLoading.value = true;
  try {
    let data;
    if (date === todayStr) {
      // 今天：有缓存直接返回，否则生成
      data = await briefApi.getToday();
    } else {
      // 历史日期：仅读缓存
      data = await briefApi.getByDate(date);
    }
    briefCache.value = {
      ...briefCache.value,
      [date]: data.has_data ? data : null,
    };
    // 如果返回了数据，更新日期点
    if (data.has_data) {
      dateDots.value = new Set([...dateDots.value, date]);
    }
  } catch (e) {
    console.error("加载简报失败", e);
    briefCache.value = { ...briefCache.value, [date]: null };
  } finally {
    isLoading.value = false;
  }
}

async function refreshData() {
  // 删除当前日期缓存，重新加载
  const cache = { ...briefCache.value };
  delete cache[selectedDate.value];
  briefCache.value = cache;
  await loadBriefForDate(selectedDate.value);
}

async function regenerate() {
  isGenerating.value = true;
  try {
    const data = await briefApi.regenerate();
    briefCache.value = {
      ...briefCache.value,
      [todayStr]: data.has_data ? data : null,
    };
    if (data.has_data) {
      dateDots.value = new Set([...dateDots.value, todayStr]);
    }
  } catch (e) {
    console.error("重新生成失败", e);
  } finally {
    isGenerating.value = false;
  }
}
// ── 详情弹窗 ────────────────────────────────────────────────────
const detailItem = ref(null);
const detailGroup = ref(null);

function openDetail(item, group) {
  detailItem.value = item;
  detailGroup.value = group;
}
function openUrl(url) {
  window.open(url, "_blank", "noopener");
}
function rankIcon(idx) {
  return ["🥇", "🥈", "🥉"][idx] || "📌";
}
</script>

<style scoped>
.brief-page {
  padding: 28px 32px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-height: 100vh;
  box-sizing: border-box;
}

/* ══ Page Header ══════════════════════════════════════════════ */
.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
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

/* ══ Main layout ══════════════════════════════════════════════ */
.main-layout {
  display: grid;
  grid-template-columns: 256px 1fr;
  gap: 16px;
  align-items: start;
  flex: 1;
}

/* ══ Calendar Panel ═══════════════════════════════════════════ */
.calendar-panel {
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  position: sticky;
  top: 28px;
}

.cal-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}

.month-nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.month-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.month-btn {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
}
.month-btn:hover:not(:disabled) {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}
.month-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.cal-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 2px;
}
.cal-week-header {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  text-align: center;
  padding: 4px 0;
}
.cal-cell {
  aspect-ratio: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  cursor: pointer;
  transition: var(--transition);
  position: relative;
  gap: 2px;
}
.cal-cell:hover:not(.other-month):not(.is-future) {
  background: var(--bg-hover);
}
.cal-cell.other-month {
  opacity: 0.2;
  cursor: default;
}
.cal-cell.is-future {
  opacity: 0.3;
  cursor: not-allowed;
}
.cal-cell.has-data {
  background: var(--brand-dim);
}
.cal-cell.has-data:hover {
  background: rgba(99, 102, 241, 0.2);
}
.cal-cell.is-today .cal-day-num {
  background: var(--gradient-brand);
  color: white;
  border-radius: 50%;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: 11px;
}
.cal-cell.is-selected {
  background: var(--brand-dim);
  outline: 2px solid var(--brand);
  outline-offset: -1px;
}
.cal-day-num {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1;
}
.cal-dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--brand-light);
}

.cal-legend {
  display: flex;
  gap: 14px;
}
.leg-item {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  color: var(--text-muted);
}
.leg-dot {
  width: 8px;
  height: 8px;
  border-radius: 2px;
}
.leg-dot.has {
  background: var(--brand-dim);
  border: 1px solid var(--brand-light);
}
.leg-dot.today {
  background: var(--gradient-brand);
}

.cal-stats {
  display: flex;
  align-items: center;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
  padding: 10px 14px;
  gap: 0;
}
.cs-item {
  flex: 1;
  text-align: center;
}
.cs-val {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}
.cs-label {
  font-size: 10px;
  color: var(--text-muted);
  margin-top: 1px;
}
.cs-divider {
  width: 1px;
  height: 28px;
  background: var(--border);
}

/* ══ Content Panel ════════════════════════════════════════════ */
.content-panel {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.content-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 2px;
}
.content-date-title {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
}
.cdt-emoji {
  font-size: 18px;
}
.content-actions {
  display: flex;
  gap: 6px;
}

.act-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition);
}
.act-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border-hover);
}
.act-btn svg.spinning {
  animation: spin 1s linear infinite;
}
.act-btn-danger {
  color: var(--red);
}
.act-btn-danger:hover {
  background: var(--red-dim);
  border-color: var(--red);
}

/* ══ Loading ══════════════════════════════════════════════════ */
.loading-area {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 分组骨架 */
.skeleton-group {
  padding: 0;
  overflow: hidden;
}
.sg-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
}
/* 通用 shimmer 骨架背景（供各骨架元素复用） */
.sk-icon,
.sk-bar,
.sk-rank,
.sk-line,
.sk-tag {
  background: linear-gradient(
    90deg,
    var(--bg-hover) 25%,
    var(--bg-active) 50%,
    var(--bg-hover) 75%
  );
  background-size: 200% 100%;
  animation: shimmer 1.5s infinite;
}

.sk-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}
.sg-info {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0;
}
.sg-right {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: auto;
}
.sk-bar {
  width: 60px;
  height: 4px;
  border-radius: 2px;
}
.sg-items {
  display: flex;
  flex-direction: column;
}
.sk-news-card {
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding: 16px 18px 16px 14px;
  border-bottom: 1px solid var(--border);
}
.sk-news-card:last-child {
  border-bottom: none;
}
.sk-rank {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  flex-shrink: 0;
  margin-right: 12px;
  margin-top: 2px;
}
.sk-news-body {
  flex: 1;
  display: flex;
  flex-direction: column;
}

.sk-line {
  height: 12px;
  border-radius: 6px;
}
.w20 {
  width: 20%;
}
.w30 {
  width: 30%;
}
.w40 {
  width: 40%;
}
.w55 {
  width: 55%;
}
.w60 {
  width: 60%;
}
.w70 {
  width: 70%;
}
.w90 {
  width: 90%;
}
.sk-tags {
  display: flex;
  gap: 6px;
}
.sk-tag {
  height: 18px;
  width: 52px;
  border-radius: 9px;
}

/* ══ Generating ═══════════════════════════════════════════════ */
.generating-card {
  padding: 56px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
  text-align: center;
}
.gen-spinner {
  position: relative;
  width: 60px;
  height: 60px;
}
.gen-ring {
  position: absolute;
  inset: -8px;
  border-radius: 50%;
  border: 2px solid transparent;
  border-top-color: var(--brand);
  border-right-color: var(--brand-light);
  animation: spin 1.5s linear infinite;
}
.gen-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.gen-sub {
  font-size: 12px;
  color: var(--text-muted);
  max-width: 320px;
  line-height: 1.7;
}
.gen-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: center;
}

/* ══ Empty ════════════════════════════════════════════════════ */
.empty-card {
  padding: 72px 24px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  text-align: center;
}
.empty-emoji {
  font-size: 52px;
}
.empty-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.empty-sub {
  font-size: 12px;
  color: var(--text-muted);
}

/* ══ Keywords Bar ═════════════════════════════════════════════ */
.keywords-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.kb-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  flex-shrink: 0;
}
.kw-tag {
  padding: 4px 12px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
  background: var(--brand-dim);
  border: 1px solid rgba(99, 102, 241, 0.2);
  color: var(--brand-light);
}
.kw-empty {
  font-size: 12px;
  color: var(--text-muted);
}
.kw-edit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-muted);
  cursor: pointer;
  transition: var(--transition);
  flex-shrink: 0;
}
.kw-edit-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
  border-color: var(--border-hover);
}

/* ══ Interest Editor Modal ════════════════════════════════════ */
.ie-modal {
  width: 100%;
  max-width: 460px;
  padding: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
.ie-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 20px 20px 16px;
  border-bottom: 1px solid var(--border);
}
.ie-header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.ie-icon {
  font-size: 22px;
  line-height: 1;
}
.ie-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.ie-subtitle {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}

.ie-input-wrap {
  display: flex;
  align-items: center;
  gap: 0;
  margin: 16px 20px 0;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  transition: var(--transition);
}
.ie-input-wrap:focus-within {
  border-color: var(--brand);
  background: var(--bg-card);
}
.ie-input-icon {
  flex-shrink: 0;
  margin-left: 12px;
  color: var(--text-dim);
}
.ie-input {
  flex: 1;
  padding: 10px 10px;
  background: transparent;
  border: none;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
}
.ie-input::placeholder {
  color: var(--text-dim);
}
.ie-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 0 14px;
  height: 38px;
  flex-shrink: 0;
  background: var(--brand-dim);
  border: none;
  border-left: 1px solid var(--border);
  color: var(--brand-light);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition);
}
.ie-add-btn:hover:not(:disabled) {
  background: var(--brand);
  color: white;
}
.ie-add-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.ie-body {
  padding: 14px 20px 16px;
  min-height: 100px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.ie-section-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
}
.ie-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.ie-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: var(--radius-full);
  font-size: 12px;
  font-weight: 500;
  background: var(--brand-dim);
  border: 1px solid rgba(99, 102, 241, 0.25);
  color: var(--brand-light);
  transition: var(--transition);
}
.ie-tag:hover {
  background: rgba(99, 102, 241, 0.2);
}
.ie-tag-del {
  display: flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  cursor: pointer;
  color: var(--brand-light);
  opacity: 0.5;
  padding: 0;
  transition: var(--transition);
}
.ie-tag-del:hover {
  opacity: 1;
  color: var(--red);
}
.ie-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 20px 0;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}
.ie-empty-icon {
  font-size: 28px;
}

.ie-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
}

/* ══ News Groups ══════════════════════════════════════════════ */
.news-groups {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.news-group {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  overflow: hidden;
  transition: var(--transition);
}
.news-group:hover {
  border-color: var(--border-hover);
}

.group-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  cursor: pointer;
  transition: var(--transition);
  user-select: none;
}
.group-header:hover {
  background: var(--bg-hover);
}

.group-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.group-icon {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}
.group-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.group-name {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
}
.group-count {
  font-size: 11px;
  color: var(--text-dim);
}

.group-right {
  display: flex;
  align-items: center;
  gap: 10px;
}
.group-bar {
  width: 60px;
  height: 4px;
  border-radius: 2px;
  background: var(--bg-active);
  overflow: hidden;
}
.gb-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.6s ease;
}
.group-rel {
  font-size: 11px;
  font-weight: 600;
  min-width: 60px;
  text-align: right;
}
.group-chevron {
  color: var(--text-dim);
  transition: transform 0.25s ease;
  flex-shrink: 0;
}
.group-chevron.open {
  transform: rotate(180deg);
}

.news-list {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--border);
}

.news-card {
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding: 0;
  cursor: pointer;
  transition: var(--transition);
  border-bottom: 1px solid var(--border);
  position: relative;
}
.news-card:last-child {
  border-bottom: none;
}
.news-card:hover {
  background: var(--bg-hover);
}
.news-card:hover .nc-accent {
  opacity: 1;
}

.nc-accent {
  width: 3px;
  flex-shrink: 0;
  align-self: stretch;
  background: var(--gc);
  opacity: 0.3;
  transition: opacity 0.2s;
}
.nc-rank {
  font-size: 18px;
  flex-shrink: 0;
  padding: 16px 12px 16px 14px;
}
.nc-body {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
  padding: 16px 18px 16px 0;
}
.nc-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.5;
}
.nc-summary {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.75;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.nc-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 2px;
}
.nc-tags {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.ntag {
  padding: 2px 8px;
  border-radius: var(--radius-full);
  background: var(--bg-active);
  color: var(--text-secondary);
  font-size: 10px;
  border: 1px solid var(--border);
}
.nc-meta {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-shrink: 0;
}
.meta-source {
  font-size: 11px;
  color: var(--text-dim);
  display: flex;
  align-items: center;
  gap: 3px;
}
.meta-relevance {
  font-size: 11px;
  color: #f59e0b;
  display: flex;
  align-items: center;
  gap: 3px;
}
.meta-read {
  font-size: 11px;
  color: var(--brand-light);
  font-weight: 600;
}

/* ══ Group collapse transition ════════════════════════════════ */
.group-collapse-enter-active,
.group-collapse-leave-active {
  transition: all 0.28s ease;
  overflow: hidden;
}
.group-collapse-enter-from,
.group-collapse-leave-to {
  opacity: 0;
  max-height: 0;
}
.group-collapse-enter-to,
.group-collapse-leave-from {
  opacity: 1;
  max-height: 1000px;
}

/* ══ Detail Modal ═════════════════════════════════════════════ */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.modal-card {
  width: 100%;
  max-width: 640px;
  max-height: 80vh;
  overflow-y: auto;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
  overflow: hidden;
}
.modal-accent {
  height: 4px;
  flex-shrink: 0;
  opacity: 0.9;
}
.modal-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 20px 24px 0;
}
.modal-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  flex: 1;
}
.modal-close {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  flex-shrink: 0;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
}
.modal-close:hover {
  background: var(--red-dim);
  color: var(--red);
  border-color: var(--red);
}

.modal-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.5;
  letter-spacing: -0.3px;
  padding: 14px 24px 0;
}

.modal-section {
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  margin: 0 24px;
}
.modal-section + .modal-section {
  margin-top: 10px;
}
.modal-section:first-of-type {
  margin-top: 16px;
}
.relevance-section {
  background: var(--brand-dim);
  border: 1px solid rgba(99, 102, 241, 0.2);
}
.ms-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 8px;
}
.ms-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.75;
  margin: 0;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 16px 24px 20px;
  margin-top: 6px;
}

/* ══ Transitions ══════════════════════════════════════════════ */
.modal-enter-active,
.modal-leave-active {
  transition: all 0.25s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from .modal-card {
  transform: scale(0.96) translateY(8px);
}
.modal-leave-to .modal-card {
  transform: scale(0.96);
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
