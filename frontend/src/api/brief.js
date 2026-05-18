/**
 * 每日简报 API
 * GET  /api/brief/dates       获取有简报的日期列表
 * GET  /api/brief             获取今日简报
 * GET  /api/brief/:date       获取指定日期简报
 * POST /api/brief/regenerate  重新生成今日简报
 */
import { api } from "./base.js";

export const briefApi = {
  // 获取有简报的日期列表
  getDates: () => api.get("/api/brief/dates"),

  // 获取今日简报
  getToday: () => api.get("/api/brief"),

  // 获取指定日期简报
  getByDate: (date) => api.get(`/api/brief/${date}`),

  // 重新生成今日简报
  regenerate: () => api.post("/api/brief/regenerate"),
};
