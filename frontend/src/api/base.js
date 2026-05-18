/**
 * API 基础配置
 * 后端地址通过环境变量 VITE_API_BASE 配置
 * 开发时默认 http://localhost:8080
 */

const BASE_URL = import.meta.env.VITE_API_BASE || "";

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

/**
 * 统一处理 401 未授权：清除 token，跳转登录页
 */
function handleUnauthorized() {
  localStorage.removeItem("wesmartflow-token");
  localStorage.removeItem("wesmartflow-user");
  // 使用 location.href 确保整个页面刷新，触发路由守卫
  window.location.href = window.location.pathname + "#/login";
}

/**
 * 构建带鉴权的请求头
 */
function buildAuthHeaders(extra = {}) {
  const headers = { ...extra };
  const token = localStorage.getItem("wesmartflow-token");
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

/**
 * 通用 JSON 请求：自动序列化 body、解析 JSON 响应、处理 401
 */
async function request(method, path, body = null, options = {}) {
  const url = `${BASE_URL}${path}`;
  const headers = {
    "Content-Type": "application/json",
    ...buildAuthHeaders(options.headers),
  };

  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
    ...options,
  });

  if (!res.ok) {
    if (res.status === 401) {
      handleUnauthorized();
      return;
    }
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new ApiError(res.status, err.message || err.detail || res.statusText);
  }

  if (res.status === 204) return null;
  return res.json();
}

/**
 * 原始请求：返回 Response 对象（用于 SSE 流式读取、文件下载、text 响应等）。
 * 自动附加鉴权 header 和 401 处理。
 */
async function requestRaw(method, path, options = {}) {
  const url = `${BASE_URL}${path}`;
  const headers =
    options.headers instanceof Headers
      ? options.headers
      : new Headers(options.headers || {});
  const token = localStorage.getItem("wesmartflow-token");
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }
  const res = await fetch(url, { ...options, method, headers });
  if (res.status === 401) {
    handleUnauthorized();
    return res;
  }
  return res;
}

/**
 * 返回带鉴权信息的请求头对象（用于需要自行构造 fetch/XHR 的场景，如 pdfjs 的 httpHeaders）。
 */
function authHeaders() {
  const token = localStorage.getItem("wesmartflow-token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

/**
 * 以鉴权方式拉取二进制资源，转成 blob URL 返回。
 * 适用场景：原生 <audio>/<img> 等不支持自定义 header 的元素。
 * 调用方在资源不再使用时应调用 URL.revokeObjectURL(url) 释放内存。
 */
async function fetchAsBlobUrl(path) {
  const res = await requestRaw("GET", path);
  if (!res.ok) {
    throw new ApiError(res.status, `加载资源失败: ${res.status}`);
  }
  const blob = await res.blob();
  return URL.createObjectURL(blob);
}

export const api = {
  get: (path, opts) => request("GET", path, null, opts),
  post: (path, body, opts) => request("POST", path, body, opts),
  patch: (path, body, opts) => request("PATCH", path, body, opts),
  delete: (path, opts) => request("DELETE", path, null, opts),

  // 返回原始 Response 的方法（用于 SSE、文件下载、text 响应等）
  getRaw: (path, opts) => requestRaw("GET", path, opts),
  postRaw: (path, opts) => requestRaw("POST", path, opts),
};

export { BASE_URL, ApiError, authHeaders, fetchAsBlobUrl };
