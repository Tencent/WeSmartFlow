/**
 * 知识节点 API
 * GET    /api/nodes          所有节点（图谱数据，含 relations）
 * GET    /api/nodes/due      今日到期复习节点
 * GET    /api/nodes/:id      节点详情（含 content / origins）
 * POST   /api/nodes          创建节点
 * PATCH  /api/nodes/:id      编辑节点
 * DELETE /api/nodes/:id      删除节点
 * POST   /api/nodes/:id/review  提交复习结果（SM-2）
 */
import { api } from "./base.js";

export const nodeApi = {
  // 获取所有节点（用于知识图谱、知识库）
  getAll: () => api.get("/api/nodes"),

  // 获取今日到期复习节点
  getDue: () => api.get("/api/nodes/due"),

  // 获取单个节点详情
  getById: (id) => api.get(`/api/nodes/${id}`),

  // 创建节点
  create: (data) => api.post("/api/nodes", data),

  // 手动更新节点信息（标题、描述、标签等）
  update: (id, data) => api.patch(`/api/nodes/${id}`, data),

  // 删除节点
  delete: (id) => api.delete(`/api/nodes/${id}`),

  // 提交复习结果，触发 SM-2 更新
  // quality: 0~5（5=完全记住，0=完全忘了）
  review: (id, quality) => api.post(`/api/nodes/${id}/review`, { quality }),
};
