/**
 * 测验 API
 * POST /api/quiz/generate/:node_id   为节点生成题目
 * POST /api/quiz/:quiz_id/submit     提交答案
 */
import { api } from "./base.js";

export const quizApi = {
  // 为某节点生成一道题
  generate: (nodeId, quizType = "multiple_choice", sessionId = null) => {
    const params = new URLSearchParams({ quiz_type: quizType });
    if (sessionId) params.append("session_id", sessionId);
    return api.post(`/api/quiz/generate/${nodeId}?${params}`);
  },

  // 提交答案，返回评分 + 掌握度变化
  submit: (quizId, answer) =>
    api.post(`/api/quiz/${quizId}/submit`, { answer }),
};
