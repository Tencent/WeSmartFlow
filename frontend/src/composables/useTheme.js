import { ref, watch } from "vue";

const isDark = ref(true);

// 初始化时读取本地存储
const saved = localStorage.getItem("wesmartflow-theme");
if (saved === "light") isDark.value = false;

// 切换并同步到 DOM + localStorage
function toggleTheme() {
  isDark.value = !isDark.value;
}

watch(
  isDark,
  (dark) => {
    document.documentElement.setAttribute(
      "data-theme",
      dark ? "dark" : "light",
    );
    localStorage.setItem("wesmartflow-theme", dark ? "dark" : "light");
  },
  { immediate: true },
);

export function useTheme() {
  return { isDark, toggleTheme };
}
