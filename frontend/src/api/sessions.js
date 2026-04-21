/**
 * 学习会话 API
 * GET  /api/sessions              历史会话列表
 * POST /api/sessions              创建新会话
 * GET  /api/sessions/:id          会话详情（含消息历史）
 * POST /api/sessions/:id/chat/stream  发送消息（SSE 流式）
 * PATCH /api/sessions/:id/duration 记录学习时长
 */
import { api, BASE_URL } from "./base.js";

// ── SSE 调试开关 ──────────────────────────────────────────────
// 设为 true 后，浏览器控制台会打印每一条原始 SSE 数据
const SSE_DEBUG = false;

function sseLog(type, data) {
  if (!SSE_DEBUG && !window.__SSE_DEBUG) return;
  const stylemap = {
    thinking: "color:#a78bfa",
    tool_call: "color:#38bdf8",
    tool_result: "color:#34d399",
    file_created: "color:#fb923c",
    node_created: "color:#f472b6",
    mastery_updated: "color:#facc15",
    done: "color:#4ade80;font-weight:bold",
    error: "color:#f87171;font-weight:bold",
    text_reply: "color:#94a3b8",
  };

  const style = stylemap[type] || "color:#cbd5e1";
  console.log(`%c[SSE] ${type}`, style, data);
}

// ── SSE 事件分派 ─────────────────────────────────────────────
/**
 * 根据回调对象构建 "事件类型 → 处理函数" 查找表。
 * 未在表中的事件类型会被忽略。
 */
function buildSSEDispatcher(callbacks) {
  const {
    onTextReply,
    onThinking,
    onToolCall,
    onToolResult,
    onFileCreated,
    onNodeCreated,
    onMasteryUpdated,
    onDone,
    onError,
  } = callbacks;

  return {
    text_reply: (d) => onTextReply?.(d.text),
    thinking: (d) => onThinking?.(d.content, d.step),
    tool_call: (d) => onToolCall?.(d.tool, d.args, d.step),
    tool_result: (d) => onToolResult?.(d.tool, d.result, d.step),
    file_created: (d) => onFileCreated?.(d.file_id),
    node_created: (d) => onNodeCreated?.(d.node_id, d.title),
    mastery_updated: (d) => onMasteryUpdated?.(d.node_id, d.delta),
    done: (d) => onDone?.({ mastery_changes: d.mastery_changes || {} }),
    error: (d) => onError?.(new Error(d.message)),
  };
}

/** 解析一行 SSE 文本为 data 对象；非 data 行或解析失败返回 null。 */
function parseSSELine(line) {
  if (!line.startsWith("data: ")) return null;
  const raw = line.slice(6).trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

/**
 * 读取 SSE 响应流并逐事件派发。
 * 按行切分，保留未完成的尾部到下一次迭代。
 */
async function readSSEStream(response, dispatcher) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop(); // 保留未完成的行

    for (const line of lines) {
      const data = parseSSELine(line);
      if (!data) continue;
      sseLog(data.type, data);
      dispatcher[data.type]?.(data);
    }
  }
}

/** 处理非 2xx 响应：把后端错误消息转成 Error 抛给 onError。 */
async function handleSSEError(response, onError) {
  const err = await response.json().catch(() => ({}));
  onError?.(new Error(err.message || `HTTP ${response.status}`));
}

export const sessionApi = {
  // 获取历史会话列表（按时间倒序）
  getAll: () => api.get("/api/sessions"),

  // 获取单个会话详情（含消息历史）
  getById: (id) => api.get(`/api/sessions/${id}`),

  // 创建新会话
  // params: { topic?, node_ids? }
  create: (params) => api.post("/api/sessions", params),

  /**
   * 发送消息（SSE 流式）
   * 使用 fetch + ReadableStream 解析，不用 EventSource（因为需要 POST）
   *
   * SSE 事件类型（通过 data.type 区分）：
   *   thinking      — LLM 推理步骤  { type, content, step }
   *   tool_call     — 工具调用      { type, tool, args, step }
   *   tool_result   — 工具结果      { type, tool, result, step }
   *   text_reply    — 最终回复文本  { type, text }   （一次性完整文本）
   *   done          — 回复完成      { type, mastery_changes }
   *   file_created  — 文件生成      { type, file_id }
   *   node_created  — 节点创建      { type, node_id, title }
   *   mastery_updated — 掌握度更新  { type, node_id, delta }
   *   error         — 错误          { type, message }
   *
   * @param {string} sessionId
   * @param {string} content
   * @param {object} callbacks
   *   onTextReply(text)                   — 收到完整的回复文本（一次性）
   *   onThinking(content, step)           — LLM 推理步骤
   *   onToolCall(tool, args, step)        — 工具调用开始
   *   onToolResult(tool, result, step)    — 工具调用完成
   *   onFileCreated(fileId)               — 文件生成完毕
   *   onNodeCreated(nodeId, title)        — 节点创建
   *   onMasteryUpdated(nodeId, delta)     — 掌握度更新
   *   onDone({ mastery_changes })         — 全部完成
   *   onError(error)                      — 出错
   * @returns {AbortController} 用于取消请求
   */
  streamMessage: (sessionId, content, callbacks = {}) => {
    const dispatcher = buildSSEDispatcher(callbacks);
    const { onError } = callbacks;
    const controller = new AbortController();

    fetch(`${BASE_URL}/api/sessions/${sessionId}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
      signal: controller.signal,
    })
      .then(async (res) => {
        if (!res.ok) {
          await handleSSEError(res, onError);
          return;
        }
        await readSSEStream(res, dispatcher);
      })
      .catch((err) => {
        if (err.name !== "AbortError") onError?.(err);
      });

    return controller;
  },

  // 记录本次会话学习时长（前端离开页面时调用，minutes 为整数分钟数）
  recordDuration: (id, minutes) =>
    api.patch(`/api/sessions/${id}/duration`, { minutes }),
};
