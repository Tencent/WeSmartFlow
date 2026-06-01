<template>
  <div
    class="quiz-card"
    :class="[`type-${quiz?.quiz_type || 'loading'}`, { answered: answered }]"
  >
    <!-- 头部 -->
    <div class="quiz-card-header">
      <div class="quiz-card-title-row">
        <svg
          class="quiz-card-icon"
          width="14"
          height="14"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <circle cx="12" cy="12" r="10" />
          <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <span class="quiz-card-badge">{{ typeLabel }}</span>
        <span
          v-if="answered"
          class="quiz-card-result"
          :class="quiz.is_correct ? 'correct' : 'wrong'"
        >
          {{ quiz.is_correct ? "✓ 回答正确" : "✗ 回答错误" }}
        </span>
      </div>
    </div>

    <!-- 加载中 -->
    <div v-if="loading" class="quiz-card-loading">
      <div class="quiz-card-spinner"></div>
      <span>加载题目中...</span>
    </div>

    <!-- 错误 -->
    <div v-else-if="fetchError" class="quiz-card-error">
      <svg
        width="13"
        height="13"
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
      <button class="quiz-card-btn-sm" @click="fetchQuiz">重试</button>
    </div>

    <!-- 题目主体 -->
    <template v-else-if="quiz">
      <!-- 题目文本 -->
      <div class="quiz-card-question" v-html="renderMd(quiz.question)"></div>

      <!-- 选择题选项 -->
      <div
        v-if="quiz.quiz_type === 'multiple_choice'"
        class="quiz-card-options"
      >
        <button
          v-for="opt in quiz.options"
          :key="opt"
          class="quiz-card-option"
          :class="optionClass(opt)"
          :disabled="answered || submitting"
          @click="selectOption(opt)"
        >
          <span class="option-letter">{{ opt[0] }}</span>
          <span
            class="option-text"
            v-html="renderMd(opt.slice(2).trim())"
          ></span>
        </button>
      </div>

      <!-- 判断题 -->
      <div v-else-if="quiz.quiz_type === 'true_false'" class="quiz-card-tf">
        <button
          class="quiz-card-tf-btn"
          :class="tfClass('true')"
          :disabled="answered || submitting"
          @click="selectTF('true')"
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
          class="quiz-card-tf-btn"
          :class="tfClass('false')"
          :disabled="answered || submitting"
          @click="selectTF('false')"
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

      <!-- 填空 / 简答 -->
      <div v-else class="quiz-card-text-input">
        <textarea
          v-model="textAnswer"
          class="quiz-card-textarea"
          :placeholder="
            quiz.quiz_type === 'fill_in' ? '请填写答案...' : '请输入你的回答...'
          "
          :rows="quiz.quiz_type === 'fill_in' ? 2 : 4"
          :disabled="answered || submitting"
        />
      </div>

      <!-- 提交按钮（未作答时显示） -->
      <div v-if="!answered" class="quiz-card-footer">
        <button
          class="quiz-card-submit"
          :disabled="!canSubmit || submitting"
          @click="submit"
        >
          <span v-if="submitting" class="quiz-card-spinner sm"></span>
          {{ submitting ? "评分中..." : "提交答案" }}
        </button>
      </div>

      <!-- 答案解析（作答后显示） -->
      <div v-if="answered" class="quiz-card-explanation">
        <div class="explanation-label">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="16" x2="12" y2="12" />
            <line x1="12" y1="8" x2="12.01" y2="8" />
          </svg>
          解析
        </div>
        <div class="explanation-correct">
          正确答案：<strong v-html="renderMd(quiz.correct_answer)"></strong>
        </div>
        <div class="explanation-text" v-html="renderMd(quiz.explanation)"></div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from "vue";
import { api } from "../../api/base.js";
import { marked } from "marked";
import DOMPurify from "dompurify";
import katex from "katex";
import "katex/dist/katex.min.css";

marked.setOptions({ breaks: true, gfm: true });

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
  /** 题目 ID（quiz_id） */
  quizId: { type: String, required: true },
});

const emit = defineEmits(["answered"]);

const loading = ref(true);
const fetchError = ref("");
const submitting = ref(false);
const quiz = ref(null);

// 用户选择
const selectedOption = ref(""); // 选择题
const selectedTF = ref(""); // 判断题
const textAnswer = ref(""); // 填空/简答

const answered = computed(() => quiz.value?.answered ?? false);

const typeLabel = computed(() => {
  const map = {
    multiple_choice: "单选题",
    true_false: "判断题",
    fill_in: "填空题",
    open_ended: "简答题",
  };
  return map[quiz.value?.quiz_type] || "题目";
});

const canSubmit = computed(() => {
  if (!quiz.value) return false;
  switch (quiz.value.quiz_type) {
    case "multiple_choice":
      return !!selectedOption.value;
    case "true_false":
      return !!selectedTF.value;
    default:
      return textAnswer.value.trim().length > 0;
  }
});

// ── 选项样式 ──────────────────────────────────────────────────────────
function optionClass(opt) {
  const letter = opt[0].toUpperCase();
  if (!answered.value) {
    return selectedOption.value === letter ? "selected" : "";
  }
  const correctLetter = (quiz.value.correct_answer || "")[0]?.toUpperCase();
  if (letter === correctLetter) return "correct";
  if (letter === selectedOption.value && letter !== correctLetter)
    return "wrong";
  return "dim";
}

function tfClass(val) {
  if (!answered.value) {
    return selectedTF.value === val ? "selected" : "";
  }
  const correctVal = isCorrectTF(quiz.value.correct_answer) ? "true" : "false";
  if (val === correctVal) return "correct";
  if (val === selectedTF.value && val !== correctVal) return "wrong";
  return "dim";
}

function isCorrectTF(answer) {
  const trueVals = ["true", "正确", "对", "是", "yes", "t", "1"];
  return trueVals.includes((answer || "").trim().toLowerCase());
}

// ── 交互 ──────────────────────────────────────────────────────────────
function selectOption(opt) {
  if (answered.value) return;
  selectedOption.value = opt[0].toUpperCase();
}

function selectTF(val) {
  if (answered.value) return;
  selectedTF.value = val;
}

// ── 数据拉取 ──────────────────────────────────────────────────────────
async function fetchQuiz() {
  if (!props.quizId) return;
  loading.value = true;
  fetchError.value = "";
  quiz.value = null;

  try {
    const data = await api.get(`/api/quiz/${props.quizId}`);
    quiz.value = data;
    // 已作答时恢复用户答案
    if (data.answered && data.user_answer) {
      if (data.quiz_type === "multiple_choice") {
        selectedOption.value = (data.user_answer || "")[0]?.toUpperCase() || "";
      } else if (data.quiz_type === "true_false") {
        selectedTF.value = data.user_answer;
      } else {
        textAnswer.value = data.user_answer;
      }
    }
  } catch (e) {
    fetchError.value = e.message || "加载失败";
  } finally {
    loading.value = false;
  }
}

// ── 提交 ──────────────────────────────────────────────────────────────
async function submit() {
  if (!canSubmit.value || submitting.value) return;
  submitting.value = true;

  // eslint-disable-next-line no-useless-assignment
  let answer = "";
  switch (quiz.value.quiz_type) {
    case "multiple_choice":
      answer = selectedOption.value;
      break;
    case "true_false":
      answer = selectedTF.value;
      break;
    default:
      answer = textAnswer.value.trim();
  }

  try {
    const result = await api.post(`/api/quiz/${props.quizId}/submit`, {
      answer,
    });
    // 将服务端返回的答案/解析合并回 quiz
    quiz.value = {
      ...quiz.value,
      answered: true,
      is_correct: result.is_correct,
      correct_answer: result.correct_answer,
      explanation: result.explanation,
      user_answer: answer,
    };
    emit("answered", {
      ...result,
      quizId: props.quizId,
      question: quiz.value.question,
      options: quiz.value.options || [],
      user_answer: answer,
      quiz_type: quiz.value.quiz_type,
    });
  } catch (e) {
    // 提交失败不阻断，仅 console 提示
    console.error("提交答案失败:", e);
  } finally {
    submitting.value = false;
  }
}

watch(
  () => props.quizId,
  () => {
    fetchQuiz();
  },
);
onMounted(() => {
  fetchQuiz();
});

defineExpose({ reload: fetchQuiz });
</script>

<style scoped>
.quiz-card {
  border-radius: var(--radius-lg, 10px);
  border: 1px solid var(--border, #e5e7eb);
  background: var(--bg-card, #fff);
  overflow: hidden;
  transition: border-color 0.2s;
}

.quiz-card:hover {
  border-color: var(--border-hover, #d1d5db);
}

/* 头部 */
.quiz-card-header {
  padding: 10px 14px 8px;
  border-bottom: 1px solid var(--border, #e5e7eb);
}

.quiz-card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.quiz-card-icon {
  color: var(--brand, #4f46e5);
  flex-shrink: 0;
}

.quiz-card-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--brand, #4f46e5);
  background: var(--brand-dim, rgba(79, 70, 229, 0.08));
  padding: 2px 8px;
  border-radius: 20px;
}

.quiz-card-result {
  margin-left: auto;
  font-size: 12px;
  font-weight: 600;
  padding: 2px 10px;
  border-radius: 20px;
}

.quiz-card-result.correct {
  color: var(--green, #22c55e);
  background: var(--green-dim, rgba(34, 197, 94, 0.1));
}

.quiz-card-result.wrong {
  color: var(--red, #ef4444);
  background: var(--red-dim, rgba(239, 68, 68, 0.08));
}

/* 加载 */
.quiz-card-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 28px;
  font-size: 12px;
  color: var(--text-muted, #9ca3af);
}

/* 错误 */
.quiz-card-error {
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

.quiz-card-btn-sm {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid rgba(239, 68, 68, 0.3);
  background: transparent;
  color: var(--red, #ef4444);
  font-size: 12px;
  cursor: pointer;
}

/* 题目文本 */
.quiz-card-question {
  padding: 14px 16px 10px;
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary, #111);
  line-height: 1.65;
}

/* 选择题选项 */
.quiz-card-options {
  padding: 0 12px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.quiz-card-option {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius-sm, 6px);
  border: 1.5px solid var(--border, #e5e7eb);
  background: transparent;
  cursor: pointer;
  text-align: left;
  transition: all 0.15s;
  font-size: 13px;
  color: var(--text-primary, #111);
  width: 100%;
}

.quiz-card-option:not(:disabled):hover {
  border-color: var(--brand, #4f46e5);
  background: var(--brand-dim, rgba(79, 70, 229, 0.04));
}

.quiz-card-option.selected {
  border-color: var(--brand, #4f46e5);
  background: var(--brand-dim, rgba(79, 70, 229, 0.08));
  color: var(--brand, #4f46e5);
}

.quiz-card-option.correct {
  border-color: var(--green, #22c55e);
  background: rgba(34, 197, 94, 0.08);
  color: var(--green, #22c55e);
}

.quiz-card-option.wrong {
  border-color: var(--red, #ef4444);
  background: rgba(239, 68, 68, 0.06);
  color: var(--red, #ef4444);
}

.quiz-card-option.dim {
  opacity: 0.45;
}

.quiz-card-option:disabled {
  cursor: default;
}

.option-letter {
  font-weight: 700;
  font-size: 12px;
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1.5px solid currentColor;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-top: 1px;
}

.option-text {
  flex: 1;
  line-height: 1.5;
}

/* 判断题 */
.quiz-card-tf {
  padding: 0 12px 12px;
  display: flex;
  gap: 10px;
}

.quiz-card-tf-btn {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px;
  border-radius: var(--radius-sm, 6px);
  border: 1.5px solid var(--border, #e5e7eb);
  background: transparent;
  cursor: pointer;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary, #111);
  transition: all 0.15s;
}

.quiz-card-tf-btn:not(:disabled):hover {
  border-color: var(--brand, #4f46e5);
  background: var(--brand-dim, rgba(79, 70, 229, 0.04));
}

.quiz-card-tf-btn.selected {
  border-color: var(--brand, #4f46e5);
  background: var(--brand-dim, rgba(79, 70, 229, 0.08));
  color: var(--brand, #4f46e5);
}

.quiz-card-tf-btn.correct {
  border-color: var(--green, #22c55e);
  background: rgba(34, 197, 94, 0.08);
  color: var(--green, #22c55e);
}

.quiz-card-tf-btn.wrong {
  border-color: var(--red, #ef4444);
  background: rgba(239, 68, 68, 0.06);
  color: var(--red, #ef4444);
}

.quiz-card-tf-btn.dim {
  opacity: 0.45;
}

.quiz-card-tf-btn:disabled {
  cursor: default;
}

/* 填空/简答 */
.quiz-card-text-input {
  padding: 0 12px 12px;
}

.quiz-card-textarea {
  width: 100%;
  padding: 9px 12px;
  border-radius: var(--radius-sm, 6px);
  border: 1.5px solid var(--border, #e5e7eb);
  background: var(--bg-input, #f9fafb);
  color: var(--text-primary, #111);
  font-size: 13px;
  line-height: 1.6;
  resize: vertical;
  outline: none;
  transition: border-color 0.15s;
  box-sizing: border-box;
  font-family: inherit;
}

.quiz-card-textarea:focus {
  border-color: var(--brand, #4f46e5);
  background: var(--bg-card, #fff);
}

.quiz-card-textarea:disabled {
  opacity: 0.7;
  cursor: default;
}

/* 提交按钮 */
.quiz-card-footer {
  padding: 0 12px 12px;
}

.quiz-card-submit {
  width: 100%;
  padding: 9px;
  border-radius: var(--radius-sm, 6px);
  border: none;
  background: var(--brand, #4f46e5);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  transition: opacity 0.15s;
}

.quiz-card-submit:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.quiz-card-submit:not(:disabled):hover {
  opacity: 0.88;
}

/* 解析 */
.quiz-card-explanation {
  margin: 0 12px 12px;
  padding: 12px;
  border-radius: var(--radius-sm, 6px);
  background: var(--bg-subtle, #f8fafc);
  border: 1px solid var(--border, #e5e7eb);
  font-size: 13px;
}

.explanation-label {
  display: flex;
  align-items: center;
  gap: 5px;
  font-weight: 600;
  color: var(--text-secondary, #6b7280);
  font-size: 12px;
  margin-bottom: 6px;
}

.explanation-correct {
  color: var(--text-secondary, #6b7280);
  font-size: 12px;
  margin-bottom: 6px;
}

.explanation-correct strong {
  color: var(--green, #22c55e);
}

.explanation-text {
  color: var(--text-primary, #111);
  line-height: 1.65;
}

/* markdown / latex 渲染内容样式重置 */
.quiz-card-question :deep(p),
.explanation-text :deep(p) {
  margin: 0 0 4px;
}
.quiz-card-question :deep(p:last-child),
.explanation-text :deep(p:last-child) {
  margin-bottom: 0;
}
.option-text :deep(p) {
  margin: 0;
  display: inline;
}
.quiz-card-question :deep(.katex-display),
.explanation-text :deep(.katex-display) {
  margin: 6px 0;
}
.explanation-correct :deep(p) {
  display: inline;
  margin: 0;
}

/* spinner */
.quiz-card-spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border, #e5e7eb);
  border-top-color: var(--brand, #4f46e5);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  flex-shrink: 0;
}

.quiz-card-spinner.sm {
  width: 13px;
  height: 13px;
  border-color: rgba(255, 255, 255, 0.4);
  border-top-color: #fff;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
