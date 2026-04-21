/**
 * 用户 & Dashboard API
 * GET   /api/user
 * PATCH /api/user
 * GET   /api/user/dashboard
 */
import { api } from "./base.js";

export const userApi = {
  // 获取当前用户信息
  getMe: () => api.get("/api/user"),

  // 更新用户信息（name / preferences 等）
  updateMe: (data) => api.patch("/api/user", data),

  // Dashboard 统计数据（节点数、streak、热力图、最近会话）
  getDashboard: () => api.get("/api/user/dashboard"),
};
