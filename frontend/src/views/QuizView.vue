<template>
  <div class="quiz-page">
    <!-- ══ 顶部 Header ══ -->
    <div class="page-header">
      <div>
        <h1 class="page-title">智能出题</h1>
        <p class="page-subtitle">
          Agent 根据知识节点动态生成练习题，帮你巩固薄弱点
        </p>
      </div>
      <div v-if="totalCount > 0" class="session-stats">
        <div class="ss-item">
          <span class="ss-val text-gradient">{{ correctCount }}</span>
          <span class="ss-label">答对</span>
        </div>
        <div class="ss-divider" />
        <div class="ss-item">
          <span class="ss-val" style="color: var(--red)">{{ wrongCount }}</span>
          <span class="ss-label">答错</span>
        </div>
        <div class="ss-divider" />
        <div class="ss-item">
          <span class="ss-val" style="color: var(--text-secondary)">{{
            totalCount
          }}</span>
          <span class="ss-label">总计</span>
        </div>
        <div class="ss-divider" />
        <div class="ss-item">
          <span class="ss-val" style="color: var(--brand-light)"
            >{{ Math.round((correctCount / totalCount) * 100) }}%</span
          >
          <span class="ss-label">正确率</span>
        </div>
      </div>
    </div>

    <!-- ══ 配置栏 ══ -->
    <div class="config-bar card">
      <!-- 节点选择 -->
      <div class="config-section">
        <div class="config-label">知识节点</div>
        <!-- 加载中 -->
        <div v-if="loadingNodes" class="loading-nodes">
          <div class="skeleton-chip" style="width: 200px" />
        </div>
        <!-- 无节点 -->
        <div v-else-if="nodes.length === 0" class="no-nodes">
          暂无知识节点，请先在对话中学习一些内容
        </div>
        <!-- 下拉选择器 -->
        <div v-else ref="dropdownRef" class="node-dropdown">
          <!-- 触发按钮 -->
          <button
            class="nd-trigger"
            :class="{ open: dropdownOpen }"
            @click="toggleDropdown"
          >
            <template v-if="selectedNode">
              <span
                class="chip-dot"
                :style="{
                  background: masteryColor(selectedNode.mastery_level),
                }"
              />
              <span class="nd-title">{{ selectedNode.title }}</span>
              <span class="nd-mastery"
                >{{
                  Math.round((selectedNode.mastery_level || 0) * 100)
                }}%</span
              >
            </template>
            <template v-else>
              <span class="nd-placeholder">选择知识节点...</span>
            </template>
            <svg
              class="nd-arrow"
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <polyline points="6 9 12 15 18 9" />
            </svg>
          </button>
          <!-- 下拉面板 -->
          <transition name="dropdown">
            <div v-if="dropdownOpen" class="nd-panel">
              <!-- 搜索框 -->
              <div class="nd-search">
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <circle cx="11" cy="11" r="8" />
                  <line x1="21" y1="21" x2="16.65" y2="16.65" />
                </svg>
                <input
                  ref="searchInputRef"
                  v-model="nodeSearch"
                  placeholder="搜索节点..."
                  class="nd-search-input"
                  @keydown.escape="dropdownOpen = false"
                />
                <button
                  v-if="nodeSearch"
                  class="nd-clear"
                  @click="nodeSearch = ''"
                >
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
              </div>
              <!-- 排序标签 -->
              <div class="nd-sort-tabs">
                <button
                  v-for="s in sortOptions"
                  :key="s.val"
                  class="nd-sort-tab"
                  :class="{ active: nodeSort === s.val }"
                  @click="nodeSort = s.val"
                >
                  {{ s.label }}
                </button>
              </div>
              <!-- 节点列表 -->
              <div class="nd-list">
                <div v-if="filteredNodes.length === 0" class="nd-empty">
                  没有匹配的节点
                </div>
                <button
                  v-for="n in filteredNodes"
                  :key="n.id"
                  class="nd-item"
                  :class="{ active: selectedNodeId === n.id }"
                  @click="selectNode(n)"
                >
                  <span
                    class="chip-dot"
                    :style="{ background: masteryColor(n.mastery_level) }"
                  />
                  <span class="nd-item-title">{{ n.title }}</span>
                  <span
                    class="nd-item-mastery"
                    :style="{ color: masteryColor(n.mastery_level) }"
                  >
                    {{ Math.round((n.mastery_level || 0) * 100) }}%
                  </span>
                  <svg
                    v-if="selectedNodeId === n.id"
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                  >
                    <polyline points="20 6 9 17 4 12" />
                  </svg>
                </button>
              </div>
            </div>
          </transition>
        </div>
      </div>

      <div class="config-divider" />

      <!-- 题型 -->
      <div class="config-section config-section--sm">
        <div class="config-label">题型</div>
        <div class="type-btns">
          <button
            v-for="t in quizTypes"
            :key="t.val"
            class="type-btn"
            :class="{ active: quizType === t.val }"
            @click="quizType = t.val"
          >
            {{ t.label }}
          </button>
        </div>
      </div>

      <div class="config-divider" />

      <!-- 操作 -->
      <div class="config-section config-section--action">
        <button
          class="btn btn-primary"
          :disabled="!selectedNodeId || generating"
          @click="startQuiz"
        >
          <svg
            v-if="!generating"
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.5"
          >
            <polygon points="5 3 19 12 5 21 5 3" />
          </svg>
          <svg
            v-else
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            class="spin-icon"
          >
            <path d="M21 12a9 9 0 11-6.219-8.56" />
          </svg>
          {{ generating ? "生成中..." : currentQuiz ? "换一题" : "开始出题" }}
        </button>
      </div>
    </div>

    <!-- ══ 空状态 ══ -->
    <div v-if="!currentQuiz && !generating && !genError" class="empty-state">
      <div class="empty-icon">🎯</div>
      <div class="empty-title">选择一个知识节点，开始练习</div>
      <div class="empty-desc">
        Agent 会根据节点内容和你的掌握程度，智能出题帮你巩固记忆
      </div>
    </div>

    <!-- ══ 生成错误 ══ -->
    <div v-if="genError" class="error-state card">
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="var(--red)"
        stroke-width="2"
      >
        <circle cx="12" cy="12" r="10" />
        <line x1="12" y1="8" x2="12" y2="12" />
        <line x1="12" y1="16" x2="12.01" y2="16" />
      </svg>
      <span>{{ genError }}</span>
      <button
        class="btn btn-ghost"
        style="margin-left: auto"
        @click="startQuiz"
      >
        重试
      </button>
    </div>

    <!-- ══ 题目卡片 ══ -->
    <transition name="card-in" mode="out-in">
      <div
        v-if="currentQuiz && !generating"
        :key="currentQuiz.id"
        class="question-card card"
      >
        <!-- 卡片头部 -->
        <div class="q-header">
          <span class="badge badge-brand">{{ quizTypeLabel }}</span>
          <span class="node-tag">
            <svg
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="3" />
              <path
                d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"
              />
            </svg>
            {{ selectedNodeTitle }}
          </span>
          <div class="q-timer" :class="{ warning: timeLeft < 15 }">
            <svg
              width="11"
              height="11"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            {{ timeLeft }}s
          </div>
        </div>

        <!-- 题目正文 -->
        <div class="q-body">
          <p class="q-text">
            {{ currentQuiz.question }}
          </p>
        </div>

        <!-- 选项 -->
        <div
          v-if="currentQuiz.options && currentQuiz.options.length"
          class="options-list"
        >
          <button
            v-for="(opt, i) in currentQuiz.options"
            :key="i"
            class="option-btn"
            :class="getOptionClass(i)"
            :disabled="answered"
            @click="selectOption(i)"
          >
            <span class="option-letter">{{ String.fromCharCode(65 + i) }}</span>
            <span class="option-text">{{ opt }}</span>
            <div v-if="answered && submitResult" class="option-indicator">
              <svg
                v-if="isCorrectOption(i)"
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
                v-else-if="selected === i"
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="3"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </div>
            <div
              v-else-if="answered && !submitResult && selected === i"
              class="option-indicator"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
                class="spin-icon"
              >
                <path d="M21 12a9 9 0 11-6.219-8.56" />
              </svg>
            </div>
          </button>
        </div>

        <!-- 填空题 / 简答题 -->
        <div v-else-if="isSubjective" class="subjective-area">
          <textarea
            v-model="subjectiveAnswer"
            class="subjective-input"
            :placeholder="
              currentQuiz.quiz_type === 'fill_in'
                ? '请输入填空答案（1~3个词或短句）'
                : '请输入你的答案（可多行）'
            "
            :rows="currentQuiz.quiz_type === 'fill_in' ? 2 : 5"
            :disabled="answered"
            @keydown.ctrl.enter="submitSubjective"
          />
          <div v-if="!answered" class="subjective-hint">
            {{
              currentQuiz.quiz_type === "fill_in" ? "" : "Ctrl+Enter 快速提交"
            }}
          </div>
        </div>

        <!-- 判断题 -->
        <div
          v-else-if="currentQuiz.quiz_type === 'true_false'"
          class="judge-btns"
        >
          <button
            class="judge-btn"
            :class="getJudgeClass(true)"
            :disabled="answered"
            @click="selectJudge(true)"
          >
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <polyline points="20 6 9 17 4 12" />
            </svg>
            正确
          </button>
          <button
            class="judge-btn"
            :class="getJudgeClass(false)"
            :disabled="answered"
            @click="selectJudge(false)"
          >
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
            错误
          </button>
        </div>

        <!-- 解析区 -->
        <transition name="slide-down">
          <div v-if="answered && submitResult" class="ai-analysis">
            <div class="aa-header">
              <div class="aa-agent">
                <div class="agent-avatar" style="width: 22px; height: 22px">
                  <svg
                    width="11"
                    height="11"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="white"
                    stroke-width="2"
                  >
                    <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                </div>
                <span>Agent 解析</span>
              </div>
              <!-- 主观题：显示评分 -->
              <div v-if="isSubjective" class="score-display">
                <span class="score-num" :class="scoreClass">{{
                  Math.round((submitResult.score || 0) * 100)
                }}</span>
                <span class="score-total">/100</span>
              </div>
              <!-- 客观题：显示对错 -->
              <span
                v-else
                class="result-badge"
                :class="submitResult.is_correct ? 'correct' : 'wrong'"
              >
                {{ submitResult.is_correct ? "✓ 回答正确" : "✗ 回答错误" }}
              </span>
            </div>
            <!-- 主观题：参考答案 -->
            <div v-if="isSubjective" class="aa-ref">
              <span class="aa-label">参考答案：</span>
              <span class="aa-ref-text">{{
                submitResult.correct_answer || currentQuiz.correct_answer
              }}</span>
            </div>
            <p class="aa-text">
              {{ currentQuiz.explanation }}
            </p>
            <div
              v-if="submitResult.mastery_delta !== undefined"
              class="aa-meta"
            >
              <span class="aa-label">掌握度变化：</span>
              <span
                class="mastery-change"
                :class="(submitResult.mastery_delta || 0) >= 0 ? 'up' : 'down'"
              >
                {{ (submitResult.mastery_delta || 0) >= 0 ? "+" : ""
                }}{{ Math.round((submitResult.mastery_delta || 0) * 100) }}%
              </span>
            </div>
          </div>
        </transition>

        <!-- 操作按钮 -->
        <div class="quiz-actions">
          <button
            v-if="!answered"
            class="btn btn-ghost"
            @click="showHint = !showHint"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            提示
          </button>
          <!-- 主观题提交按钮 -->
          <button
            v-if="isSubjective && !answered"
            class="btn btn-primary"
            :disabled="!subjectiveAnswer.trim() || submitting"
            style="margin-left: auto"
            @click="submitSubjective"
          >
            <svg
              v-if="!submitting"
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
            <svg
              v-else
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              class="spin-icon"
            >
              <path d="M21 12a9 9 0 11-6.219-8.56" />
            </svg>
            {{ submitting ? "AI 评分中..." : "提交答案" }}
          </button>
          <button
            v-if="answered"
            class="btn btn-primary"
            style="margin-left: auto"
            @click="startQuiz"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
            >
              <polyline points="23 4 23 10 17 10" />
              <path d="M20.49 15a9 9 0 11-2.12-9.36L23 10" />
            </svg>
            下一题
          </button>
        </div>

        <!-- 提示框 -->
        <transition name="slide-down">
          <div v-if="showHint && !answered" class="hint-box">
            <span
              class="badge badge-yellow"
              style="margin-bottom: 6px; display: inline-block"
              >提示</span
            >
            <p>
              {{
                currentQuiz.hint ||
                "仔细思考题目中的关键词，结合节点知识点作答。"
              }}
            </p>
          </div>
        </transition>
      </div>
    </transition>

    <!-- ══ 生成中骨架 ══ -->
    <div v-if="generating" class="skeleton-card card">
      <div class="sk-header">
        <div class="sk-badge" />
        <div class="sk-tag" />
      </div>
      <div class="sk-line sk-line--lg" />
      <div class="sk-line sk-line--md" />
      <div class="sk-options">
        <div v-for="i in 4" :key="i" class="sk-option" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from "vue";
import { useRoute } from "vue-router";
import { nodeApi } from "@/api/nodes.js";
import { quizApi } from "@/api/quizzes.js";

const route = useRoute();

// ── 节点列表 ──────────────────────────────────────────────────
const nodes = ref([]);
const loadingNodes = ref(true);
const selectedNodeId = ref(null);

async function loadNodes() {
  loadingNodes.value = true;
  try {
    const list = await nodeApi.getAll();
    nodes.value = list || [];
    // 优先选中从图谱跳转带来的 nodeId，否则默认选掌握度最低的节点
    if (nodes.value.length > 0) {
      const fromGraph = route.query.nodeId;
      if (fromGraph && nodes.value.find((n) => n.id === fromGraph)) {
        selectedNodeId.value = fromGraph;
      } else if (!selectedNodeId.value) {
        const sorted = [...nodes.value].sort(
          (a, b) => (a.mastery_level || 0) - (b.mastery_level || 0),
        );
        selectedNodeId.value = sorted[0].id;
      }
    }
  } catch (e) {
    console.error("加载节点失败:", e);
  } finally {
    loadingNodes.value = false;
  }
}

loadNodes();

const selectedNode = computed(() =>
  nodes.value.find((n) => n.id === selectedNodeId.value),
);
const selectedNodeTitle = computed(() => selectedNode.value?.title || "");

// ── 下拉选择器 ────────────────────────────────────────────────
const dropdownOpen = ref(false);
const dropdownRef = ref(null);
const searchInputRef = ref(null);
const nodeSearch = ref("");
const nodeSort = ref("mastery"); // mastery | alpha

const sortOptions = [
  { val: "mastery", label: "按掌握度" },
  { val: "alpha", label: "按名称" },
];

const filteredNodes = computed(() => {
  let list = nodes.value;
  if (nodeSearch.value.trim()) {
    const q = nodeSearch.value.trim().toLowerCase();
    list = list.filter((n) => n.title.toLowerCase().includes(q));
  }
  if (nodeSort.value === "mastery") {
    list = [...list].sort(
      (a, b) => (a.mastery_level || 0) - (b.mastery_level || 0),
    );
  } else {
    list = [...list].sort((a, b) => a.title.localeCompare(b.title, "zh"));
  }
  return list;
});

async function toggleDropdown() {
  dropdownOpen.value = !dropdownOpen.value;
  if (dropdownOpen.value) {
    await nextTick();
    searchInputRef.value?.focus();
  }
}

function selectNode(n) {
  selectedNodeId.value = n.id;
  dropdownOpen.value = false;
  nodeSearch.value = "";
}

// 点击外部关闭
function onClickOutside(e) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target)) {
    dropdownOpen.value = false;
  }
}
onMounted(() => document.addEventListener("mousedown", onClickOutside));
onUnmounted(() => {
  document.removeEventListener("mousedown", onClickOutside);
  clearInterval(timer);
});

function masteryColor(level) {
  if (!level) return "var(--text-dim)";
  if (level < 0.4) return "var(--red)";
  if (level < 0.7) return "#f59e0b";
  return "var(--green)";
}

// ── 题型 ──────────────────────────────────────────────────────
const quizTypes = [
  { val: "multiple_choice", label: "选择题" },
  { val: "true_false", label: "判断题" },
  { val: "fill_in", label: "填空题" },
  { val: "open_ended", label: "简答题" },
];
const quizType = ref("multiple_choice");

const isSubjective = computed(
  () =>
    currentQuiz.value?.quiz_type === "fill_in" ||
    currentQuiz.value?.quiz_type === "open_ended",
);

const quizTypeLabel = computed(() => {
  return quizTypes.find((t) => t.val === quizType.value)?.label || "选择题";
});

// ── 题目状态 ──────────────────────────────────────────────────
const currentQuiz = ref(null);
const generating = ref(false);
const genError = ref("");
const answered = ref(false);
const selected = ref(null); // 选择题：选中的选项 index
const judgeAnswer = ref(null); // 判断题：true/false
const subjectiveAnswer = ref(""); // 主观题：文本答案
const submitting = ref(false); // 主观题提交中（LLM评分需要时间）
const submitResult = ref(null);
const showHint = ref(false);

const scoreClass = computed(() => {
  const s = (submitResult.value?.score || 0) * 100;
  if (s >= 80) return "score-high";
  if (s >= 60) return "score-mid";
  return "score-low";
});

// 计分
const correctCount = ref(0);
const wrongCount = ref(0);
const totalCount = computed(() => correctCount.value + wrongCount.value);

// ── 计时器 ────────────────────────────────────────────────────
const timeLeft = ref(60);
let timer = null;

function startTimer() {
  clearInterval(timer);
  // 主观题给更多时间
  timeLeft.value =
    quizType.value === "open_ended"
      ? 300
      : quizType.value === "fill_in"
        ? 120
        : 60;
  timer = setInterval(() => {
    if (timeLeft.value > 0) {
      timeLeft.value--;
    } else {
      clearInterval(timer);
      // 超时自动提交错误
      if (!answered.value && currentQuiz.value) {
        autoSubmitTimeout();
      }
    }
  }, 1000);
}

async function autoSubmitTimeout() {
  answered.value = true;
  wrongCount.value++;
  try {
    submitResult.value = await quizApi.submit(
      currentQuiz.value.id,
      "__timeout__",
    );
  } catch (e) {
    console.error("自动提交超时失败", e);
    submitResult.value = { is_correct: false };
  }
}

// ── 出题 ──────────────────────────────────────────────────────
async function startQuiz() {
  if (!selectedNodeId.value || generating.value) return;
  generating.value = true;
  genError.value = "";
  currentQuiz.value = null;
  answered.value = false;
  selected.value = null;
  judgeAnswer.value = null;
  subjectiveAnswer.value = "";
  submitting.value = false;
  submitResult.value = null;
  showHint.value = false;
  clearInterval(timer);

  try {
    const quiz = await quizApi.generate(selectedNodeId.value, quizType.value);
    currentQuiz.value = quiz;
    startTimer();
  } catch (e) {
    genError.value = e.message || "出题失败，请重试";
  } finally {
    generating.value = false;
  }
}

// ── 答题（选择题）────────────────────────────────────────────
function isCorrectOption(i) {
  if (!currentQuiz.value || !submitResult.value) return false;
  const correct = currentQuiz.value.correct_answer;
  // correct_answer 可能是 "A"/"B"/"C"/"D" 或 index
  if (typeof correct === "number") return i === correct;
  return String.fromCharCode(65 + i) === correct.toUpperCase();
}

function getOptionClass(i) {
  if (!answered.value) return selected.value === i ? "selected" : "";
  // 后端还没返回结果时，只显示 selected 状态，不显示对错颜色
  if (!submitResult.value) return selected.value === i ? "selected" : "";
  if (isCorrectOption(i)) return "correct";
  if (selected.value === i) return "wrong";
  return "dimmed";
}

async function selectOption(i) {
  if (answered.value) return;
  selected.value = i;
  answered.value = true;
  submitting.value = true;
  showHint.value = false;
  clearInterval(timer);

  const answerStr = String.fromCharCode(65 + i);
  try {
    submitResult.value = await quizApi.submit(currentQuiz.value.id, answerStr);
    if (submitResult.value.is_correct) correctCount.value++;
    else wrongCount.value++;
  } catch (e) {
    console.log(e);
    // 本地判断兜底
    const correct = currentQuiz.value.correct_answer;
    const isCorrect =
      typeof correct === "number"
        ? correct === i
        : correct.toUpperCase() === answerStr;
    submitResult.value = { is_correct: isCorrect };
    if (isCorrect) correctCount.value++;
    else wrongCount.value++;
  } finally {
    submitting.value = false;
  }
}

// ── 答题（判断题）────────────────────────────────────────────
function getJudgeClass(val) {
  if (!answered.value) return judgeAnswer.value === val ? "selected" : "";
  // 后端还没返回结果时，只显示 selected 状态，不显示对错颜色
  if (!submitResult.value) return judgeAnswer.value === val ? "selected" : "";
  const isCorrect = submitResult.value.is_correct;
  // 根据后端返回的结果判断对错
  if (judgeAnswer.value === val && isCorrect) return "correct";
  if (judgeAnswer.value === val && !isCorrect) return "wrong";
  // 如果用户选错了，高亮正确答案
  if (!isCorrect && judgeAnswer.value !== val) return "correct";
  return "";
}

async function selectJudge(val) {
  if (answered.value) return;
  judgeAnswer.value = val;
  answered.value = true;
  submitting.value = true;
  showHint.value = false;
  clearInterval(timer);

  try {
    submitResult.value = await quizApi.submit(
      currentQuiz.value.id,
      String(val),
    );
    if (submitResult.value.is_correct) correctCount.value++;
    else wrongCount.value++;
  } catch (e) {
    console.log(e);
    const correct = currentQuiz.value.correct_answer;
    const correctBool =
      correct === "true" || correct === true || correct === "True";
    const isCorrect = val === correctBool;
    submitResult.value = { is_correct: isCorrect };
    if (isCorrect) correctCount.value++;
    else wrongCount.value++;
  } finally {
    submitting.value = false;
  }
}

// ── 答题（主观题）────────────────────────────────────────────
async function submitSubjective() {
  if (answered.value || !subjectiveAnswer.value.trim() || submitting.value)
    return;
  submitting.value = true;
  showHint.value = false;
  clearInterval(timer);

  try {
    submitResult.value = await quizApi.submit(
      currentQuiz.value.id,
      subjectiveAnswer.value.trim(),
    );
    answered.value = true;
    const score = submitResult.value.score || 0;
    if (score >= 0.6) correctCount.value++;
    else wrongCount.value++;
  } catch (e) {
    // 兜底：直接标记已答，不计分
    console.log("submitSubjective error:", e);
    submitResult.value = {
      is_correct: false,
      score: 0,
      correct_answer: currentQuiz.value.correct_answer,
    };
    answered.value = true;
    wrongCount.value++;
  } finally {
    submitting.value = false;
  }
}

// onUnmounted 已在上方 onClickOutside 注销处合并
</script>

<style scoped>
.quiz-page {
  padding: 28px 32px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Header */
.page-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
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

.session-stats {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 10px 18px;
}
.ss-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.ss-val {
  font-size: 18px;
  font-weight: 700;
  line-height: 1;
}
.ss-label {
  font-size: 10px;
  color: var(--text-muted);
}
.ss-divider {
  width: 1px;
  height: 28px;
  background: var(--border);
}

/* Config bar */
.config-bar {
  display: flex;
  align-items: flex-start;
  gap: 0;
  padding: 16px 20px;
  flex-wrap: wrap;
}
.config-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  flex: 1;
  min-width: 0;
}
.config-section--sm {
  flex: 0 0 auto;
}
.config-section--action {
  flex: 0 0 auto;
  align-self: flex-end;
}
.config-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.config-divider {
  width: 1px;
  background: var(--border);
  margin: 0 20px;
  align-self: stretch;
}

/* Node chips */
.node-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.node-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: var(--radius-full);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: var(--transition);
  white-space: nowrap;
}
.node-chip:hover {
  border-color: var(--brand-light);
  color: var(--text-primary);
}
.node-chip.active {
  background: var(--brand-dim);
  border-color: var(--border-active);
  color: var(--brand-light);
}
.chip-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.chip-mastery {
  font-size: 10px;
  color: var(--text-muted);
}
.node-chip.active .chip-mastery {
  color: var(--brand-light);
  opacity: 0.7;
}

.no-nodes {
  font-size: 12px;
  color: var(--text-muted);
  padding: 4px 0;
}
.loading-nodes {
  display: flex;
  gap: 6px;
}
.skeleton-chip {
  height: 32px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  animation: pulse 1.5s ease-in-out infinite;
}

/* Node dropdown */
.node-dropdown {
  position: relative;
  width: 260px;
}
.nd-trigger {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: var(--transition);
  text-align: left;
}
.nd-trigger:hover,
.nd-trigger.open {
  border-color: var(--brand-light);
  background: var(--bg-card);
}
.nd-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nd-mastery {
  font-size: 11px;
  color: var(--text-muted);
  flex-shrink: 0;
}
.nd-placeholder {
  flex: 1;
  color: var(--text-muted);
}
.nd-arrow {
  margin-left: auto;
  flex-shrink: 0;
  color: var(--text-muted);
  transition: transform 0.2s;
}
.nd-trigger.open .nd-arrow {
  transform: rotate(180deg);
}

.nd-panel {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  width: 280px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3);
  z-index: 100;
  overflow: hidden;
}
.nd-search {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-muted);
}
.nd-search-input {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 12px;
}
.nd-search-input::placeholder {
  color: var(--text-dim);
}
.nd-clear {
  background: none;
  border: none;
  cursor: pointer;
  color: var(--text-muted);
  padding: 0;
  display: flex;
}
.nd-clear:hover {
  color: var(--text-primary);
}

.nd-sort-tabs {
  display: flex;
  gap: 0;
  padding: 6px 8px;
  border-bottom: 1px solid var(--border);
}
.nd-sort-tab {
  flex: 1;
  padding: 4px 0;
  font-size: 11px;
  font-weight: 500;
  background: none;
  border: 1px solid var(--border);
  color: var(--text-muted);
  cursor: pointer;
  transition: var(--transition);
}
.nd-sort-tab:first-child {
  border-radius: var(--radius-sm) 0 0 var(--radius-sm);
}
.nd-sort-tab:last-child {
  border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
  border-left: none;
}
.nd-sort-tab.active {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}

.nd-list {
  max-height: 240px;
  overflow-y: auto;
  padding: 4px;
}
.nd-list::-webkit-scrollbar {
  width: 4px;
}
.nd-list::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 2px;
}
.nd-empty {
  padding: 16px;
  text-align: center;
  font-size: 12px;
  color: var(--text-muted);
}
.nd-item {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: none;
  border: none;
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: var(--transition);
  text-align: left;
}
.nd-item:hover {
  background: var(--bg-hover);
}
.nd-item.active {
  background: var(--brand-dim);
  color: var(--brand-light);
}
.nd-item-title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.nd-item-mastery {
  font-size: 11px;
  font-weight: 600;
  flex-shrink: 0;
}

/* Dropdown transition */
.dropdown-enter-active,
.dropdown-leave-active {
  transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
.dropdown-enter-from,
.dropdown-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* Type buttons */
.type-btns {
  display: flex;
  gap: 4px;
}
.type-btn {
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition);
}
.type-btn.active {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}

/* Empty / Error state */
.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 64px 32px;
  gap: 12px;
  text-align: center;
}
.empty-icon {
  font-size: 48px;
  line-height: 1;
}
.empty-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.empty-desc {
  font-size: 13px;
  color: var(--text-muted);
  max-width: 360px;
  line-height: 1.6;
}

.error-state {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 14px 18px;
  color: var(--red);
  font-size: 13px;
}

/* Question card */
.question-card {
  padding: 28px 32px;
}

.q-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 24px;
}
.node-tag {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--bg-hover);
  padding: 3px 8px;
  border-radius: var(--radius-full);
  border: 1px solid var(--border);
}
.q-timer {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-secondary);
  background: var(--bg-hover);
  padding: 4px 10px;
  border-radius: var(--radius-full);
  transition: var(--transition);
}
.q-timer.warning {
  color: var(--red);
  background: var(--red-dim);
}

.q-body {
  margin-bottom: 24px;
}
.q-text {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-primary);
  line-height: 1.75;
}

/* Options */
.options-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}
.option-btn {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 13px 16px;
  border-radius: var(--radius-md);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 13px;
  cursor: pointer;
  transition: var(--transition);
  text-align: left;
  width: 100%;
}
.option-btn:hover:not(:disabled) {
  border-color: var(--brand-light);
  background: var(--brand-dim);
}
.option-btn.selected {
  border-color: var(--brand);
  background: var(--brand-dim);
}
.option-btn.correct {
  border-color: var(--green);
  background: var(--green-dim);
  color: var(--green);
}
.option-btn.wrong {
  border-color: var(--red);
  background: var(--red-dim);
  color: var(--red);
}
.option-btn.dimmed {
  opacity: 0.35;
}
.option-letter {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.06);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
}
.option-text {
  flex: 1;
}
.option-indicator {
  margin-left: auto;
}

/* Subjective input */
.subjective-area {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 20px;
}
.subjective-input {
  width: 100%;
  padding: 12px 14px;
  border-radius: var(--radius-md);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 14px;
  line-height: 1.7;
  resize: vertical;
  font-family: inherit;
  transition: var(--transition);
  box-sizing: border-box;
}
.subjective-input:focus {
  outline: none;
  border-color: var(--brand-light);
  background: var(--bg-card);
}
.subjective-input:disabled {
  opacity: 0.7;
  cursor: not-allowed;
}
.subjective-hint {
  font-size: 11px;
  color: var(--text-dim);
  text-align: right;
}

/* Score display */
.score-display {
  display: flex;
  align-items: baseline;
  gap: 2px;
}
.score-num {
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
}
.score-num.score-high {
  color: var(--green);
}
.score-num.score-mid {
  color: #f59e0b;
}
.score-num.score-low {
  color: var(--red);
}
.score-total {
  font-size: 12px;
  color: var(--text-muted);
}

/* Reference answer */
.aa-ref {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.aa-ref-text {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 500;
  line-height: 1.6;
}

/* Judge buttons */
.judge-btns {
  display: flex;
  gap: 12px;
  margin-bottom: 20px;
}
.judge-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 16px;
  border-radius: var(--radius-md);
  font-size: 14px;
  font-weight: 600;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-primary);
  cursor: pointer;
  transition: var(--transition);
}
.judge-btn:hover:not(:disabled) {
  border-color: var(--brand-light);
  background: var(--brand-dim);
}
.judge-btn.selected {
  border-color: var(--brand);
  background: var(--brand-dim);
}
.judge-btn.correct {
  border-color: var(--green);
  background: var(--green-dim);
  color: var(--green);
}
.judge-btn.wrong {
  border-color: var(--red);
  background: var(--red-dim);
  color: var(--red);
}

/* AI Analysis */
.ai-analysis {
  margin-bottom: 20px;
  padding: 16px 18px;
  background: linear-gradient(
    135deg,
    rgba(99, 102, 241, 0.06),
    rgba(168, 85, 247, 0.06)
  );
  border: 1px solid rgba(99, 102, 241, 0.2);
  border-radius: var(--radius-md);
}
.aa-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}
.aa-agent {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--brand-light);
}
.result-badge {
  font-size: 12px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: var(--radius-full);
}
.result-badge.correct {
  background: var(--green-dim);
  color: var(--green);
}
.result-badge.wrong {
  background: var(--red-dim);
  color: var(--red);
}
.aa-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.75;
  margin-bottom: 10px;
}
.aa-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}
.aa-label {
  color: var(--text-muted);
}
.mastery-change {
  font-weight: 600;
}
.mastery-change.up {
  color: var(--green);
}
.mastery-change.down {
  color: var(--red);
}

/* Actions */
.quiz-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}
.hint-box {
  margin-top: 12px;
  padding: 14px 16px;
  background: rgba(245, 158, 11, 0.06);
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: var(--radius-md);
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
}

/* Skeleton */
.skeleton-card {
  padding: 28px 32px;
}
.sk-header {
  display: flex;
  gap: 8px;
  margin-bottom: 24px;
}
.sk-badge {
  width: 56px;
  height: 20px;
  border-radius: var(--radius-full);
  background: var(--bg-hover);
  animation: pulse 1.5s ease-in-out infinite;
}
.sk-tag {
  width: 100px;
  height: 20px;
  border-radius: var(--radius-full);
  background: var(--bg-hover);
  animation: pulse 1.5s ease-in-out infinite 0.1s;
}
.sk-line {
  height: 16px;
  border-radius: 4px;
  background: var(--bg-hover);
  margin-bottom: 10px;
  animation: pulse 1.5s ease-in-out infinite;
}
.sk-line--lg {
  width: 90%;
}
.sk-line--md {
  width: 65%;
}
.sk-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 24px;
}
.sk-option {
  height: 48px;
  border-radius: var(--radius-md);
  background: var(--bg-hover);
  animation: pulse 1.5s ease-in-out infinite;
}
.sk-option:nth-child(2) {
  animation-delay: 0.1s;
}
.sk-option:nth-child(3) {
  animation-delay: 0.2s;
}
.sk-option:nth-child(4) {
  animation-delay: 0.3s;
}

/* Transitions */
.card-in-enter-active {
  transition: all 0.28s cubic-bezier(0.4, 0, 0.2, 1);
}
.card-in-enter-from {
  opacity: 0;
  transform: translateY(12px);
}
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.28s ease;
}
.slide-down-enter-from {
  opacity: 0;
  transform: translateY(-8px);
}
.slide-down-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}

.spin-icon {
  animation: spin 0.8s linear infinite;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.4;
  }
}
</style>
