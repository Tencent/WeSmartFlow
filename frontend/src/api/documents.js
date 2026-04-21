/**
 * 文档 API
 * GET    /api/documents           文档列表
 * GET    /api/documents/:id       文档详情 + 提取状态
 * POST   /api/documents/upload    上传文档（multipart/form-data，单文件）
 * POST   /api/documents/:id/extract  手动触发重新提取
 * GET    /api/documents/:id/content  获取文档内容（分段）
 * GET    /api/documents/:id/nodes    获取文档关联的节点
 * GET    /api/documents/nodes/:id/documents  获取节点关联的文档
 * GET    /api/documents/:id/summary  获取文档摘要信息
 * DELETE /api/documents/:id       删除文档
 */
import { api, BASE_URL } from "./base.js";

export const documentApi = {
  // 获取文档列表
  getAll: () => api.get("/api/documents"),

  // 获取单个文档详情（含提取状态 + 提取节点 id 列表）
  getById: (id) => api.get(`/api/documents/${id}`),

  // 获取文档摘要信息（节点统计、内容预览等）
  getSummary: (id) => api.get(`/api/documents/${id}/summary`),

  // 上传文档（单文件，后台自动触发提取）
  upload: (file) => {
    const formData = new FormData();
    formData.append("file", file); // 后端 FastAPI 接收字段名是 'file'
    return fetch(`${BASE_URL}/api/documents/upload`, {
      method: "POST",
      body: formData,
      // 不设置 Content-Type，让浏览器自动处理 multipart boundary
    }).then(async (r) => {
      if (!r.ok) {
        const err = await r.json().catch(() => ({}));
        throw new Error(err.detail || err.message || `上传失败 ${r.status}`);
      }
      return r.json();
    });
  },

  // 手动触发（重新）提取知识节点
  extract: (id) => api.post(`/api/documents/${id}/extract`),

  // 获取文档内容（分段）
  getContent: (id) => api.get(`/api/documents/${id}/content`),

  // 获取文档关联的节点
  getNodes: (id) => api.get(`/api/documents/${id}/nodes`),

  // 获取节点关联的文档
  getNodeDocuments: (nodeId) =>
    api.get(`/api/documents/nodes/${nodeId}/documents`),

  // 手动添加现有节点到文档
  addNode: (docId, nodeId) =>
    api.post(`/api/documents/${docId}/add_node`, { node_id: nodeId }),

  // 删除文档（同时解除与节点的关联，但不删除节点）
  delete: (id) => api.delete(`/api/documents/${id}`),
};
