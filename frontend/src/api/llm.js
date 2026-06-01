/**
 * 轻量级 LLM 问答 API
 * POST /api/llm/quick-ask  纯 LLM 流式问答（不走 Agent）
 */
import { api } from "./base.js";

/**
 * 解析 SSE 行
 */
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

export const llmApi = {
  /**
   * 轻量级"问AI"流式接口
   *
   * @param {object} params
   * @param {string} params.question - 用户的问题或选中的文本
   * @param {string} [params.context] - 可选的学习上下文
   * @param {object} callbacks
   * @param {function} callbacks.onTextChunk - (delta: string) => void
   * @param {function} callbacks.onDone - () => void
   * @param {function} callbacks.onError - (error: Error) => void
   * @returns {AbortController} 用于取消请求
   */
  quickAsk: ({ question, context = "" }, callbacks = {}) => {
    const { onTextChunk, onDone, onError } = callbacks;
    const controller = new AbortController();

    api
      .postRaw("/api/llm/quick-ask", {
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, context }),
        signal: controller.signal,
      })
      .then(async (res) => {
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          onError?.(
            new Error(err.message || err.detail || `HTTP ${res.status}`),
          );
          return;
        }

        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop();

          for (const line of lines) {
            const data = parseSSELine(line);
            if (!data) continue;

            if (data.type === "text_chunk") {
              onTextChunk?.(data.delta);
            } else if (data.type === "done") {
              onDone?.();
            } else if (data.type === "error") {
              onError?.(new Error(data.message));
            }
          }
        }

        // 处理 buffer 中剩余的数据
        if (buffer.trim()) {
          const data = parseSSELine(buffer);
          if (data) {
            if (data.type === "text_chunk") onTextChunk?.(data.delta);
            else if (data.type === "done") onDone?.();
            else if (data.type === "error") onError?.(new Error(data.message));
          }
        }
      })
      .catch((err) => {
        if (err.name !== "AbortError") onError?.(err);
      });

    return controller;
  },
};
