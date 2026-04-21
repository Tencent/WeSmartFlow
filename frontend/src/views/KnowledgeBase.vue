<template>
  <div class="kb-page">
    <!-- Header -->
    <div class="kb-header">
      <div class="kb-header-left">
        <h1 class="page-title">知识库</h1>
        <p class="page-subtitle">你的个人知识节点库，与知识图谱实时同步</p>
      </div>
      <div class="kb-header-right">
        <div class="search-bar" :class="{ focused: searchFocused }">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            v-model="searchQuery"
            placeholder="搜索知识节点、文档..."
            @focus="searchFocused = true"
            @blur="searchFocused = false"
          />
        </div>
        <button class="btn btn-ghost" @click="$router.push('/graph')">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <circle cx="18" cy="5" r="3" />
            <circle cx="6" cy="12" r="3" />
            <circle cx="18" cy="19" r="3" />
            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
          </svg>
          图谱视图
        </button>
        <button class="btn btn-primary" @click="showUpload = true">
          <svg
            width="13"
            height="13"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <line x1="12" y1="5" x2="12" y2="19" />
            <line x1="5" y1="12" x2="19" y2="12" />
          </svg>
          添加文档
        </button>
      </div>
    </div>

    <!-- Stats bar -->
    <div class="kb-stats">
      <div v-for="s in kbStats" :key="s.label" class="ks-item">
        <div class="ks-val text-gradient">
          {{ s.val }}
        </div>
        <div class="ks-label">
          {{ s.label }}
        </div>
      </div>
      <div class="ks-divider" />
      <!-- 掌握度分布 -->
      <div class="ks-mastery-dist">
        <div class="kmd-label">掌握度分布</div>
        <div class="kmd-bars">
          <div
            v-for="d in masteryDist"
            :key="d.label"
            class="kmd-bar"
            :title="d.label"
          >
            <div
              class="kmd-fill"
              :style="{ height: d.pct + '%', background: d.color }"
            />
            <div class="kmd-count">
              {{ d.count }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Filter tabs -->
    <div class="kb-filters">
      <button
        v-for="f in filterTabs"
        :key="f.key"
        class="kb-filter-btn"
        :class="{ active: activeFilter === f.key }"
        @click="activeFilter = f.key"
      >
        <span v-if="f.color" class="kfb-dot" :style="{ background: f.color }" />
        {{ f.label }}
        <span class="kfb-count">{{ f.count }}</span>
      </button>
      <div class="kb-sort">
        <select v-model="sortBy">
          <option value="recent">最近学习</option>
          <option value="mastery-desc">掌握度↓</option>
          <option value="mastery-asc">掌握度↑</option>
          <option value="name">名称</option>
        </select>
      </div>
    </div>

    <!-- Main layout -->
    <div class="kb-layout">
      <!-- Left: node list -->
      <div class="kb-list">
        <div
          v-for="node in filteredNodes"
          :key="node.id"
          class="kn-card"
          :class="{ active: selectedNode?.id === node.id }"
          @click="selectedNode = node"
        >
          <div class="kn-top">
            <div
              class="kn-emoji-wrap"
              :style="{ background: getSubjectColor(node.subject) + '18' }"
            >
              <span class="kn-emoji">{{ node.emoji }}</span>
            </div>
            <div class="kn-main">
              <div class="kn-name">
                {{ node.label }}
              </div>
              <div class="kn-subject-line">
                <span
                  class="kn-dot"
                  :style="{ background: getSubjectColor(node.subject) }"
                />
                {{ node.subject }}
                <span class="kn-sep">·</span>
                <span class="kn-studied">{{ node.lastStudied }}</span>
              </div>
            </div>
            <div
              class="kn-mastery-badge"
              :style="{ color: getMasteryColor(node.mastery) }"
            >
              {{ node.mastery }}%
            </div>
          </div>
          <div class="kn-bottom">
            <div class="progress-bar">
              <div
                class="progress-fill"
                :style="{
                  width: node.mastery + '%',
                  background: getMasteryColor(node.mastery),
                }"
              />
            </div>
            <div class="kn-tags">
              <span
                v-for="tag in node.tags.slice(0, 3)"
                :key="tag"
                class="kn-tag"
                >{{ tag }}</span
              >
            </div>
          </div>
        </div>

        <!-- Empty -->
        <div v-if="filteredNodes.length === 0" class="kb-empty">
          <div class="ke-icon">🔍</div>
          <div class="ke-text">没有找到匹配的知识节点</div>
        </div>
      </div>

      <!-- Right: node detail -->
      <div v-if="selectedNode" class="kb-detail">
        <!-- Node header -->
        <div class="nd-header">
          <div
            class="nd-emoji-bg"
            :style="{
              background: getSubjectColor(selectedNode.subject) + '15',
            }"
          >
            <span class="nd-emoji">{{ selectedNode.emoji }}</span>
          </div>
          <div class="nd-title-wrap">
            <h2 class="nd-title">
              {{ selectedNode.label }}
            </h2>
            <div class="nd-badges">
              <span
                class="badge"
                :style="{
                  background: getSubjectColor(selectedNode.subject) + '20',
                  color: getSubjectColor(selectedNode.subject),
                  border: `1px solid ${getSubjectColor(selectedNode.subject)}30`,
                }"
              >
                {{ selectedNode.subject }}
              </span>
              <span v-if="selectedNode.mastery >= 80" class="badge badge-green"
                >已掌握</span
              >
              <span
                v-else-if="selectedNode.mastery >= 50"
                class="badge badge-yellow"
                >学习中</span
              >
              <span v-else class="badge badge-red">待突破</span>
            </div>
          </div>
          <div class="nd-actions-top">
            <button class="btn btn-primary btn-sm" @click="studyNode">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path
                  d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
                />
              </svg>
              继续学习
            </button>
          </div>
        </div>

        <!-- 三维掌握度 -->
        <div class="mastery-section">
          <div class="ms-overview">
            <div class="mso-circle">
              <svg width="80" height="80" viewBox="0 0 80 80">
                <circle
                  cx="40"
                  cy="40"
                  r="34"
                  fill="none"
                  stroke="var(--bg-hover)"
                  stroke-width="6"
                />
                <circle
                  cx="40"
                  cy="40"
                  r="34"
                  fill="none"
                  :stroke="getMasteryColor(selectedNode.mastery)"
                  stroke-width="6"
                  stroke-linecap="round"
                  :stroke-dasharray="`${(selectedNode.mastery / 100) * 213.6} 213.6`"
                  transform="rotate(-90 40 40)"
                  style="transition: stroke-dasharray 0.6s ease"
                />
                <text
                  x="40"
                  y="36"
                  text-anchor="middle"
                  font-size="16"
                  font-weight="700"
                  fill="var(--text-primary)"
                >
                  {{ selectedNode.mastery }}%
                </text>
                <text
                  x="40"
                  y="50"
                  text-anchor="middle"
                  font-size="9"
                  fill="var(--text-dim)"
                >
                  掌握度
                </text>
              </svg>
            </div>
            <div class="mso-dims">
              <div
                v-for="d in getNodeDims(selectedNode)"
                :key="d.label"
                class="msod-item"
              >
                <div class="msod-header">
                  <span class="msod-label">{{ d.label }}</span>
                  <span class="msod-val" :style="{ color: d.color }"
                    >{{ d.val }}%</span
                  >
                </div>
                <div class="progress-bar">
                  <div
                    class="progress-fill"
                    :style="{ width: d.val + '%', background: d.color }"
                  />
                </div>
                <div class="msod-desc">
                  {{ d.desc }}
                </div>
              </div>
            </div>
          </div>

          <!-- 衰减提醒 -->
          <div v-if="selectedNode.decayWarning" class="decay-hint">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"
              />
              <line x1="12" y1="9" x2="12" y2="13" />
              <line x1="12" y1="17" x2="12.01" y2="17" />
            </svg>
            {{ selectedNode.decayWarning }}
          </div>
        </div>

        <!-- 概念描述 -->
        <div class="nd-section">
          <div class="nds-title">概念描述</div>
          <p class="nd-desc">
            {{ selectedNode.desc }}
          </p>
        </div>

        <!-- 详细内容（content 字段）-->
        <div v-if="selectedNode.content" class="nd-section">
          <!-- 核心要点 -->
          <div class="nds-title">
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <polyline points="9 11 12 14 22 4" />
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
            </svg>
            核心要点
          </div>
          <ul class="key-points">
            <li
              v-for="(pt, i) in selectedNode.content.key_points"
              :key="i"
              class="kp-item"
            >
              <span class="kp-dot" />
              <span>{{ pt }}</span>
            </li>
          </ul>

          <!-- 示例代码 -->
          <template v-if="selectedNode.content.examples?.length">
            <div class="nds-title" style="margin-top: 14px">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <polyline points="16 18 22 12 16 6" />
                <polyline points="8 6 2 12 8 18" />
              </svg>
              示例
            </div>
            <div
              v-for="ex in selectedNode.content.examples"
              :key="ex.title"
              class="example-block"
            >
              <div class="ex-title">
                {{ ex.title }}
              </div>
              <pre
                v-if="ex.code"
                class="ex-code"
              ><code>{{ ex.code }}</code></pre>
              <p v-if="ex.text" class="ex-text">
                {{ ex.text }}
              </p>
            </div>
          </template>

          <!-- 常见误区 -->
          <template v-if="selectedNode.content.common_mistakes?.length">
            <div class="nds-title" style="margin-top: 14px">
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="8" x2="12" y2="12" />
                <line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              常见误区
            </div>
            <ul class="mistake-list">
              <li
                v-for="(m, i) in selectedNode.content.common_mistakes"
                :key="i"
                class="ml-item"
              >
                <svg
                  width="11"
                  height="11"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                >
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
                {{ m }}
              </li>
            </ul>
          </template>
        </div>

        <!-- 关联节点 -->
        <div class="nd-section">
          <div class="nds-title">
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="18" cy="5" r="3" />
              <circle cx="6" cy="12" r="3" />
              <circle cx="18" cy="19" r="3" />
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
              <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" />
            </svg>
            关联知识节点
          </div>
          <div class="related-nodes">
            <div
              v-for="rel in selectedNode.related"
              :key="rel.id"
              class="rn-item"
              @click="selectRelated(rel)"
            >
              <span class="rn-emoji">{{ rel.emoji }}</span>
              <div class="rn-info">
                <div class="rn-name">
                  {{ rel.name }}
                </div>
                <div class="rn-rel-type" :class="rel.type">
                  {{ getRelTypeLabel(rel.type) }}
                </div>
              </div>
              <div
                class="rn-mastery"
                :style="{ color: getMasteryColor(rel.mastery) }"
              >
                {{ rel.mastery }}%
              </div>
            </div>
          </div>
        </div>

        <!-- 来源定位 -->
        <div v-if="selectedNode.origins?.length" class="nd-section">
          <div class="nds-title">
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0118 0z" />
              <circle cx="12" cy="10" r="3" />
            </svg>
            来源定位
          </div>
          <div class="origins-list">
            <div
              v-for="origin in selectedNode.origins"
              :key="origin.doc_id || origin.session_id"
              class="origin-item"
            >
              <!-- 文档来源 -->
              <template
                v-if="origin.type === 'document' || origin.type === 'generated'"
              >
                <div class="origin-header">
                  <div
                    class="origin-icon"
                    :class="origin.type === 'generated' ? 'ai' : 'upload'"
                  >
                    <svg
                      v-if="origin.type === 'generated'"
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <circle cx="12" cy="12" r="3" />
                      <path
                        d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"
                      />
                    </svg>
                    <svg
                      v-else
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <path
                        d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"
                      />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                  </div>
                  <div class="origin-info">
                    <div class="origin-name">
                      {{ origin.doc_name }}
                    </div>
                    <div class="origin-location">
                      <span v-if="origin.location.page"
                        >第 {{ origin.location.page }} 页</span
                      >
                      <span v-if="origin.location.section" class="loc-sep"
                        >·</span
                      >
                      <span v-if="origin.location.section">{{
                        origin.location.section
                      }}</span>
                      <span v-if="origin.location.paragraph" class="loc-sep"
                        >·</span
                      >
                      <span v-if="origin.location.paragraph"
                        >第 {{ origin.location.paragraph }} 段</span
                      >
                      <span v-if="origin.location.slide"
                        >第 {{ origin.location.slide }} 张幻灯片</span
                      >
                    </div>
                  </div>
                  <button
                    class="origin-jump-btn"
                    title="前往文档"
                    @click="$router.push('/documents')"
                  >
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <path
                        d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"
                      />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                  </button>
                </div>
                <!-- 原文摘录 -->
                <div v-if="origin.excerpt" class="origin-excerpt">
                  <span class="excerpt-label">原文</span>
                  <blockquote class="excerpt-text">
                    {{ origin.excerpt }}
                  </blockquote>
                </div>
              </template>

              <!-- 会话来源 -->
              <template v-else-if="origin.type === 'session'">
                <div class="origin-header">
                  <div class="origin-icon session">
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <path
                        d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
                      />
                    </svg>
                  </div>
                  <div class="origin-info">
                    <div class="origin-name">人机交互学习</div>
                    <div class="origin-location">
                      {{ origin.location.context }}
                    </div>
                  </div>
                  <button
                    class="origin-jump-btn"
                    title="查看会话"
                    @click="$router.push('/sessions')"
                  >
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <path
                        d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"
                      />
                      <polyline points="15 3 21 3 21 9" />
                      <line x1="10" y1="14" x2="21" y2="3" />
                    </svg>
                  </button>
                </div>
                <div v-if="origin.excerpt" class="origin-excerpt">
                  <span class="excerpt-label">摘录</span>
                  <blockquote class="excerpt-text">
                    {{ origin.excerpt }}
                  </blockquote>
                </div>
              </template>
            </div>
          </div>
        </div>

        <!-- 学习记录 -->
        <div class="nd-section">
          <div class="nds-title">
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
            学习记录
          </div>
          <div class="study-timeline">
            <div
              v-for="log in selectedNode.logs"
              :key="log.date"
              class="stl-item"
            >
              <div class="stl-left">
                <div class="stl-dot" :class="log.type" />
                <div class="stl-line" />
              </div>
              <div class="stl-content">
                <div class="stl-text">
                  {{ log.text }}
                </div>
                <div class="stl-date">
                  {{ log.date }}
                </div>
                <div v-if="log.gain" class="stl-gain">
                  <svg
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <polyline points="18 15 12 9 6 15" />
                  </svg>
                  掌握度 +{{ log.gain }}%
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- 快捷操作 -->
        <div class="nd-quick-actions">
          <button class="nqa-btn" @click="$router.push('/quiz')">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M9 11l3 3L22 4" />
            </svg>
            出题练习
          </button>
          <button class="nqa-btn" @click="$router.push('/graph')">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="18" cy="5" r="3" />
              <circle cx="6" cy="12" r="3" />
              <circle cx="18" cy="19" r="3" />
              <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" />
            </svg>
            图谱中查看
          </button>
          <button class="nqa-btn">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
            </svg>
            添加笔记
          </button>
        </div>
      </div>

      <!-- Empty detail state -->
      <div v-else class="kb-detail kb-detail-empty">
        <div class="kde-icon">
          <svg
            width="36"
            height="36"
            viewBox="0 0 24 24"
            fill="none"
            stroke-width="1.5"
          >
            <defs>
              <linearGradient id="kbg" x1="0" y1="0" x2="24" y2="24">
                <stop stop-color="#6366f1" />
                <stop offset="1" stop-color="#a855f7" />
              </linearGradient>
            </defs>
            <circle stroke="url(#kbg)" cx="18" cy="5" r="3" />
            <circle stroke="url(#kbg)" cx="6" cy="12" r="3" />
            <circle stroke="url(#kbg)" cx="18" cy="19" r="3" />
            <line
              stroke="url(#kbg)"
              x1="8.59"
              y1="13.51"
              x2="15.42"
              y2="17.49"
            />
            <line
              stroke="url(#kbg)"
              x1="15.41"
              y1="6.51"
              x2="8.59"
              y2="10.49"
            />
          </svg>
        </div>
        <p class="kde-text">选择左侧节点<br />查看详细掌握情况</p>
      </div>
    </div>

    <!-- Upload modal -->
    <transition name="modal">
      <div
        v-if="showUpload"
        class="modal-overlay"
        @click.self="showUpload = false"
      >
        <div class="upload-modal card">
          <div class="um-header">
            <h3>添加文档</h3>
            <button class="nd-close" @click="showUpload = false">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
              >
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          </div>
          <div
            class="upload-zone"
            :class="{ dragging: isDragging }"
            @dragover.prevent="isDragging = true"
            @dragleave="isDragging = false"
            @drop.prevent="isDragging = false"
          >
            <div class="uz-icon">📄</div>
            <div class="uz-title">拖拽文件至此，或点击选择</div>
            <div class="uz-desc">支持 PDF、Markdown、Word、TXT</div>
            <button class="btn btn-ghost btn-sm" style="margin-top: 10px">
              选择文件
            </button>
          </div>
          <div class="um-hint">
            <svg
              width="12"
              height="12"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            Agent 将自动从文档中提取知识节点，并关联到你的知识图谱
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed } from "vue";
import { useRouter } from "vue-router";

const router = useRouter();
const searchQuery = ref("");
const searchFocused = ref(false);
const activeFilter = ref("all");
const sortBy = ref("recent");
const selectedNode = ref(null);
const showUpload = ref(false);
const isDragging = ref(false);

// ── 数据 ────────────────────────────────────────────────────────
const nodes = ref([
  {
    id: 1,
    label: "递归算法",
    emoji: "🔄",
    subject: "算法",
    mastery: 72,
    understanding: 80,
    memory: 65,
    connection: 70,
    lastStudied: "今天",
    decayWarning: null,
    tags: ["递归", "分治", "算法基础"],
    desc: "将大问题分解为同类型的小问题，是分治、动态规划等算法的基础。三要素：基础情况、递归关系、终止保证。",
    // 详细内容（API: node.content）
    content: {
      key_points: [
        "终止条件（Base Case）：递归必须有明确的停止时刻，否则会无限调用导致栈溢出",
        "递推关系（Recursive Case）：大问题必须能拆解为规模更小的同类问题",
        "调用自身：函数在执行中直接或间接调用自身，每次调用规模缩小",
      ],
      examples: [
        {
          title: "斐波那契数列",
          code: "def fib(n):\n    if n <= 1: return n       # 终止条件\n    return fib(n-1) + fib(n-2) # 递推关系",
        },
        {
          title: "汉诺塔",
          code: 'def hanoi(n, from_rod, to_rod, aux_rod):\n    if n == 1:\n        print(f"移动圆盘 1: {from_rod} → {to_rod}")\n        return\n    hanoi(n-1, from_rod, aux_rod, to_rod)\n    print(f"移动圆盘 {n}: {from_rod} → {to_rod}")\n    hanoi(n-1, aux_rod, to_rod, from_rod)',
        },
      ],
      common_mistakes: [
        "忘记写终止条件，导致无限递归和 RecursionError",
        "递推方向错误：每次递归调用没有让问题规模缩小",
        "对性能误解：未做记忆化时存在大量重复计算（如朴素 fib）",
      ],
    },
    // 精确来源定位（API: node.origins）
    origins: [
      {
        doc_id: "doc_01",
        doc_name: "数据结构与算法.pdf",
        type: "document",
        location: { page: 45, section: "第3章 递归与分治", paragraph: 2 },
        excerpt:
          "递归算法是一种直接或间接地调用自身的算法。在计算机实现时，递归算法往往比非递归算法需要更多的存储空间，但逻辑更为清晰。",
      },
      {
        session_id: "sess_01",
        type: "session",
        location: {
          message_index: 3,
          context: "你问：递归的三要素是什么？ · 2026-04-09 11:32",
        },
        excerpt:
          "Agent 在对话中解析了终止条件、递推关系、调用自身三个要素，并给出了汉诺塔示例。",
      },
      {
        doc_id: "doc_02",
        doc_name: "递归算法课件.pdf",
        type: "generated",
        location: { slide: 2, section: "核心概念" },
        excerpt: null,
      },
    ],
    related: [
      { id: 2, name: "分治思想", emoji: "⚡", type: "prereq", mastery: 55 },
      { id: 3, name: "动态规划", emoji: "📊", type: "extends", mastery: 38 },
      { id: 5, name: "二叉树遍历", emoji: "🌳", type: "applies", mastery: 85 },
      { id: 7, name: "时间复杂度", emoji: "⏱️", type: "related", mastery: 78 },
    ],
    logs: [
      {
        type: "study",
        text: "学习了递归三要素，完成汉诺塔代码实现",
        date: "今天 11:30",
        gain: 5,
      },
      {
        type: "quiz",
        text: "随堂测验 4/5 正确（答错了复杂度比较题）",
        date: "今天 11:45",
        gain: 2,
      },
      {
        type: "study",
        text: "学习了分治思想与递归的关系",
        date: "3天前",
        gain: 8,
      },
      {
        type: "review",
        text: "复习了 Base Case 的重要性",
        date: "5天前",
        gain: 3,
      },
    ],
  },
  {
    id: 2,
    label: "分治思想",
    emoji: "⚡",
    subject: "算法",
    mastery: 55,
    understanding: 60,
    memory: 50,
    connection: 55,
    lastStudied: "3天前",
    decayWarning: "⚠️ 记忆度偏低，建议尽快复习",
    tags: ["分治", "归并", "算法设计"],
    desc: "将问题分解为独立的子问题分别求解，再合并结果。典型应用：归并排序、快速排序、二分查找。",
    content: {
      key_points: [
        "分解（Divide）：将原问题划分为若干规模较小的子问题",
        "解决（Conquer）：递归地求解每个子问题",
        "合并（Combine）：将子问题的解合并为原问题的解",
      ],
      examples: [
        {
          title: "归并排序",
          code: "# 先分成两半，各自排序，再合并\ndef merge_sort(arr):\n    if len(arr) <= 1: return arr\n    mid = len(arr) // 2\n    return merge(merge_sort(arr[:mid]), merge_sort(arr[mid:]))",
        },
      ],
      common_mistakes: [
        "子问题之间有依赖关系（不独立），不适合分治",
        "合并步骤复杂度过高，导致整体性能下降",
      ],
    },
    origins: [
      {
        doc_id: "doc_01",
        doc_name: "数据结构与算法.pdf",
        type: "document",
        location: { page: 65, section: "第4章 分治策略", paragraph: 1 },
        excerpt:
          "分治法的设计思想是将一个难以直接解决的大问题，分割成一些规模较小的相同问题，以便各个击破，分而治之。",
      },
    ],
    related: [
      { id: 1, name: "递归算法", emoji: "🔄", type: "applies", mastery: 72 },
      { id: 4, name: "归并排序", emoji: "🗂️", type: "extends", mastery: 65 },
    ],
    logs: [
      { type: "study", text: "学习了归并排序实现", date: "3天前", gain: 10 },
      { type: "quiz", text: "练习了2道分治题目", date: "5天前", gain: 5 },
    ],
  },
  {
    id: 3,
    label: "动态规划",
    emoji: "📊",
    subject: "算法",
    mastery: 38,
    understanding: 40,
    memory: 35,
    connection: 40,
    lastStudied: "5天前",
    decayWarning: "⚠️ 已超过推荐复习周期，建议今日复习",
    tags: ["DP", "记忆化", "最优子结构"],
    desc: "通过记忆化或填表法解决重叠子问题，避免重复计算。核心：最优子结构 + 重叠子问题。",
    content: {
      key_points: [
        "最优子结构：问题的最优解包含子问题的最优解",
        "重叠子问题：同一子问题被重复求解多次",
        "状态转移方程：dp[i] = f(dp[i-1], dp[i-2], ...)",
      ],
      examples: [],
      common_mistakes: [
        "与分治混淆：分治子问题独立，DP 子问题重叠",
        "状态定义不清晰，导致转移方程错误",
      ],
    },
    origins: [
      {
        session_id: "sess_03",
        type: "session",
        location: {
          message_index: 1,
          context: "你问：动态规划和递归有什么区别？ · 2026-04-04",
        },
        excerpt:
          "DP 通过存储子问题结果避免重复计算，而朴素递归会重复求解相同子问题。",
      },
    ],
    related: [
      { id: 1, name: "递归算法", emoji: "🔄", type: "prereq", mastery: 72 },
      { id: 10, name: "神经网络", emoji: "🧠", type: "related", mastery: 30 },
    ],
    logs: [
      {
        type: "study",
        text: "了解了 DP 的基本概念和状态转移",
        date: "5天前",
        gain: 12,
      },
    ],
  },
  {
    id: 5,
    label: "二叉树遍历",
    emoji: "🌳",
    subject: "数据结构",
    mastery: 85,
    understanding: 90,
    memory: 80,
    connection: 85,
    lastStudied: "昨天",
    decayWarning: null,
    tags: ["二叉树", "遍历", "DFS"],
    desc: "前序、中序、后序三种递归遍历方式，以及层序（BFS）遍历。中序遍历 BST 得到有序序列。",
    content: {
      key_points: [
        "前序遍历：根 → 左 → 右（常用于复制树结构）",
        "中序遍历：左 → 根 → 右（BST 中序得到有序序列）",
        "后序遍历：左 → 右 → 根（常用于删除树）",
        "层序遍历：用队列实现，按层从上到下",
      ],
      examples: [
        {
          title: "中序遍历",
          code: "def inorder(root):\n    if not root: return []\n    return inorder(root.left) + [root.val] + inorder(root.right)",
        },
      ],
      common_mistakes: [],
    },
    origins: [
      {
        doc_id: "doc_01",
        doc_name: "数据结构与算法.pdf",
        type: "document",
        location: { page: 112, section: "第6章 树", paragraph: 3 },
        excerpt:
          "对二叉树的遍历是指按照某条搜索路径巡访树中每个结点，使得每个结点均被访问一次，而且仅被访问一次。",
      },
    ],
    related: [
      { id: 1, name: "递归算法", emoji: "🔄", type: "prereq", mastery: 72 },
      { id: 6, name: "图论基础", emoji: "🕸️", type: "extends", mastery: 42 },
    ],
    logs: [
      {
        type: "quiz",
        text: "测验满分，四种遍历全部实现正确",
        date: "昨天",
        gain: 8,
      },
      {
        type: "study",
        text: "深入理解了中序遍历与 BST 的关系",
        date: "昨天",
        gain: 5,
      },
    ],
  },
  {
    id: 7,
    label: "时间复杂度",
    emoji: "⏱️",
    subject: "算法",
    mastery: 78,
    understanding: 85,
    memory: 70,
    connection: 80,
    lastStudied: "今天",
    decayWarning: null,
    tags: ["Big-O", "复杂度分析", "递归树"],
    desc: "用大 O 表示算法运行时间随输入规模增长的趋势。常见：O(1) < O(log n) < O(n) < O(n log n) < O(n²)。",
    content: {
      key_points: [
        "O(1)：常数时间，与输入规模无关（数组随机访问）",
        "O(log n)：每次操作规模减半（二分查找）",
        "O(n log n)：常见于分治排序（归并、快排平均）",
        "O(n²)：双重循环（冒泡排序）",
      ],
      examples: [
        {
          title: "递归树分析 fib(n)",
          text: "fib(n) 时间复杂度为 O(2ⁿ)，因为每次调用产生两个子问题，形成高度为 n 的二叉树。",
        },
      ],
      common_mistakes: [
        "只看循环层数，忽略单次操作本身的复杂度",
        "混淆最坏/平均/最好时间复杂度",
      ],
    },
    origins: [
      {
        doc_id: "doc_01",
        doc_name: "数据结构与算法.pdf",
        type: "document",
        location: { page: 12, section: "第1章 算法分析", paragraph: 1 },
        excerpt:
          "算法的时间复杂度是一个函数，它定性描述该算法的运行时间。这是一个代表算法输入值的字符串的长度的函数。",
      },
    ],
    related: [
      { id: 1, name: "递归算法", emoji: "🔄", type: "related", mastery: 72 },
      { id: 2, name: "分治思想", emoji: "⚡", type: "related", mastery: 55 },
    ],
    logs: [
      { type: "study", text: "学习了递归树分析法", date: "今天", gain: 6 },
      { type: "study", text: "掌握了主定理的基本用法", date: "2天前", gain: 4 },
    ],
  },
  {
    id: 8,
    label: "微积分基础",
    emoji: "📐",
    subject: "数学",
    mastery: 60,
    understanding: 65,
    memory: 55,
    connection: 60,
    lastStudied: "4天前",
    decayWarning: null,
    tags: ["极限", "导数", "积分"],
    desc: "极限、导数和积分的基本概念。导数描述函数的瞬时变化率，积分是求面积的工具。",
    content: null,
    origins: [
      {
        doc_id: "doc_01",
        doc_name: "高等数学（下）.pdf",
        type: "document",
        location: { page: 1, section: "第1章 极限与连续" },
        excerpt: null,
      },
    ],
    related: [
      { id: 9, name: "偏导数", emoji: "🧮", type: "extends", mastery: 45 },
      { id: 11, name: "梯度下降", emoji: "📉", type: "applies", mastery: 22 },
    ],
    logs: [
      { type: "study", text: "完成了极限和导数基础", date: "4天前", gain: 15 },
    ],
  },
  {
    id: 12,
    label: "英语写作结构",
    emoji: "✍️",
    subject: "英语",
    mastery: 88,
    understanding: 92,
    memory: 85,
    connection: 88,
    lastStudied: "昨天",
    decayWarning: null,
    tags: ["议论文", "段落结构", "写作技巧"],
    desc: "议论文三段式结构：引言（Hook + Background + Thesis）、论述（Topic + Evidence + Analysis）、结论（Restate + Implication）。",
    content: null,
    origins: [
      {
        session_id: "sess_05",
        type: "session",
        location: {
          message_index: 2,
          context: "你问：如何写好英语议论文结构？ · 2026-04-08",
        },
        excerpt:
          "好的议论文结构是：引言段抛出 thesis statement，每个 body paragraph 围绕一个 topic sentence 展开。",
      },
    ],
    related: [],
    logs: [
      { type: "quiz", text: "写作练习评分 A，结构清晰", date: "昨天", gain: 4 },
      {
        type: "study",
        text: "学习了 Evidence + Analysis 的展开技巧",
        date: "3天前",
        gain: 7,
      },
    ],
  },
]);

// ── 统计 ────────────────────────────────────────────────────────
const kbStats = computed(() => [
  { val: nodes.value.length, label: "知识节点" },
  { val: nodes.value.filter((n) => n.mastery >= 80).length, label: "已掌握" },
  { val: nodes.value.filter((n) => n.mastery < 50).length, label: "待突破" },
  { val: nodes.value.filter((n) => n.decayWarning).length, label: "需复习" },
]);

const masteryDist = computed(() => {
  const bins = [
    { label: "0-20%", color: "#ef4444", count: 0 },
    { label: "20-40%", color: "#f97316", count: 0 },
    { label: "40-60%", color: "#f59e0b", count: 0 },
    { label: "60-80%", color: "#84cc16", count: 0 },
    { label: "80-100%", color: "#10b981", count: 0 },
  ];
  nodes.value.forEach((n) => {
    const i = Math.min(4, Math.floor(n.mastery / 20));
    bins[i].count++;
  });
  const max = Math.max(...bins.map((b) => b.count), 1);
  return bins.map((b) => ({ ...b, pct: (b.count / max) * 100 }));
});

// ── 筛选 ────────────────────────────────────────────────────────
const subjects = ["算法", "数据结构", "AI", "数学", "英语"];
const filterTabs = computed(() => [
  { key: "all", label: "全部", count: nodes.value.length, color: null },
  {
    key: "weak",
    label: "待突破",
    count: nodes.value.filter((n) => n.mastery < 50).length,
    color: "#ef4444",
  },
  {
    key: "review",
    label: "需复习",
    count: nodes.value.filter((n) => n.decayWarning).length,
    color: "#f59e0b",
  },
  ...subjects
    .map((s) => ({
      key: s,
      label: s,
      count: nodes.value.filter((n) => n.subject === s).length,
      color: getSubjectColor(s),
    }))
    .filter((f) => f.count > 0),
]);

const filteredNodes = computed(() => {
  let list = nodes.value;
  if (searchQuery.value)
    list = list.filter(
      (n) =>
        n.label.includes(searchQuery.value) ||
        n.tags.some((t) => t.includes(searchQuery.value)),
    );
  if (activeFilter.value === "weak") list = list.filter((n) => n.mastery < 50);
  else if (activeFilter.value === "review")
    list = list.filter((n) => n.decayWarning);
  else if (activeFilter.value !== "all")
    list = list.filter((n) => n.subject === activeFilter.value);

  return [...list].sort((a, b) => {
    if (sortBy.value === "mastery-desc") return b.mastery - a.mastery;
    if (sortBy.value === "mastery-asc") return a.mastery - b.mastery;
    if (sortBy.value === "name") return a.label.localeCompare(b.label);
    return 0;
  });
});

// ── 工具函数 ─────────────────────────────────────────────────────
function getSubjectColor(subject) {
  return (
    {
      算法: "#6366f1",
      数据结构: "#10b981",
      AI: "#a855f7",
      数学: "#f59e0b",
      英语: "#3b82f6",
    }[subject] || "#6366f1"
  );
}
function getMasteryColor(mastery) {
  if (mastery >= 80) return "#10b981";
  if (mastery >= 50) return "#f59e0b";
  return "#ef4444";
}
function getNodeDims(node) {
  return [
    {
      label: "理解度",
      val: node.understanding,
      color: getMasteryColor(node.understanding),
      desc: "能用自己的话解释这个概念",
    },
    {
      label: "记忆度",
      val: node.memory,
      color: getMasteryColor(node.memory),
      desc: "当前记忆鲜活程度（随时间衰减）",
    },
    {
      label: "连接度",
      val: node.connection,
      color: getMasteryColor(node.connection),
      desc: "与其他知识的关联深度",
    },
  ];
}
function getRelTypeLabel(type) {
  return (
    {
      prereq: "前置依赖",
      extends: "延伸",
      applies: "应用场景",
      related: "相关概念",
    }[type] || type
  );
}

function selectRelated(rel) {
  const node = nodes.value.find((n) => n.id === rel.id);
  if (node) selectedNode.value = node;
}

function studyNode() {
  router.push({ path: "/chat", query: { topic: selectedNode.value?.label } });
}
</script>

<style scoped>
.kb-page {
  padding: 24px 28px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  max-width: 1300px;
  box-sizing: border-box;
}

/* Header */
.kb-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 16px;
  flex-shrink: 0;
}
.page-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.4px;
  margin-bottom: 3px;
}
.page-subtitle {
  font-size: 13px;
  color: var(--text-secondary);
}
.kb-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.search-bar {
  display: flex;
  align-items: center;
  gap: 7px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 6px 12px;
  transition: var(--transition);
}
.search-bar.focused {
  border-color: var(--border-active);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);
}
.search-bar input {
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 13px;
  width: 180px;
}
.search-bar input::placeholder {
  color: var(--text-dim);
}

/* Stats bar */
.kb-stats {
  display: flex;
  align-items: center;
  gap: 0;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 12px 20px;
  margin-bottom: 12px;
  flex-shrink: 0;
}
.ks-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 16px;
  border-right: 1px solid var(--border);
}
.ks-item:first-child {
  padding-left: 0;
}
.ks-val {
  font-size: 20px;
  font-weight: 700;
  letter-spacing: -0.5px;
}
.ks-label {
  font-size: 11px;
  color: var(--text-muted);
}
.ks-divider {
  width: 1px;
  height: 32px;
  background: var(--border);
  margin: 0 12px;
}

/* Mastery distribution */
.ks-mastery-dist {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  padding-left: 12px;
}
.kmd-label {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  margin-right: 4px;
}
.kmd-bars {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 32px;
}
.kmd-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
}
.kmd-fill {
  width: 14px;
  border-radius: 3px 3px 0 0;
  min-height: 3px;
  transition: height 0.4s ease;
}
.kmd-count {
  font-size: 9px;
  color: var(--text-dim);
}

/* Filter tabs */
.kb-filters {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-bottom: 12px;
  flex-shrink: 0;
  flex-wrap: wrap;
}
.kb-filter-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 11px;
  border-radius: var(--radius-full);
  background: transparent;
  border: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: var(--transition);
}
.kb-filter-btn:hover {
  color: var(--text-primary);
  border-color: var(--border-hover);
}
.kb-filter-btn.active {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}
.kfb-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}
.kfb-count {
  font-size: 10px;
  background: var(--bg-hover);
  border-radius: 8px;
  padding: 0 5px;
  color: var(--text-dim);
}
.kb-sort {
  margin-left: auto;
}
.kb-sort select {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 5px 8px;
  color: var(--text-secondary);
  font-size: 12px;
  outline: none;
  cursor: pointer;
}

/* Layout */
.kb-layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 14px;
  flex: 1;
  min-height: 0;
}

/* Node list */
.kb-list {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-right: 4px;
}

.kn-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px 14px;
  cursor: pointer;
  transition: var(--transition);
}
.kn-card:hover {
  border-color: var(--border-hover);
  transform: translateX(2px);
}
.kn-card.active {
  background: var(--brand-dim);
  border-color: var(--border-active);
}

.kn-top {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 9px;
}
.kn-emoji-wrap {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.kn-emoji {
  font-size: 16px;
}
.kn-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.kn-subject-line {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);
}
.kn-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.kn-sep {
  opacity: 0.4;
}
.kn-studied {
  color: var(--text-dim);
}
.kn-mastery-badge {
  font-size: 15px;
  font-weight: 700;
  letter-spacing: -0.5px;
  margin-left: auto;
  flex-shrink: 0;
}

.kn-bottom {
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.kn-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.kn-tag {
  font-size: 10px;
  padding: 1px 7px;
  border-radius: 4px;
  background: var(--bg-hover);
  color: var(--text-dim);
}
.kn-card.active .kn-tag {
  background: rgba(99, 102, 241, 0.15);
  color: var(--brand-light);
}

.kb-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 40px 20px;
  color: var(--text-muted);
}
.ke-icon {
  font-size: 32px;
}
.ke-text {
  font-size: 13px;
  text-align: center;
}

/* Detail panel */
.kb-detail {
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding-right: 2px;
}
.kb-detail-empty {
  align-items: center;
  justify-content: center;
}
.kde-icon {
  width: 72px;
  height: 72px;
  border-radius: 16px;
  background: var(--brand-dim);
  border: 1px solid rgba(99, 102, 241, 0.2);
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 4px;
}
.kde-text {
  font-size: 13px;
  color: var(--text-muted);
  text-align: center;
  line-height: 1.8;
}

/* Node header */
.nd-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
}
.nd-emoji-bg {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.nd-emoji {
  font-size: 26px;
}
.nd-title-wrap {
  flex: 1;
  min-width: 0;
}
.nd-title {
  font-size: 18px;
  font-weight: 800;
  color: var(--text-primary);
  letter-spacing: -0.4px;
  margin-bottom: 6px;
}
.nd-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.nd-actions-top {
  flex-shrink: 0;
}

/* Mastery section */
.mastery-section {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 16px;
}
.ms-overview {
  display: flex;
  gap: 16px;
  align-items: center;
}
.mso-circle {
  flex-shrink: 0;
}
.mso-dims {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.msod-header {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}
.msod-label {
  font-size: 12px;
  color: var(--text-secondary);
  font-weight: 500;
}
.msod-val {
  font-size: 12px;
  font-weight: 700;
}
.msod-desc {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 2px;
}
.decay-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--yellow);
  background: var(--yellow-dim);
  border: 1px solid rgba(245, 158, 11, 0.2);
  border-radius: var(--radius-sm);
  padding: 7px 10px;
  margin-top: 10px;
}

/* Sections */
.nd-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.nds-title {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.07em;
}
.nd-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
}

/* Related nodes */
.related-nodes {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.rn-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  cursor: pointer;
  transition: var(--transition);
}
.rn-item:hover {
  background: var(--brand-dim);
  border-color: var(--border-active);
}
.rn-emoji {
  font-size: 16px;
  flex-shrink: 0;
}
.rn-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}
.rn-rel-type {
  font-size: 10px;
  margin-top: 1px;
}
.rn-rel-type.prereq {
  color: var(--red);
}
.rn-rel-type.extends {
  color: var(--brand-light);
}
.rn-rel-type.applies {
  color: var(--green);
}
.rn-rel-type.related {
  color: var(--text-dim);
}
.rn-mastery {
  font-size: 13px;
  font-weight: 700;
  margin-left: auto;
  flex-shrink: 0;
}

/* Content: key points, examples, mistakes */
.key-points {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0;
  margin: 0;
  list-style: none;
}
.kp-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.kp-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-light);
  flex-shrink: 0;
  margin-top: 5px;
}

.example-block {
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.ex-title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  padding: 8px 12px 6px;
  border-bottom: 1px solid var(--border);
}
.ex-code {
  margin: 0;
  padding: 10px 12px;
  font-size: 11px;
  line-height: 1.7;
  color: var(--text-primary);
  font-family: "SF Mono", "Fira Code", monospace;
  overflow-x: auto;
  background: rgba(0, 0, 0, 0.2);
}
[data-theme="light"] .ex-code {
  background: #f8f8fa;
}
.ex-text {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 10px 12px;
  margin: 0;
  line-height: 1.6;
}

.mistake-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0;
  margin: 0;
  list-style: none;
}
.ml-item {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.ml-item svg {
  color: var(--red);
  flex-shrink: 0;
  margin-top: 3px;
}

/* Origins (精确来源定位) */
.origins-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.origin-item {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
  background: var(--bg-hover);
}
.origin-header {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 10px 12px;
}
.origin-icon {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.origin-icon.upload {
  background: rgba(99, 102, 241, 0.1);
  color: var(--brand-light);
}
.origin-icon.ai {
  background: rgba(168, 85, 247, 0.1);
  color: #a855f7;
}
.origin-icon.session {
  background: rgba(16, 185, 129, 0.1);
  color: var(--green);
}

.origin-info {
  flex: 1;
  min-width: 0;
}
.origin-name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.origin-location {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 2px;
  display: flex;
  align-items: center;
  gap: 3px;
  flex-wrap: wrap;
}
.loc-sep {
  color: var(--text-dim);
}

.origin-jump-btn {
  width: 26px;
  height: 26px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-muted);
  transition: var(--transition);
  flex-shrink: 0;
}
.origin-jump-btn:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}

.origin-excerpt {
  border-top: 1px solid var(--border);
  padding: 8px 12px;
  display: flex;
  gap: 8px;
  align-items: flex-start;
}
.excerpt-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-dim);
  letter-spacing: 0.05em;
  flex-shrink: 0;
  padding-top: 2px;
}
.excerpt-text {
  margin: 0;
  font-size: 11px;
  line-height: 1.7;
  color: var(--text-secondary);
  font-style: italic;
  border-left: 2px solid var(--brand-dim);
  padding-left: 8px;
}

/* Study timeline */
.study-timeline {
  display: flex;
  flex-direction: column;
}
.stl-item {
  display: flex;
  gap: 10px;
}
.stl-left {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 14px;
  flex-shrink: 0;
}
.stl-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}
.stl-dot.study {
  background: var(--brand-light);
}
.stl-dot.quiz {
  background: var(--green);
}
.stl-dot.review {
  background: var(--yellow);
}
.stl-line {
  flex: 1;
  width: 1.5px;
  background: var(--border);
  min-height: 12px;
}
.stl-item:last-child .stl-line {
  display: none;
}
.stl-content {
  flex: 1;
  padding-bottom: 14px;
}
.stl-text {
  font-size: 12px;
  color: var(--text-primary);
  line-height: 1.5;
}
.stl-date {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 2px;
}
.stl-gain {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  color: var(--green);
  margin-top: 3px;
}

/* Quick actions */
.nd-quick-actions {
  display: flex;
  gap: 6px;
  padding-top: 4px;
  flex-wrap: wrap;
}
.nqa-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: var(--transition);
}
.nqa-btn:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}

.nd-close {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
}
.nd-close:hover {
  background: var(--red-dim);
  color: var(--red);
}

/* Upload modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  z-index: 100;
  background: rgba(0, 0, 0, 0.6);
  backdrop-filter: blur(6px);
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
}
.upload-modal {
  width: 100%;
  max-width: 480px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.um-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.um-header h3 {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.upload-zone {
  border: 2px dashed var(--border);
  border-radius: var(--radius-lg);
  padding: 36px 24px;
  text-align: center;
  transition: var(--transition);
  cursor: pointer;
}
.upload-zone.dragging {
  border-color: var(--brand);
  background: var(--brand-dim);
}
.upload-zone:hover {
  border-color: var(--border-hover);
}
.uz-icon {
  font-size: 36px;
  margin-bottom: 10px;
}
.uz-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 5px;
}
.uz-desc {
  font-size: 12px;
  color: var(--text-muted);
}
.um-hint {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-muted);
  background: var(--bg-hover);
  padding: 10px 12px;
  border-radius: var(--radius-sm);
}

/* Transitions */
.modal-enter-active,
.modal-leave-active {
  transition: all 0.25s ease;
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from .upload-modal {
  transform: scale(0.95) translateY(8px);
}
</style>
