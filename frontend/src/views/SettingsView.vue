<template>
  <div class="settings-page page-std">
    <div class="page-header">
      <div>
        <h1 class="page-title">设置</h1>
        <p class="page-subtitle">配置 AI 模型和 API 参数</p>
      </div>
      <button class="btn btn-primary" :disabled="saving" @click="saveAll">
        <svg
          v-if="!saveSuccess"
          width="13"
          height="13"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path
            d="M19 21H5a2 2 0 01-2-2V5a2 2 0 012-2h11l5 5v11a2 2 0 01-2 2z"
          />
          <polyline points="17 21 17 13 7 13 7 21" />
          <polyline points="7 3 7 8 15 8" />
        </svg>
        {{ saveSuccess ? "✓ 已保存" : saving ? "保存中..." : "保存设置" }}
      </button>
    </div>

    <!-- 用量概览 -->
    <div v-if="quotaLoaded" class="quota-overview card">
      <div class="quota-header">
        <svg
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
        >
          <path d="M12 20V10" />
          <path d="M18 20V4" />
          <path d="M6 20v-4" />
        </svg>
        <span class="quota-title">免费额度用量</span>
        <span class="quota-hint">配置自己的 API Key 后不受额度限制</span>
      </div>
      <div class="quota-bars">
        <div v-for="item in quotaItems" :key="item.key" class="quota-item">
          <div class="qi-label">
            <span class="qi-icon" v-html="item.icon" />
            <span class="qi-name">{{ item.name }}</span>
            <span v-if="!item.isPlatform" class="qi-badge unlimited"
              >自有 Key · 无限</span
            >
            <span v-else class="qi-count"
              >{{ item.used }} / {{ item.limit }}</span
            >
          </div>
          <div v-if="item.isPlatform" class="qi-bar-track">
            <div
              class="qi-bar-fill"
              :class="item.barClass"
              :style="{ width: item.percent + '%' }"
            />
          </div>
          <div v-else class="qi-bar-track">
            <div class="qi-bar-fill unlimited-bar" style="width: 100%" />
          </div>
        </div>
      </div>
    </div>

    <div class="settings-layout">
      <!-- Sidebar tabs -->
      <div class="settings-tabs">
        <button
          v-for="tab in tabs"
          :key="tab.key"
          class="st-btn"
          :class="{ active: activeTab === tab.key }"
          @click="activeTab = tab.key"
        >
          <span v-html="tab.icon" />
          {{ tab.label }}
        </button>
      </div>

      <!-- Content -->
      <div class="settings-content">
        <!-- AI 模型 -->
        <div v-if="activeTab === 'model'">
          <div class="settings-section card">
            <div class="ss-title">AI 模型配置</div>
            <p class="ss-desc">
              使用 OpenAI 兼容格式的 LLM 接口，需支持
              <strong>Function Calling</strong>（工具调用）能力。
            </p>

            <div class="config-block">
              <div class="cb-title">API 配置</div>
              <div class="form-item">
                <label>API Key</label>
                <div class="input-with-btn">
                  <input
                    v-model="form.llm_api_key"
                    class="form-input"
                    :type="showKey ? 'text' : 'password'"
                    placeholder="sk-..."
                  />
                  <button
                    class="btn btn-ghost btn-sm"
                    @click="showKey = !showKey"
                  >
                    {{ showKey ? "隐藏" : "显示" }}
                  </button>
                </div>
                <div v-if="maskedKeys.llm_api_key" class="field-hint">
                  当前已保存：{{ maskedKeys.llm_api_key }}
                </div>
              </div>
              <div class="form-item">
                <label>Base URL</label>
                <input
                  v-model="form.llm_base_url"
                  class="form-input"
                  placeholder="https://api.openai.com/v1"
                />
              </div>
              <div class="form-item">
                <label
                  >模型名称
                  <span class="optional"
                    >（需支持 Function Calling）</span
                  ></label
                >
                <input
                  v-model="form.llm_model"
                  class="form-input"
                  placeholder="gpt-4o / deepseek-chat / qwen-plus ..."
                />
              </div>
              <div class="form-item-row">
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="testing"
                  @click="testLLM"
                >
                  {{ testing ? "测试中..." : "测试连接" }}
                </button>
                <div
                  v-if="testStatus !== 'idle'"
                  class="status-hint"
                  :class="testStatus"
                >
                  <span v-if="testStatus === 'success'">✓ {{ testReply }}</span>
                  <span v-else>✗ {{ testError }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Tavily 搜索 -->
        <div v-if="activeTab === 'tavily'">
          <div class="settings-section card">
            <div class="ss-title">Tavily 搜索配置</div>
            <p class="ss-desc">
              Tavily 是专为 AI 设计的搜索 API，用于联网搜索增强回答。访问
              <a
                href="https://tavily.com"
                target="_blank"
                style="color: var(--brand-light)"
                >tavily.com</a
              >获取 <strong>免费</strong> API Key。
            </p>
            <div class="config-block">
              <div class="cb-title">API 配置</div>
              <div class="form-item">
                <label>Tavily API Key</label>
                <div class="input-with-btn">
                  <input
                    v-model="form.tavily_api_key"
                    class="form-input"
                    :type="showTavilyKey ? 'text' : 'password'"
                    placeholder="tvly-..."
                  />
                  <button
                    class="btn btn-ghost btn-sm"
                    @click="showTavilyKey = !showTavilyKey"
                  >
                    {{ showTavilyKey ? "隐藏" : "显示" }}
                  </button>
                </div>
                <div v-if="maskedKeys.tavily_api_key" class="field-hint">
                  当前已保存：{{ maskedKeys.tavily_api_key }}
                </div>
              </div>
              <div class="form-item-row">
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="testingTavily"
                  @click="testTavily"
                >
                  {{ testingTavily ? "测试中..." : "测试连接" }}
                </button>
                <div
                  v-if="tavilyStatus !== 'idle'"
                  class="status-hint"
                  :class="tavilyStatus"
                >
                  <span v-if="tavilyStatus === 'success'"
                    >✓ {{ tavilyReply }}</span
                  >
                  <span v-else>✗ {{ tavilyError }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 图像生成 -->
        <div v-if="activeTab === 'image'">
          <div class="settings-section card">
            <div class="ss-title">图像生成 API 配置</div>
            <p class="ss-desc">
              配置兼容 OpenAI Images
              API（<code>/v1/images/generations</code>）的图像生成服务。
            </p>
            <div class="config-block">
              <div class="cb-title">API 配置</div>
              <div class="form-item">
                <label>API Key</label>
                <div class="input-with-btn">
                  <input
                    v-model="form.img_api_key"
                    class="form-input"
                    :type="showImgKey ? 'text' : 'password'"
                    placeholder="any"
                  />
                  <button
                    class="btn btn-ghost btn-sm"
                    @click="showImgKey = !showImgKey"
                  >
                    {{ showImgKey ? "隐藏" : "显示" }}
                  </button>
                </div>
                <div v-if="maskedKeys.img_api_key" class="field-hint">
                  当前已保存：{{ maskedKeys.img_api_key }}
                </div>
              </div>
              <div class="form-item">
                <label>Base URL</label>
                <input
                  v-model="form.img_base_url"
                  class="form-input"
                  placeholder="http://localhost:8080/v1"
                />
              </div>
              <div class="form-item">
                <label>模型名称</label>
                <input
                  v-model="form.img_model"
                  class="form-input"
                  placeholder="gpt-image-1 / dall-e-3 / qwen-image-2.0 ..."
                />
              </div>
              <div class="form-item-row">
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="testingImage"
                  @click="testImageGen"
                >
                  {{ testingImage ? "测试中..." : "测试连接" }}
                </button>
                <div
                  v-if="imageStatus !== 'idle'"
                  class="status-hint"
                  :class="imageStatus"
                >
                  <span v-if="imageStatus === 'success'"
                    >✓ {{ imageReply }}</span
                  >
                  <span v-else>✗ {{ imageError }}</span>
                </div>
                <div v-if="testImageUrl" class="test-image-preview">
                  <img :src="testImageUrl" alt="测试生成图片" />
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 关于 -->
        <div v-if="activeTab === 'about'">
          <div class="settings-section card about-card">
            <div class="about-logo">
              <div class="logo-mark-lg">
                <img src="/logo.png" alt="Logo" class="logo-img-lg" />
              </div>
              <div>
                <div class="about-name">WeSmartFlow</div>
                <div class="about-tagline">你的本地个人知识大脑</div>
              </div>
            </div>
            <div class="about-desc">
              WeSmartFlow 是一个开源的本地 AI 教育助手。你学过的所有东西，都被
              AI
              组织成一张属于你自己的知识图谱，完全离线，完全私有，越用越懂你。
            </div>
            <div class="about-meta">
              <div class="am-item">
                <span class="am-label">版本</span><span>v0.1.0-alpha</span>
              </div>
              <div class="am-item">
                <span class="am-label">许可证</span><span>MIT</span>
              </div>
              <div class="am-item">
                <span class="am-label">技术栈</span
                ><span>Vue 3 + Vite + Python</span>
              </div>
            </div>
            <div class="about-links">
              <a
                class="btn btn-ghost btn-sm"
                href="https://github.com/Tencent/WeSmartFlow"
                target="_blank"
              >
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="currentColor"
                >
                  <path
                    d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"
                  />
                </svg>
                GitHub
              </a>
              <a class="btn btn-ghost btn-sm" href="#" target="_blank"
                >📖 文档</a
              >
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from "vue";
import { settingsApi } from "@/api";

const activeTab = ref("model");
const showKey = ref(false);
const saving = ref(false);
const saveSuccess = ref(false);
const testing = ref(false);
const testStatus = ref("idle"); // 'idle' | 'success' | 'error'
const testReply = ref("");
const testError = ref("");

// Tavily 测试状态
const showTavilyKey = ref(false);
const testingTavily = ref(false);
const tavilyStatus = ref("idle"); // 'idle' | 'success' | 'error'
const tavilyReply = ref("");
const tavilyError = ref("");

// 图像生成测试状态
const showImgKey = ref(false);
const testingImage = ref(false);
const imageStatus = ref("idle"); // 'idle' | 'success' | 'error'
const imageReply = ref("");
const imageError = ref("");
const testImageUrl = ref(""); // 测试生成的图片 base64 data URL

// 用量数据
const quotaLoaded = ref(false);
const quotaItems = ref([]);

// 表单数据（用户输入，空字符串表示不修改）
const form = reactive({
  llm_api_key: "",
  llm_base_url: "",
  llm_model: "",
  tavily_api_key: "",
  img_api_key: "",
  img_base_url: "",
  img_model: "",
});

// 已保存的脱敏值（用于提示用户当前已配置）
const maskedKeys = reactive({
  llm_api_key: "",
  tavily_api_key: "",
  img_api_key: "",
});

const tabs = [
  {
    key: "model",
    label: "AI 模型",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
  },
  {
    key: "tavily",
    label: "Tavily 搜索",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
  },
  {
    key: "image",
    label: "图像生成",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
  },
  {
    key: "about",
    label: "关于",
    icon: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
  },
];

// 加载用量数据
async function loadQuota() {
  try {
    const data = await settingsApi.getQuota();
    const icons = {
      llm: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2"/><line x1="8" y1="21" x2="16" y2="21"/><line x1="12" y1="17" x2="12" y2="21"/></svg>`,
      search: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
      image: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="8.5" cy="8.5" r="1.5"/><polyline points="21 15 16 10 5 21"/></svg>`,
    };
    const names = { llm: "AI 对话", search: "搜索", image: "图像生成" };
    quotaItems.value = ["llm", "search", "image"].map((key) => {
      const info = data[key] || {
        used: 0,
        limit: 0,
        remaining: 0,
        is_platform: true,
      };
      const percent =
        info.limit > 0 ? Math.min((info.used / info.limit) * 100, 100) : 0;
      let barClass = "bar-ok";
      if (percent >= 90) barClass = "bar-danger";
      else if (percent >= 70) barClass = "bar-warn";
      return {
        key,
        name: names[key],
        icon: icons[key],
        used: info.used,
        limit: info.limit,
        remaining: info.remaining,
        isPlatform: info.is_platform,
        percent,
        barClass,
      };
    });
    quotaLoaded.value = true;
  } catch (e) {
    console.error("加载用量数据失败", e);
  }
}

// 加载当前配置
async function loadSettings() {
  try {
    const data = await settingsApi.get();
    // 非敏感字段直接填入表单
    form.llm_base_url = data.llm_base_url || "";
    form.llm_model = data.llm_model || "";
    form.img_base_url = data.img_base_url || "";
    form.img_model = data.img_model || "";
    // 敏感字段只存脱敏值用于提示
    maskedKeys.llm_api_key = data.llm_api_key || "";
    maskedKeys.tavily_api_key = data.tavily_api_key || "";
    maskedKeys.img_api_key = data.img_api_key || "";
  } catch (e) {
    console.error("加载设置失败", e);
  }
}

// 保存设置
async function saveAll() {
  saving.value = true;
  try {
    // 只发送非空字段（空字符串表示用户没有输入新值，不覆盖）
    const payload = {};
    for (const [k, v] of Object.entries(form)) {
      if (v !== "") payload[k] = v;
    }
    const data = await settingsApi.save(payload);
    if (data.ok) {
      // 保存成功后重新加载（刷新脱敏提示，清空密码输入框）
      form.llm_api_key = "";
      form.tavily_api_key = "";
      form.img_api_key = "";
      await loadSettings();
      // 显示保存成功状态，1.5s 后恢复
      saveSuccess.value = true;
      setTimeout(() => {
        saveSuccess.value = false;
      }, 1500);
    }
  } catch (e) {
    console.error("保存失败", e);
  } finally {
    saving.value = false;
  }
}

// 测试 LLM 连接
async function testLLM() {
  testing.value = true;
  testStatus.value = "idle";
  try {
    const data = await settingsApi.testLLM();
    if (data.ok) {
      testStatus.value = "success";
      testReply.value = data.reply || "连接成功";
    } else {
      testStatus.value = "error";
      testError.value = data.error || "连接失败";
    }
  } catch (e) {
    testStatus.value = "error";
    testError.value = String(e);
  } finally {
    testing.value = false;
    loadQuota();
  }
}

// 测试 Tavily 连接
async function testTavily() {
  testingTavily.value = true;
  tavilyStatus.value = "idle";
  try {
    const data = await settingsApi.testTavily();
    if (data.ok) {
      tavilyStatus.value = "success";
      tavilyReply.value = data.reply || "连接成功";
    } else {
      tavilyStatus.value = "error";
      tavilyError.value = data.error || "连接失败";
    }
  } catch (e) {
    tavilyStatus.value = "error";
    tavilyError.value = String(e);
  } finally {
    testingTavily.value = false;
    loadQuota();
  }
}

// 测试图像生成连接
async function testImageGen() {
  testingImage.value = true;
  imageStatus.value = "idle";
  testImageUrl.value = "";
  try {
    const data = await settingsApi.testImage();
    if (data.ok) {
      imageStatus.value = "success";
      imageReply.value = data.reply || "连接成功";
      if (data.image) {
        testImageUrl.value = data.image;
      }
    } else {
      imageStatus.value = "error";
      imageError.value = data.error || "连接失败";
    }
  } catch (e) {
    imageStatus.value = "error";
    imageError.value = String(e);
  } finally {
    testingImage.value = false;
    loadQuota();
  }
}

onMounted(() => {
  loadSettings();
  loadQuota();
});
</script>

<style scoped>
.settings-page {
}

.settings-layout {
  display: grid;
  grid-template-columns: 180px 1fr;
  gap: 16px;
}

/* Tabs */
.settings-tabs {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.st-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
  text-align: left;
}
.st-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.st-btn.active {
  background: var(--brand-dim);
  color: var(--brand-light);
}

/* Section */
.settings-section {
  padding: 24px;
  margin-bottom: 14px;
}
.ss-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}
.ss-desc {
  font-size: 12px;
  color: var(--text-muted);
  line-height: 1.6;
  margin-bottom: 18px;
}

/* Model selector */
.model-selector {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}
.model-option {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 16px;
  border-radius: var(--radius-md);
  background: var(--bg-hover);
  border: 1.5px solid var(--border);
  cursor: pointer;
  transition: var(--transition);
}
.model-option:hover {
  border-color: var(--border-hover);
}
.model-option.active {
  border-color: var(--border-active);
  background: var(--brand-dim);
}
.mo-icon {
  font-size: 22px;
  flex-shrink: 0;
}
.mo-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.mo-desc {
  font-size: 11px;
  color: var(--text-muted);
}
.mo-badge {
  margin-left: auto;
}

/* Config block */
.config-block {
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 16px;
}
.cb-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--text-secondary);
  margin-bottom: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

/* Form */
.form-item {
  margin-bottom: 12px;
}
.form-item label {
  display: block;
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 5px;
}
.form-input {
  width: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  color: var(--text-primary);
  font-size: 13px;
  outline: none;
  transition: var(--transition);
}
.form-input:focus {
  border-color: var(--border-active);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}
.form-select {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  color: var(--text-secondary);
  font-size: 13px;
  outline: none;
  cursor: pointer;
}
.input-with-btn {
  display: flex;
  gap: 8px;
}
.input-with-btn .form-input {
  flex: 1;
}

/* 字段辅助提示 */
.field-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 4px;
}
.optional {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 400;
}
.form-item-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 4px;
}
.form-item-row .status-hint {
  margin-top: 0;
}

.status-hint {
  font-size: 12px;
  margin-top: 8px;
  padding: 5px 8px;
  border-radius: var(--radius-sm);
}
.status-hint.success {
  color: var(--green);
  background: var(--green-dim);
}
.status-hint.error {
  color: var(--red);
  background: var(--red-dim);
}
.status-hint.idle {
  color: var(--text-dim);
}

/* 测试图片预览 */
.test-image-preview {
  margin-top: 12px;
}
.test-image-preview img {
  max-width: 256px;
  max-height: 256px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

/* 用量概览 */
.quota-overview {
  padding: 18px 22px;
  margin-bottom: 16px;
}
.quota-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 14px;
  color: var(--text-secondary);
}
.quota-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
}
.quota-hint {
  font-size: 11px;
  color: var(--text-dim);
  margin-left: auto;
}
.quota-bars {
  display: flex;
  gap: 16px;
}
.quota-item {
  flex: 1;
  min-width: 0;
}
.qi-label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 12px;
}
.qi-icon {
  display: flex;
  align-items: center;
  color: var(--text-muted);
}
.qi-name {
  font-weight: 600;
  color: var(--text-secondary);
}
.qi-count {
  margin-left: auto;
  font-size: 11px;
  color: var(--text-muted);
  font-family: "Fira Code", monospace;
}
.qi-badge {
  margin-left: auto;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 600;
}
.qi-badge.unlimited {
  background: var(--green-dim);
  color: var(--green);
}
.qi-bar-track {
  height: 6px;
  background: var(--bg-hover);
  border-radius: 3px;
  overflow: hidden;
}
.qi-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}
.qi-bar-fill.bar-ok {
  background: linear-gradient(90deg, #6366f1, #818cf8);
}
.qi-bar-fill.bar-warn {
  background: linear-gradient(90deg, #f59e0b, #fbbf24);
}
.qi-bar-fill.bar-danger {
  background: linear-gradient(90deg, #ef4444, #f87171);
}
.qi-bar-fill.unlimited-bar {
  background: linear-gradient(90deg, #10b981, #34d399);
  opacity: 0.5;
}

/* Data stats */
.data-stats {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 18px;
}
.ds-item {
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 12px;
  display: flex;
  align-items: center;
  gap: 10px;
}
.ds-icon {
  display: flex;
  align-items: center;
}
.ds-val {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.ds-label {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 1px;
}

.data-path {
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 12px 14px;
}
.dp-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.dp-path {
  display: flex;
  align-items: center;
  gap: 10px;
}
.dp-path code {
  flex: 1;
  font-size: 13px;
  color: var(--brand-light);
  font-family: "Fira Code", monospace;
}

/* Action list */
.action-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.action-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
}
.ai-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.ai-desc {
  font-size: 11px;
  color: var(--text-muted);
}
.btn-danger {
  background: var(--red-dim);
  color: var(--red);
  border: 1px solid rgba(239, 68, 68, 0.2);
}
.btn-danger:hover {
  background: var(--red);
  color: white;
}

/* Prefs */
.pref-list {
  display: flex;
  flex-direction: column;
}
.pref-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
}
.pref-item:last-child {
  border-bottom: none;
}
.pi-label {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.pi-desc {
  font-size: 11px;
  color: var(--text-muted);
}

/* Toggle */
.toggle {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  flex-shrink: 0;
}
.toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}
.toggle-slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--bg-active);
  border: 1px solid var(--border-hover);
  border-radius: 20px;
  transition: var(--transition);
}
.toggle-slider::before {
  content: "";
  position: absolute;
  height: 14px;
  width: 14px;
  left: 2px;
  bottom: 2px;
  background: var(--text-dim);
  border-radius: 50%;
  transition: var(--transition);
}
.toggle input:checked + .toggle-slider {
  background: var(--brand);
  border-color: var(--brand);
}
.toggle input:checked + .toggle-slider::before {
  transform: translateX(16px);
  background: white;
}

/* About */
.about-card {
  display: flex;
  flex-direction: column;
  gap: 18px;
}
.about-logo {
  display: flex;
  align-items: center;
  gap: 14px;
}
.logo-mark-lg {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
}
.logo-img-lg {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: 12px;
}
.about-name {
  font-size: 20px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.4px;
}
.about-tagline {
  font-size: 12px;
  color: var(--text-muted);
  margin-top: 2px;
}
.about-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
}
.about-meta {
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.am-item {
  display: flex;
  gap: 12px;
  font-size: 13px;
}
.am-label {
  color: var(--text-muted);
  min-width: 60px;
}
.about-links {
  display: flex;
  gap: 8px;
}
</style>
