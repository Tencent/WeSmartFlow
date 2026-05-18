/**
 * 设置 API
 * GET  /api/settings            获取当前设置
 * POST /api/settings            保存设置
 * POST /api/settings/test       测试 LLM 连接
 * POST /api/settings/test-tavily  测试 Tavily 连接
 * POST /api/settings/test-image   测试图像生成连接
 */
import { api } from "./base.js";

export const settingsApi = {
  // 获取当前设置
  get: () => api.get("/api/settings"),

  // 保存设置
  save: (data) => api.post("/api/settings", data),

  // 查询用户剩余免费次数
  getQuota: () => api.get("/api/settings/quota"),

  // 测试 LLM 连接
  testLLM: () => api.post("/api/settings/test"),

  // 测试 Tavily 连接
  testTavily: () => api.post("/api/settings/test-tavily"),

  // 测试图像生成连接
  testImage: () => api.post("/api/settings/test-image"),
};
