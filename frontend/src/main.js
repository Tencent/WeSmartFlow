import { createApp } from "vue";
import { createRouter, createWebHashHistory } from "vue-router";
import App from "./App.vue";
import "./style.css";

import Dashboard from "./views/DashboardView.vue";
import Graph from "./views/GraphView.vue";
import Chat from "./views/ChatView.vue";
import Quiz from "./views/QuizView.vue";
import DailyBrief from "./views/DailyBrief.vue";
import Documents from "./views/DocumentsView.vue";
import Sessions from "./views/SessionsView.vue";
import Profile from "./views/ProfileView.vue";
import Settings from "./views/SettingsView.vue";

const routes = [
  { path: "/", redirect: "/dashboard" },
  { path: "/dashboard", component: Dashboard },
  { path: "/graph", component: Graph },
  // /knowledge 重定向到 /graph（列表视图），保持旧链接可用
  { path: "/knowledge", redirect: "/graph" },
  { path: "/chat", component: Chat },
  { path: "/quiz", component: Quiz },
  { path: "/sessions", component: Sessions },
  { path: "/brief", component: DailyBrief },
  { path: "/documents", component: Documents },
  { path: "/profile", component: Profile },
  { path: "/settings", component: Settings },
  // /immersive 兼容旧链接，重定向到统一的 AI 辅导页
  {
    path: "/immersive",
    redirect: (to) => ({
      path: "/chat",
      query: { topic: to.query.topic, mode: "immersive" },
    }),
  },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

createApp(App).use(router).mount("#app");
