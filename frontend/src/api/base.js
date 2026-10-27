/**
 * API 基础配置
 * 后端地址通过环境变量 VITE_API_BASE 配置
 * 开发时默认 http://localhost:8080
 */

const BASE_URL = import.meta.env.VITE_API_BASE || "";

class ApiError extends Error {
  constructor(status, message, details = {}) {
    super(message);
    this.status = status;
    this.code = details.code || "request_failed";
    this.requestId = details.request_id || "";
    this.retryable = Boolean(details.retryable);
  }
}

function createRequestId() {
  if (typeof crypto !== "undefined" && crypto.randomUUID) {
    return `web_${crypto.randomUUID()}`;
  }
  return `web_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * 统一处理 401 未授权：清除 token，跳转登录页
 * 注意：当前若在 admin 路由下（独立账号体系），不跳普通 /login，
 * 避免普通用户 token 过期把 admin 页面冲掉。
 */
function handleUnauthorized() {
  localStorage.removeItem("wesmartflow-token");
  localStorage.removeItem("wesmartflow-user");
  if (
    typeof window !== "undefined" &&
    window.location.hash.startsWith("#/admin")
  ) {
    return;
  }
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
  if (!headers["X-Request-ID"]) {
    headers["X-Request-ID"] = createRequestId();
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
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new ApiError(
      res.status,
      err.detail || err.message || res.statusText,
      {
        ...err,
        request_id: err.request_id || res.headers.get("X-Request-ID") || "",
      },
    );
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
  if (!headers.has("X-Request-ID")) {
    headers.set("X-Request-ID", createRequestId());
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

/**
 * 拼接主资源 URL：/api/documents/{docId}/raw。
 * iframe / web-view 等无法注入 header 的场景，传入单文档短时效票据 ``ticket``
 * （由 POST /api/documents/{docId}/ticket 签发）。登录 token 禁止放进 URL。
 */
function docRawUrl(docId, { ticket = "", revision = "" } = {}) {
  const url = `${BASE_URL}/api/documents/${docId}/raw`;
  const params = new URLSearchParams();
  if (revision) params.set("v", String(revision));
  if (ticket) params.set("ticket", ticket);
  const query = params.toString();
  return query ? `${url}?${query}` : url;
}

/**
 * 拼接伴生资源 URL：/api/documents/{docId}/asset/{subPath}。
 */
function docAssetUrl(docId, subPath, { ticket = "" } = {}) {
  const cleaned = String(subPath || "").replace(/^\/+/, "");
  const url = `${BASE_URL}/api/documents/${docId}/asset/${cleaned}`;
  return ticket ? `${url}?ticket=${encodeURIComponent(ticket)}` : url;
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

export {
  BASE_URL,
  ApiError,
  authHeaders,
  fetchAsBlobUrl,
  docRawUrl,
  docAssetUrl,
  createRequestId,
};
