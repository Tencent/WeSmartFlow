import { createApp } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import App from "./App.vue";
import "./style.css";

import Login from "./views/LoginView.vue";
import GitHubCallback from "./views/GitHubCallback.vue";
import Dashboard from "./views/DashboardView.vue";
import Graph from "./views/GraphView.vue";
import Chat from "./views/ChatView.vue";
import Immersive from "./views/ImmersiveView.vue";
import Quiz from "./views/QuizView.vue";
import DailyBrief from "./views/DailyBrief.vue";
import Documents from "./views/DocumentsView.vue";
import Sessions from "./views/SessionsView.vue";
import Profile from "./views/ProfileView.vue";
import Settings from "./views/SettingsView.vue";

const routes = [
  { path: "/login", component: Login, meta: { public: true } },
  {
    path: "/auth/github/callback",
    component: GitHubCallback,
    meta: { public: true },
  },
  { path: "/", redirect: "/chat" },
  { path: "/dashboard", component: Dashboard },
  { path: "/graph", component: Graph },
  // /knowledge 重定向到 /graph（列表视图），保持旧链接可用，保留 query 参数
  {
    path: "/knowledge",
    redirect: (to) => ({ path: "/graph", query: to.query }),
  },
  { path: "/chat", component: Chat },
  { path: "/immersive", component: Immersive },
  { path: "/quiz", component: Quiz },
  { path: "/sessions", component: Sessions },
  { path: "/brief", component: DailyBrief },
  { path: "/documents", component: Documents },
  { path: "/profile", component: Profile },
  { path: "/settings", component: Settings },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

// GitHub OAuth 回调处理：
// GitHub 回调 URL 格式为 http://localhost:5173/?code=xxx
// 由于使用 hash 模式，需要在应用启动时检测 URL query 中的 code 参数
// 并重定向到 hash 路由 /#/auth/github/callback?code=xxx
(function handleGitHubOAuthRedirect() {
  const urlParams = new URLSearchParams(window.location.search);
  const code = urlParams.get("code");
  if (code && !window.location.hash.includes("/auth/github/callback")) {
    // 清除 URL 中的 query 参数，跳转到 hash 路由
    window.location.replace(
      `${window.location.pathname}#/auth/github/callback?code=${encodeURIComponent(code)}`,
    );
  }
})();

// 路由守卫：未登录跳转到登录页
router.beforeEach((to) => {
  const token = localStorage.getItem("wesmartflow-token");
  if (!to.meta.public && !token) {
    return "/login";
  }
  // 已登录时访问登录页，跳转到首页
  if (to.path === "/login" && token) {
    return "/chat";
  }
});

createApp(App).use(router).mount("#app");
