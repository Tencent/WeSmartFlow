/**
 * 交互式可视化（EduViz）API
 *
 * 对应后端 routers/viz.py
 */
import { api, BASE_URL, authHeaders } from "./base.js";

/**
 * 调用后端 generate_interactive_viz 工具生成一个新的可视化
 * @param {Object} payload
 * @param {string} payload.title 标题
 * @param {string} payload.concept 核心概念描述
 * @param {string} [payload.interaction_hint] 交互形式建议
 * @param {string[]} [payload.node_ids] 关联的知识节点 ID
 * @param {string} [payload.session_id] 所属会话 ID
 * @returns {Promise<{ok: boolean, viz_id?: string, error?: string}>}
 */
export function generateViz(payload) {
  return api.post("/api/viz/generate", payload);
}

/**
 * 拉取 viz.js 源代码（纯文本）
 * @param {string} vizId
 * @returns {Promise<string>}
 */
export async function fetchVizCode(vizId) {
  const url = `${BASE_URL}/api/viz/${vizId}/code`;
  const res = await fetch(url, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error(`加载可视化代码失败: HTTP ${res.status}`);
  }
  return res.text();
}

/**
 * 获取可视化元信息
 * @param {string} vizId
 */
export function fetchVizMeta(vizId) {
  return api.get(`/api/viz/${vizId}/meta`);
}

/**
 * 列出当前用户的可视化（按时间倒序）
 * @param {number} [limit=20]
 */
export function listViz(limit = 20) {
  return api.get(`/api/viz?limit=${limit}`);
}
