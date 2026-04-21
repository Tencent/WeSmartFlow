/**
 * API 基础配置
 * 后端地址通过环境变量 VITE_API_BASE 配置
 * 开发时默认 http://localhost:8000
 */

const BASE_URL = import.meta.env.VITE_API_BASE || "";

class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

async function request(method, path, body = null, options = {}) {
  const url = `${BASE_URL}${path}`;
  const headers = { "Content-Type": "application/json", ...options.headers };

  const res = await fetch(url, {
    method,
    headers,
    body: body ? JSON.stringify(body) : null,
    ...options,
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }));
    throw new ApiError(res.status, err.message || res.statusText);
  }

  if (res.status === 204) return null;
  return res.json();
}

export const api = {
  get: (path, opts) => request("GET", path, null, opts),
  post: (path, body, opts) => request("POST", path, body, opts),
  patch: (path, body, opts) => request("PATCH", path, body, opts),
  delete: (path, opts) => request("DELETE", path, null, opts),
};

export { BASE_URL, ApiError };
