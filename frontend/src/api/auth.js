/**
 * 认证 API — 邮箱验证码登录 + GitHub OAuth 登录
 */

import { BASE_URL } from "./base.js";

export const authApi = {
  // ── 邮箱验证码登录 ──

  /**
   * 发送邮箱验证码
   * @param {string} email - 邮箱地址
   * @returns {Promise<{message: string, cooldown: number}>}
   */
  async sendCode(email) {
    const res = await fetch(`${BASE_URL}/api/auth/send-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "发送验证码失败");
    }

    return res.json();
  },

  /**
   * 邮箱验证码登录/注册
   * @param {string} email - 邮箱地址
   * @param {string} code - 验证码
   * @param {string} name - 用户昵称（可选，新用户注册时使用）
   * @returns {Promise<{access_token: string, token_type: string, user_id: string, user_name: string}>}
   */
  async verifyCode(email, code, name = "") {
    const res = await fetch(`${BASE_URL}/api/auth/verify-code`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, code, name }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "验证失败");
    }

    return res.json();
  },

  // ── GitHub OAuth 登录 ──

  /**
   * 获取 GitHub 授权 URL
   * @returns {Promise<{authorize_url: string}>}
   */
  async getGitHubAuthorizeUrl() {
    const res = await fetch(`${BASE_URL}/api/auth/github/authorize`);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "获取 GitHub 授权地址失败");
    }

    return res.json();
  },

  /**
   * GitHub OAuth 回调登录
   * @param {string} code - GitHub 回调的 code
   * @returns {Promise<{access_token: string, token_type: string, user_id: string, user_name: string}>}
   */
  async githubCallback(code) {
    const res = await fetch(`${BASE_URL}/api/auth/github/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || "GitHub 登录失败");
    }

    return res.json();
  },
};
