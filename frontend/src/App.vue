<template>
  <div class="app-layout" :class="{ 'sidebar-collapsed': sidebarCollapsed }">
    <aside class="sidebar">
      <!-- Logo -->
      <div class="sidebar-logo">
        <div class="logo-mark">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <defs>
              <linearGradient id="lg1" x1="2" y1="2" x2="22" y2="22">
                <stop stop-color="#6366f1" />
                <stop offset="1" stop-color="#a855f7" />
              </linearGradient>
            </defs>
            <path d="M12 2L2 7l10 5 10-5-10-5z" fill="url(#lg1)" />
            <path
              d="M2 17l10 5 10-5"
              stroke="url(#lg1)"
              stroke-width="1.8"
              stroke-linecap="round"
              fill="none"
            />
            <path
              d="M2 12l10 5 10-5"
              stroke="url(#lg1)"
              stroke-width="1.8"
              stroke-linecap="round"
              fill="none"
              opacity="0.6"
            />
          </svg>
        </div>
        <div class="logo-text">
          <div class="logo-name">AscendFlow</div>
          <div class="logo-tagline">本地知识大脑</div>
        </div>
        <button
          class="collapse-btn"
          :title="sidebarCollapsed ? '展开菜单' : '收起菜单'"
          @click="sidebarCollapsed = !sidebarCollapsed"
        >
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2.2"
          >
            <polyline v-if="!sidebarCollapsed" points="15 18 9 12 15 6" />
            <polyline v-else points="9 18 15 12 9 6" />
          </svg>
        </button>
      </div>

      <!-- Nav -->
      <nav class="sidebar-nav">
        <!-- 核心 -->
        <div class="nav-group">
          <div class="nav-group-label">核心</div>
          <router-link
            v-for="item in coreNav"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :title="sidebarCollapsed ? item.label : ''"
          >
            <span class="nav-icon" v-html="item.icon" />
            <span class="nav-label">{{ item.label }}</span>
            <span
              v-if="item.badge"
              class="nav-badge"
              :class="item.badgeType || 'brand'"
              >{{ item.badge }}</span
            >
          </router-link>
        </div>

        <!-- 学习 -->
        <div class="nav-group">
          <div class="nav-group-label">学习</div>
          <router-link
            v-for="item in learnNav"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :title="sidebarCollapsed ? item.label : ''"
          >
            <span class="nav-icon" v-html="item.icon" />
            <span class="nav-label">{{ item.label }}</span>
            <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
          </router-link>
        </div>

        <!-- 素材 -->
        <div class="nav-group">
          <div class="nav-group-label">素材</div>
          <router-link
            v-for="item in materialNav"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :title="sidebarCollapsed ? item.label : ''"
          >
            <span class="nav-icon" v-html="item.icon" />
            <span class="nav-label">{{ item.label }}</span>
            <span v-if="item.badge" class="nav-badge">{{ item.badge }}</span>
          </router-link>
        </div>

        <!-- 个人 -->
        <div class="nav-group">
          <div class="nav-group-label">个人</div>
          <router-link
            v-for="item in personalNav"
            :key="item.path"
            :to="item.path"
            class="nav-item"
            :title="sidebarCollapsed ? item.label : ''"
          >
            <span class="nav-icon" v-html="item.icon" />
            <span class="nav-label">{{ item.label }}</span>
          </router-link>
        </div>
      </nav>

      <!-- 底部 -->
      <div class="sidebar-footer">
        <!-- 主题切换 -->
        <button
          class="theme-toggle"
          :title="sidebarCollapsed ? (isDark ? '深色' : '浅色') : ''"
          @click="toggleTheme"
        >
          <div class="tt-track" :class="{ light: !isDark }">
            <div class="tt-thumb">
              <svg
                v-if="!isDark"
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
              >
                <circle cx="12" cy="12" r="5" />
                <line x1="12" y1="1" x2="12" y2="3" />
                <line x1="12" y1="21" x2="12" y2="23" />
                <line x1="4.22" y1="4.22" x2="5.64" y2="5.64" />
                <line x1="18.36" y1="18.36" x2="19.78" y2="19.78" />
                <line x1="1" y1="12" x2="3" y2="12" />
                <line x1="21" y1="12" x2="23" y2="12" />
                <line x1="4.22" y1="19.78" x2="5.64" y2="18.36" />
                <line x1="18.36" y1="5.64" x2="19.78" y2="4.22" />
              </svg>
              <svg
                v-else
                width="10"
                height="10"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
              >
                <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
              </svg>
            </div>
          </div>
          <span class="tt-label">{{ isDark ? "深色" : "浅色" }}</span>
        </button>

        <!-- User -->
        <router-link
          to="/profile"
          class="sidebar-user"
          :title="sidebarCollapsed ? 'Rony Yuan' : ''"
        >
          <div
            class="avatar"
            style="width: 30px; height: 30px; font-size: 12px; font-weight: 700"
          >
            袁
          </div>
          <div class="user-info">
            <div class="user-name">Rony Yuan</div>
            <div class="user-sub">
              <span
                class="badge badge-brand"
                style="font-size: 10px; padding: 1px 6px"
                >Pro</span
              >
            </div>
          </div>
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            style="color: var(--text-dim); flex-shrink: 0"
          >
            <polyline points="9 18 15 12 9 6" />
          </svg>
        </router-link>
      </div>
    </aside>

    <!-- Main -->
    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useTheme } from "./composables/useTheme.js";
const { isDark, toggleTheme } = useTheme();
const sidebarCollapsed = ref(false);

// 核心：知识图谱相关
const coreNav = [
  {
    path: "/dashboard",
    label: "今日学习",
    icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M3 9l9-7 9 7v11a2 2 0 01-2 2H5a2 2 0 01-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>`,
  },
  {
    path: "/graph",
    label: "知识图谱",
    icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>`,
  },
];

// 学习：产生知识的行为
const learnNav = [
  {
    path: "/chat",
    label: "AI 辅导",
    icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg>`,
  },
  {
    path: "/quiz",
    label: "练习出题",
    icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/></svg>`,
  },
  {
    path: "/sessions",
    label: "学习历史",
    icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>`,
  },
  {
    path: "/brief",
    label: "每日简报",
    icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M4 22h16a2 2 0 002-2V4a2 2 0 00-2-2H8a2 2 0 00-2 2v16a2 2 0 01-2 2zm0 0a2 2 0 01-2-2v-9c0-1.1.9-2 2-2h2"/><path d="M18 14h-8"/><path d="M15 18h-5"/><path d="M10 6h8v4h-8z"/></svg>`,
  },
];

// 素材：知识的原料
const materialNav = [
  {
    path: "/documents",
    label: "文档管理",
    icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>`,
  },
];

// 个人
const personalNav = [
  {
    path: "/profile",
    label: "我的档案",
    icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`,
  },
  {
    path: "/settings",
    label: "设置",
    icon: `<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z"/></svg>`,
  },
];
</script>

<style scoped>
.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* Sidebar */
.sidebar {
  width: var(--sidebar-width);
  background: var(--bg-panel);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  transition: width 0.22s cubic-bezier(0.4, 0, 0.2, 1);
  overflow: hidden;
}

/* 收缩状态 */
.sidebar-collapsed .sidebar {
  width: 56px;
}
.sidebar-collapsed .logo-text,
.sidebar-collapsed .nav-label,
.sidebar-collapsed .nav-badge,
.sidebar-collapsed .nav-group-label,
.sidebar-collapsed .tt-label,
.sidebar-collapsed .user-info,
.sidebar-collapsed .sidebar-user > svg {
  display: none;
}
.sidebar-collapsed .sidebar-logo {
  padding: 14px 12px;
  justify-content: center;
}
.sidebar-collapsed .collapse-btn {
  margin-left: 0;
}
.sidebar-collapsed .nav-item {
  justify-content: center;
  padding: 8px;
}
.sidebar-collapsed .nav-icon {
  opacity: 0.8;
}
.sidebar-collapsed .theme-toggle {
  justify-content: center;
  padding: 6px;
}
.sidebar-collapsed .sidebar-user {
  justify-content: center;
  padding: 7px;
}
.sidebar-collapsed .tt-track {
  flex-shrink: 0;
}

/* Logo */
.sidebar-logo {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 16px 14px;
  border-bottom: 1px solid var(--border);
  position: relative;
}
.logo-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
}
.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 5px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-dim);
  flex-shrink: 0;
  margin-left: auto;
  transition: var(--transition);
}
.collapse-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.logo-mark {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: rgba(99, 102, 241, 0.1);
  border: 1px solid rgba(99, 102, 241, 0.18);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.logo-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.3px;
  line-height: 1.2;
}
.logo-tagline {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 1px;
  letter-spacing: 0.02em;
}

/* Nav */
.sidebar-nav {
  flex: 1;
  padding: 10px 8px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-group {
  margin-bottom: 4px;
}
.nav-group-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  letter-spacing: 0.07em;
  text-transform: uppercase;
  padding: 6px 10px 4px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 10px;
  border-radius: var(--radius-sm);
  color: var(--text-secondary);
  text-decoration: none;
  transition: var(--transition);
  margin-bottom: 1px;
  font-size: 13px;
  font-weight: 500;
}
.nav-item:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.nav-item.router-link-active {
  background: var(--brand-dim);
  color: var(--brand-light);
  border: 1px solid rgba(99, 102, 241, 0.14);
}

.nav-icon {
  display: flex;
  align-items: center;
  opacity: 0.65;
  flex-shrink: 0;
}
.nav-item:hover .nav-icon,
.nav-item.router-link-active .nav-icon {
  opacity: 1;
}
.nav-label {
  flex: 1;
}

.nav-badge {
  font-size: 9px;
  font-weight: 700;
  background: var(--gradient-brand);
  color: white;
  padding: 1px 5px;
  border-radius: var(--radius-full);
}

/* Footer */
.sidebar-footer {
  border-top: 1px solid var(--border);
  padding: 8px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* Theme toggle */
.theme-toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: var(--transition);
  color: var(--text-secondary);
  width: 100%;
}
.theme-toggle:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.tt-track {
  width: 32px;
  height: 18px;
  border-radius: var(--radius-full);
  background: var(--bg-active);
  border: 1px solid var(--border-hover);
  position: relative;
  flex-shrink: 0;
  transition: var(--transition);
}
.tt-track.light {
  background: var(--brand-dim);
  border-color: var(--border-active);
}
.tt-thumb {
  position: absolute;
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--text-muted);
  display: flex;
  align-items: center;
  justify-content: center;
  transition:
    transform 0.22s cubic-bezier(0.4, 0, 0.2, 1),
    background 0.18s;
  color: white;
}
.tt-track.light .tt-thumb {
  transform: translateX(14px);
  background: var(--brand);
}
.tt-label {
  font-size: 12px;
  font-weight: 500;
}

/* User */
.sidebar-user {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 7px 8px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition);
  text-decoration: none;
}
.sidebar-user:hover {
  background: var(--bg-hover);
}
.user-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}
.user-sub {
  margin-top: 1px;
}
.user-info {
  flex: 1;
  min-width: 0;
}

/* Main */
.main-content {
  flex: 1;
  overflow-y: auto;
  background: var(--bg-base);
}

/* Page transition */
.page-enter-active,
.page-leave-active {
  transition: all 0.18s ease;
}
.page-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.page-leave-to {
  opacity: 0;
}
</style>
