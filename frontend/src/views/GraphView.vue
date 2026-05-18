<template>
  <div class="graph-page">
    <!-- ── 顶部工具栏 ─────────────────────────────────────────── -->
    <div class="graph-toolbar">
      <div class="gt-left">
        <!-- 视图切换 -->
        <div class="view-switch">
          <button
            class="vs-btn"
            :class="{ active: viewMode === 'graph' }"
            @click="viewMode = 'graph'"
          >
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
            图谱
          </button>
          <button
            class="vs-btn"
            :class="{ active: viewMode === 'list' }"
            @click="viewMode = 'list'"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="8" y1="6" x2="21" y2="6" />
              <line x1="8" y1="12" x2="21" y2="12" />
              <line x1="8" y1="18" x2="21" y2="18" />
              <line x1="3" y1="6" x2="3.01" y2="6" />
              <line x1="3" y1="12" x2="3.01" y2="12" />
              <line x1="3" y1="18" x2="3.01" y2="18" />
            </svg>
            列表
          </button>
        </div>
        <span class="graph-stats">
          {{
            viewMode === "graph"
              ? `${visibleNodes.length} / ${nodes.length} 个概念 · ${visibleEdges.length} 条关联`
              : `${sortedNodes.length} / ${nodes.length} 个概念`
          }}
        </span>
      </div>

      <div class="gt-center">
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
            placeholder="搜索知识节点..."
            @focus="searchFocused = true"
            @blur="searchFocused = false"
          />
        </div>
      </div>

      <div class="gt-right">
        <!-- 列表视图排序 -->
        <select v-if="viewMode === 'list'" v-model="sortBy" class="sort-select">
          <option value="recent">最近学习</option>
          <option value="mastery-desc">掌握度↓</option>
          <option value="mastery-asc">掌握度↑</option>
          <option value="name">名称</option>
        </select>
        <!-- 图谱视图控制 -->
        <div v-if="viewMode === 'graph'" class="graph-controls">
          <button class="ctrl-btn" title="重置视图" @click="resetView">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M3 12a9 9 0 109-9 9.75 9.75 0 00-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
            </svg>
          </button>
          <span class="zoom-val">{{ Math.round(zoom * 100) }}%</span>
        </div>
      </div>
    </div>

    <!-- ── 主体区 ──────────────────────────────────────────────── -->
    <div class="graph-body">
      <!-- 加载中 -->
      <div v-if="loading" class="graph-loading">
        <div class="gl-spinner" />
        <span>加载知识图谱...</span>
      </div>

      <!-- 空状态 -->
      <div v-else-if="nodes.length === 0" class="graph-empty">
        <div class="ge-icon">🕸️</div>
        <div class="ge-title">知识图谱为空</div>
        <div class="ge-desc">上传文档或开始学习，知识节点将自动出现在这里</div>
        <button
          class="btn btn-primary btn-sm"
          @click="$router.push('/documents')"
        >
          上传文档
        </button>
      </div>

      <!-- ═══ 图谱视图 ═════════════════════════════════════════ -->
      <template v-if="!loading && nodes.length > 0 && viewMode === 'graph'">
        <div ref="canvasWrap" class="graph-canvas-wrap">
          <svg
            class="graph-svg"
            :viewBox="`0 0 ${svgW} ${svgH}`"
            @mousedown="onSvgMousedown"
            @mousemove="onSvgMousemove"
            @mouseup="onSvgMouseup"
            @wheel.prevent="onWheel"
          >
            <defs>
              <radialGradient id="node-glow" cx="50%" cy="50%" r="50%">
                <stop offset="0%" stop-color="#6366f1" stop-opacity="0.3" />
                <stop offset="100%" stop-color="#6366f1" stop-opacity="0" />
              </radialGradient>
            </defs>

            <g :transform="`translate(${pan.x},${pan.y}) scale(${zoom})`">
              <!-- 边：无选中时只显示 prereq 边（淡显），选中时只显示该节点的连接边 -->
              <g class="edges-layer">
                <line
                  v-for="edge in displayedEdges"
                  :key="edge.id"
                  :x1="getNode(edge.source)?.x"
                  :y1="getNode(edge.source)?.y"
                  :x2="getNode(edge.target)?.x"
                  :y2="getNode(edge.target)?.y"
                  :stroke="edgeColors[edge.type]"
                  :stroke-width="
                    selectedNode && isConnected(edge, selectedNode.id) ? 2 : 1
                  "
                  :stroke-dasharray="edge.type === 'related' ? '4,3' : 'none'"
                  :opacity="
                    selectedNode
                      ? isConnected(edge, selectedNode.id)
                        ? 0.75
                        : 0.08
                      : 0.18
                  "
                />
              </g>

              <!-- 节点 -->
              <g
                v-for="node in visibleNodes"
                :key="node.id"
                :transform="`translate(${node.x},${node.y})`"
                class="node-group"
                :class="{
                  selected: selectedNode?.id === node.id,
                  dimmed:
                    selectedNode && !isConnected2(node.id, selectedNode.id),
                }"
                @mousedown.stop="onNodeMousedown($event, node)"
                @click.stop="selectNode(node)"
              >
                <!-- 选中光环 -->
                <circle
                  v-if="selectedNode?.id === node.id"
                  :r="getNodeRadius(node) + 10"
                  :fill="getNodeColor(node)"
                  opacity="0.12"
                />
                <!-- 掌握度环 -->
                <circle
                  :r="getNodeRadius(node) + 4"
                  fill="none"
                  stroke="var(--bg-hover)"
                  stroke-width="3"
                />
                <circle
                  :r="getNodeRadius(node) + 4"
                  fill="none"
                  :stroke="getMasteryColor(node.mastery)"
                  stroke-width="3"
                  stroke-linecap="round"
                  :stroke-dasharray="`${(node.mastery / 100) * (2 * Math.PI * (getNodeRadius(node) + 4)).toFixed(1)} 999`"
                  :transform="`rotate(-90)`"
                  opacity="0.8"
                />
                <!-- 节点背景 -->
                <circle
                  :r="getNodeRadius(node)"
                  :fill="getNodeBg(node)"
                  :stroke="getNodeColor(node)"
                  stroke-width="1.5"
                  opacity="0.9"
                />
                <!-- emoji -->
                <text
                  text-anchor="middle"
                  dominant-baseline="central"
                  :font-size="getNodeRadius(node) * 0.9"
                  style="user-select: none; pointer-events: none"
                >
                  {{ node.emoji }}
                </text>
                <!-- 标签 -->
                <text
                  text-anchor="middle"
                  :y="getNodeRadius(node) + 14"
                  font-size="11"
                  fill="var(--text-secondary)"
                  style="user-select: none; pointer-events: none"
                  :font-weight="selectedNode?.id === node.id ? '600' : '400'"
                >
                  {{ node.label }}
                </text>
              </g>
            </g>
          </svg>
        </div>
      </template>

      <!-- ═══ 列表视图 ═════════════════════════════════════════ -->
      <template v-else-if="!loading && nodes.length > 0">
        <div class="list-view">
          <!-- 统计条 -->
          <div class="list-stats">
            <div v-for="s in listStats" :key="s.label" class="ls-item">
              <div class="ls-val text-gradient">
                {{ s.val }}
              </div>
              <div class="ls-label">
                {{ s.label }}
              </div>
            </div>
            <div class="ls-divider" />
            <div class="ls-mastery">
              <div class="lsm-label">掌握度分布</div>
              <div class="lsm-bars">
                <div
                  v-for="d in masteryDist"
                  :key="d.label"
                  class="lsm-bar"
                  :title="`${d.label}: ${d.count}个`"
                >
                  <div
                    class="lsm-fill"
                    :style="{ height: d.pct + '%', background: d.color }"
                  />
                  <div class="lsm-count">
                    {{ d.count }}
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 节点卡片列表 -->
          <div class="node-list">
            <div
              v-for="node in sortedNodes"
              :key="node.id"
              class="node-card"
              :class="{ active: selectedNode?.id === node.id }"
              @click="selectNode(node)"
            >
              <div class="nc-top">
                <div
                  class="nc-emoji-wrap"
                  :style="{ background: getSubjectColor(node.subject) + '18' }"
                >
                  <span class="nc-emoji">{{ node.emoji }}</span>
                </div>
                <div class="nc-main">
                  <div class="nc-name">
                    {{ node.label }}
                  </div>
                  <div class="nc-meta">
                    <span
                      class="nc-dot"
                      :style="{ background: getSubjectColor(node.subject) }"
                    />
                    {{ node.subject }}
                    <span class="nc-sep">·</span>
                    <span>{{ node.lastStudied }}</span>
                  </div>
                </div>
                <div
                  class="nc-mastery-val"
                  :style="{ color: getMasteryColor(node.mastery) }"
                >
                  {{ node.mastery }}%
                </div>
              </div>
              <div class="nc-bottom">
                <div class="progress-bar">
                  <div
                    class="progress-fill"
                    :style="{
                      width: node.mastery + '%',
                      background: getMasteryColor(node.mastery),
                    }"
                  />
                </div>
                <div class="nc-tags">
                  <span
                    v-for="tag in (node.tags || []).slice(0, 3)"
                    :key="tag"
                    class="nc-tag"
                    >{{ tag }}</span
                  >
                </div>
              </div>
            </div>

            <div v-if="sortedNodes.length === 0" class="list-empty">
              <div>🔍</div>
              <div>没有找到匹配的知识节点</div>
            </div>
          </div>
        </div>
      </template>

      <!-- ═══ 右侧详情面板（两个视图共用）═════════════════════ -->
      <transition name="panel-slide">
        <div v-if="selectedNode" class="detail-panel">
          <!-- 面板头部 -->
          <div class="dp-header">
            <div
              class="dp-emoji"
              :style="{
                background: getSubjectColor(selectedNode.subject) + '15',
              }"
            >
              {{ selectedNode.emoji }}
            </div>
            <div class="dp-title-wrap">
              <h3 class="dp-title">
                {{ selectedNode.label }}
              </h3>
              <div class="dp-badges">
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
                <span
                  v-if="selectedNode.mastery >= 80"
                  class="badge badge-green"
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
            <button class="dp-close" @click="selectedNode = null">
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

          <!-- 滚动内容区 -->
          <div class="dp-body">
            <!-- 掌握度 -->
            <div class="dp-mastery">
              <div class="dpm-circle">
                <svg width="72" height="72" viewBox="0 0 72 72">
                  <circle
                    cx="36"
                    cy="36"
                    r="30"
                    fill="none"
                    stroke="var(--bg-hover)"
                    stroke-width="5"
                  />
                  <circle
                    cx="36"
                    cy="36"
                    r="30"
                    fill="none"
                    :stroke="getMasteryColor(selectedNode.mastery)"
                    stroke-width="5"
                    stroke-linecap="round"
                    :stroke-dasharray="`${(selectedNode.mastery / 100) * 188.5} 188.5`"
                    transform="rotate(-90 36 36)"
                    style="transition: stroke-dasharray 0.6s ease"
                  />
                  <text
                    x="36"
                    y="33"
                    text-anchor="middle"
                    font-size="14"
                    font-weight="700"
                    fill="var(--text-primary)"
                  >
                    {{ selectedNode.mastery }}%
                  </text>
                  <text
                    x="36"
                    y="44"
                    text-anchor="middle"
                    font-size="8"
                    fill="var(--text-dim)"
                  >
                    掌握度
                  </text>
                </svg>
              </div>
              <div class="dpm-dims">
                <div
                  v-for="d in getNodeDims(selectedNode)"
                  :key="d.label"
                  class="dpmd-item"
                >
                  <div class="dpmd-top">
                    <span class="dpmd-label">{{ d.label }}</span>
                    <span class="dpmd-val" :style="{ color: d.color }">{{
                      d.val
                    }}</span>
                  </div>
                  <div class="progress-bar">
                    <div
                      class="progress-fill"
                      :style="{ width: d.val, background: d.color }"
                    />
                  </div>
                </div>
              </div>
            </div>

            <!-- 衰减提醒 -->
            <div v-if="selectedNode.decayWarning" class="dp-decay">
              <svg
                width="12"
                height="12"
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

            <!-- 描述 -->
            <div class="dp-section">
              <div class="dp-section-title">概念描述</div>
              <p class="dp-desc">
                {{ selectedNode.desc }}
              </p>
            </div>

            <!-- 核心要点 -->
            <div
              v-if="selectedNode.content?.key_points?.length"
              class="dp-section"
            >
              <div class="dp-section-title">
                <svg
                  width="11"
                  height="11"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <polyline points="9 11 12 14 22 4" />
                  <path
                    d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"
                  />
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
            </div>

            <!-- 示例 -->
            <div
              v-if="selectedNode.content?.examples?.length"
              class="dp-section"
            >
              <div class="dp-section-title">
                <svg
                  width="11"
                  height="11"
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
                v-for="(ex, i) in selectedNode.content.examples"
                :key="i"
                class="example-block"
              >
                <p class="ex-text">
                  {{ ex }}
                </p>
              </div>
            </div>

            <!-- 常见误区 -->
            <div
              v-if="selectedNode.content?.common_mistakes?.length"
              class="dp-section"
            >
              <div class="dp-section-title">
                <svg
                  width="11"
                  height="11"
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
                    width="10"
                    height="10"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                  >
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </svg>
                  {{
                    typeof m === "string"
                      ? m
                      : m.description || m.text || JSON.stringify(m)
                  }}
                </li>
              </ul>
            </div>

            <!-- 关联节点 -->
            <div class="dp-section">
              <div class="dp-section-title">
                <svg
                  width="11"
                  height="11"
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
                关联节点 ({{ getRelated(selectedNode.id).length }})
              </div>
              <div class="related-chips">
                <button
                  v-for="r in getRelated(selectedNode.id)"
                  :key="r.id"
                  class="related-chip"
                  @click="selectNode(r)"
                >
                  <span>{{ r.emoji }}</span>
                  <span>{{ r.label }}</span>
                  <span
                    class="rc-mastery"
                    :style="{ color: getMasteryColor(r.mastery) }"
                    >{{ r.mastery }}%</span
                  >
                </button>
              </div>
            </div>

            <!-- 来源定位 -->
            <div v-if="selectedNode.origins?.length" class="dp-section">
              <div class="dp-section-title">
                <svg
                  width="11"
                  height="11"
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
                  v-for="(origin, oi) in selectedNode.origins"
                  :key="origin.source_id + '_' + oi"
                  class="origin-item"
                >
                  <div class="origin-header">
                    <div
                      class="origin-icon"
                      :class="
                        origin.type === 'generated'
                          ? 'ai'
                          : origin.type === 'session'
                            ? 'session'
                            : 'upload'
                      "
                    >
                      <svg
                        v-if="origin.type === 'session'"
                        width="11"
                        height="11"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                      >
                        <path
                          d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
                        />
                      </svg>
                      <svg
                        v-else-if="origin.type === 'generated'"
                        width="11"
                        height="11"
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
                        width="11"
                        height="11"
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
                        {{ origin.doc_name || "人机交互学习" }}
                      </div>
                      <div class="origin-location">
                        {{ origin.location }}
                      </div>
                    </div>
                    <button
                      class="origin-jump"
                      :title="
                        origin.type === 'session' ? '跳转到会话' : '跳转到文档'
                      "
                      @click="
                        $router.push({
                          path:
                            origin.type === 'session' ? '/chat' : '/documents',
                          query:
                            origin.type === 'session'
                              ? { session_id: origin.source_id }
                              : { id: origin.source_id },
                        })
                      "
                    >
                      <svg
                        width="11"
                        height="11"
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
                    <blockquote>{{ origin.excerpt }}</blockquote>
                  </div>
                </div>
              </div>
            </div>

            <!-- 学习记录（有数据才显示） -->
            <div v-if="selectedNode.logs?.length" class="dp-section">
              <div class="dp-section-title">
                <svg
                  width="11"
                  height="11"
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
              <div class="study-log">
                <div
                  v-for="log in selectedNode.logs"
                  :key="log.date"
                  class="sl-item"
                >
                  <div class="sl-dot" :class="log.type" />
                  <div class="sl-content">
                    <div class="sl-text">
                      {{ log.text }}
                    </div>
                    <div class="sl-date">
                      {{ log.date }}
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <!-- /dp-body -->

          <!-- 底部操作 -->
          <div class="dp-footer">
            <button
              class="btn btn-primary btn-sm"
              style="flex: 1"
              @click="confirmAction('study')"
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
                  d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
                />
              </svg>
              继续学习
            </button>
            <button
              class="btn btn-ghost btn-sm"
              style="flex: 1"
              @click="confirmAction('quiz')"
            >
              <svg
                width="12"
                height="12"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M9 11l3 3L22 4" />
              </svg>
              出题练习
            </button>
          </div>
        </div>
      </transition>
    </div>

    <!-- 确认弹窗 -->
    <transition name="fade">
      <div
        v-if="confirmDialog.show"
        class="confirm-overlay"
        @click.self="confirmDialog.show = false"
      >
        <div class="confirm-box">
          <div class="confirm-icon">
            <svg
              v-if="confirmDialog.type === 'study'"
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path
                d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"
              />
            </svg>
            <svg
              v-else
              width="24"
              height="24"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
            </svg>
          </div>
          <div class="confirm-title">
            {{ confirmDialog.type === "study" ? "继续学习" : "出题练习" }}
          </div>
          <div class="confirm-desc">
            {{
              confirmDialog.type === "study"
                ? `即将跳转到对话页面，以「${selectedNode?.label}」为主题开始新的学习会话`
                : `即将跳转到练习页面，针对「${selectedNode?.label}」进行出题测验`
            }}
          </div>
          <div class="confirm-actions">
            <button
              class="btn btn-ghost btn-sm"
              @click="confirmDialog.show = false"
            >
              取消
            </button>
            <button class="btn btn-primary btn-sm" @click="doConfirm">
              确认
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from "vue";
import { useRouter, useRoute } from "vue-router";
import { nodeApi } from "@/api";

const router = useRouter();
const route = useRoute();
const canvasWrap = ref(null);
const svgW = ref(900);
const svgH = ref(620);
const zoom = ref(1);
const pan = ref({ x: 0, y: 0 });
const searchQuery = ref("");
const searchFocused = ref(false);
const activeFilter = ref("all");
const sortBy = ref("recent");
const viewMode = ref("graph");
const selectedNode = ref(null);
const loading = ref(false);

// ── 节点数据（从后端加载）──────────────────────────────────────
const nodes = ref([]);
const edges = ref([]);

// 后端 NodeBrief -> 图谱节点格式转换
const SUBJECT_COLORS = {
  算法: "#6366f1",
  数据结构: "#10b981",
  AI: "#a855f7",
  数学: "#f59e0b",
  英语: "#3b82f6",
};
const SUBJECT_EMOJIS = {
  算法: "🔄",
  数据结构: "🌳",
  AI: "🧠",
  数学: "📐",
  英语: "✍️",
};
const DEFAULT_COLORS = [
  "#6366f1",
  "#10b981",
  "#a855f7",
  "#f59e0b",
  "#3b82f6",
  "#ef4444",
];
const colorCache = {};
function getTagColor(tag) {
  if (!colorCache[tag]) {
    const idx = Object.keys(colorCache).length % DEFAULT_COLORS.length;
    colorCache[tag] = SUBJECT_COLORS[tag] || DEFAULT_COLORS[idx];
  }
  return colorCache[tag];
}

// 格式化最近学习时间（后端返回 UTC 时间，强制按 UTC 解析）
function formatLastStudied(lastReviewAt) {
  if (!lastReviewAt) return "从未学习";
  // 确保字符串末尾有 Z，避免被当作本地时间解析
  const str =
    lastReviewAt.endsWith("Z") || lastReviewAt.includes("+")
      ? lastReviewAt
      : lastReviewAt + "Z";
  const d = new Date(str);
  const diff = Math.floor((Date.now() - d.getTime()) / 86400000);
  if (diff < 0) return "今天"; // 数据异常（未来时间）降级显示
  if (diff === 0) return "今天";
  if (diff === 1) return "昨天";
  if (diff < 7) return `${diff}天前`;
  return `${Math.floor(diff / 7)}周前`;
}

// 计算衰减警告
// due_date 是 ISO 日期字符串（如 "2024-01-01"）
// 用 UTC 日期字符串统一比较，避免本地时区与 UTC 混用导致 ±1 天误差
function calcDecayWarning(dueDate) {
  if (!dueDate) return null;
  // Pydantic 序列化 datetime 为 "2024-01-01T00:00:00"，截取前 10 位得到纯日期
  const dueDateStr = String(dueDate).slice(0, 10);
  // 取 UTC 今天的日期字符串（YYYY-MM-DD），与后端 due_date 保持同一时区基准
  const now = new Date();
  const todayStr = `${now.getUTCFullYear()}-${String(now.getUTCMonth() + 1).padStart(2, "0")}-${String(now.getUTCDate()).padStart(2, "0")}`;
  if (dueDateStr < todayStr) {
    // 两个纯日期字符串都按 UTC 解析，相减得到精确天数
    const overdue = Math.floor(
      (Date.parse(todayStr) - Date.parse(dueDateStr)) / 86400000,
    );
    if (overdue > 7) return `已逾期 ${overdue} 天，记忆可能严重衰减`;
    return `已逾期 ${overdue} 天，建议尽快复习`;
  }
  if (dueDateStr === todayStr) return "今天到期，建议今日复习";
  return null;
}

// 通用力导向函数：对一组粒子（{x,y,r}）做斥力+向心引力迭代
// particles: Array<{ x, y, r }>  r 为该粒子的"排斥半径"
// gravity: 向原点(0,0)的引力系数（簇内用0,0为中心；簇间传入cx,cy后粒子坐标已是绝对坐标，用全局中心）
function runForceLayout(
  particles,
  {
    iterations = 150,
    repulsion = 5000,
    damping = 0.75,
    boundW = 0,
    boundH = 0,
    margin = 0,
    gravity = 0.01,
    gcx = 0,
    gcy = 0,
    radiusWeighted = false,
  } = {},
) {
  const n = particles.length;
  if (n <= 1) return;
  const vx = new Array(n).fill(0);
  const vy = new Array(n).fill(0);
  for (let iter = 0; iter < iterations; iter++) {
    const fx = new Array(n).fill(0);
    const fy = new Array(n).fill(0);
    // 节点间斥力
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        const dx = particles[i].x - particles[j].x;
        const dy = particles[i].y - particles[j].y;
        const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const minDist = particles[i].r + particles[j].r;
        if (dist < minDist * 1.1) {
          // radiusWeighted=true（簇间）时斥力乘以 minDist，半径越大斥力越强；簇内保持原始斥力
          const force = radiusWeighted
            ? (repulsion * 10) / (dist * dist)
            : repulsion / (dist * dist);
          const nx = dx / dist,
            ny = dy / dist;
          fx[i] += nx * force;
          fy[i] += ny * force;
          fx[j] -= nx * force;
          fy[j] -= ny * force;
        }
      }
    }
    // 向中心的引力（防止节点无限飘散）
    for (let i = 0; i < n; i++) {
      fx[i] += (gcx - particles[i].x) * gravity;
      fy[i] += (gcy - particles[i].y) * gravity;
    }
    for (let i = 0; i < n; i++) {
      vx[i] = (vx[i] + fx[i]) * damping;
      vy[i] = (vy[i] + fy[i]) * damping;
      particles[i].x += vx[i];
      particles[i].y += vy[i];
      if (boundW > 0)
        particles[i].x = Math.max(
          margin + particles[i].r,
          Math.min(boundW - margin - particles[i].r, particles[i].x),
        );
      if (boundH > 0)
        particles[i].y = Math.max(
          margin + particles[i].r,
          Math.min(boundH - margin - particles[i].r, particles[i].y),
        );
    }
  }
}

// 布局：连通分量识别 → 簇内力导向 → 簇作为超级节点做簇间力导向
function layoutNodes(rawNodes) {
  const W = svgW.value || 900;
  const H = svgH.value || 600;
  const cx = W / 2;
  const cy = H / 2;

  if (rawNodes.length === 0) return [];

  // ── Step1: 构建无向邻接表 ─────────────────────────────────
  const adj = {};
  for (const n of rawNodes) adj[n.id] = new Set();
  // 1a. 按 relations 连边
  for (const n of rawNodes) {
    for (const rel of n.relations || []) {
      if (adj[rel.target_node_id] !== undefined) {
        adj[n.id].add(rel.target_node_id);
        adj[rel.target_node_id].add(n.id);
      }
    }
  }
  // 1b. 同一个 tag 的节点也视为连通（星形链）
  const tagGroups = {};
  for (const n of rawNodes) {
    const tag = n.tags?.[0] || "其他";
    if (!tagGroups[tag]) tagGroups[tag] = [];
    tagGroups[tag].push(n.id);
  }
  for (const ids of Object.values(tagGroups)) {
    for (let i = 1; i < ids.length; i++) {
      adj[ids[0]].add(ids[i]);
      adj[ids[i]].add(ids[0]);
    }
  }

  // ── Step2: BFS 识别连通分量 ───────────────────────────────
  const visited = new Set();
  const components = [];
  for (const n of rawNodes) {
    if (visited.has(n.id)) continue;
    const comp = [];
    const queue = [n.id];
    visited.add(n.id);
    while (queue.length) {
      const cur = queue.shift();
      comp.push(rawNodes.find((x) => x.id === cur));
      for (const nb of adj[cur]) {
        if (!visited.has(nb)) {
          visited.add(nb);
          queue.push(nb);
        }
      }
    }
    components.push(comp);
  }
  components.sort((a, b) => b.length - a.length);

  // ── Step3: 簇内力导向布局 ─────────────────────────────────
  // ┌─────────────────── 可调参数 ───────────────────────────┐
  const NODE_R = 60; // 节点视觉半径（含掌握度环 + 标签间距），越大节点越大、簇越散
  const INIT_R_MIN_FACTOR = 3.5; // initR 最小值 = NODE_R * 此系数，越大初始圆越大
  const INIT_R_PER_NODE = 2.8; // initR 按节点数扩展系数，越大多节点簇初始越散
  const CLUSTER_ITERATIONS = 200; // 簇内力导向迭代次数，越多布局越收敛
  const CLUSTER_REPULSION = 16000; // 簇内节点间斥力，越大节点间距越大
  const CLUSTER_DAMPING = 0.7; // 阻尼系数（0~1），越小收敛越快但可能震荡
  const CLUSTER_GRAVITY = 0.04; // 向簇中心的引力，越大节点越向中心聚拢
  const BOUND_R_SINGLE = 20; // 单节点簇的包围半径额外留白
  const BOUND_R_PADDING = 100; // 多节点簇包围半径在最远节点基础上的额外留白
  // └────────────────────────────────────────────────────────┘

  // 每个簇的粒子初始排列在小圆上，再跑力导向
  const clusterLayouts = components.map((comp) => {
    const count = comp.length;
    // 初始环形半径：保证初始不完全重叠，最小值放大避免引力过度压缩
    const initR =
      count === 1
        ? 0
        : Math.max(
            NODE_R * INIT_R_MIN_FACTOR,
            (NODE_R * INIT_R_PER_NODE * count) / (2 * Math.PI),
          );
    const particles = comp.map((n, i) => ({
      id: n.id,
      r: NODE_R,
      x: initR * Math.cos((i / Math.max(count, 1)) * 2 * Math.PI - Math.PI / 2),
      y: initR * Math.sin((i / Math.max(count, 1)) * 2 * Math.PI - Math.PI / 2),
    }));
    // 单节点不需要迭代；gravity 向簇中心(0,0)聚拢，防止节点飘散
    if (count > 1)
      runForceLayout(particles, {
        iterations: CLUSTER_ITERATIONS,
        repulsion: CLUSTER_REPULSION,
        damping: CLUSTER_DAMPING,
        gravity: CLUSTER_GRAVITY,
        gcx: 0,
        gcy: 0,
      });
    // 计算簇的包围半径（最远粒子到中心的距离 + 节点半径 + 间距）
    const boundR =
      count === 1
        ? NODE_R + BOUND_R_SINGLE
        : Math.max(...particles.map((p) => Math.sqrt(p.x * p.x + p.y * p.y))) +
          NODE_R +
          BOUND_R_PADDING;
    return { comp, particles, boundR };
  });

  // ── Step4: 簇间力导向（把每个簇当成半径=boundR的超级节点）─
  // ┌─────────────────── 可调参数 ───────────────────────────┐
  const GLOBAL_INIT_R_GAP = 40; // 初始大圆半径：相邻两簇 boundR 之和再加此留白
  const GLOBAL_INIT_R_CIRC = 30; // 初始大圆半径：按周长估算时每簇间的间距
  const GLOBAL_ITERATIONS = 300; // 簇间力导向迭代次数，越多布局越收敛
  const GLOBAL_REPULSION = 80000; // 簇间斥力，越大簇与簇之间距离越大
  const GLOBAL_DAMPING = 0.65; // 阻尼系数（0~1），越小收敛越快但可能震荡
  const GLOBAL_GRAVITY = 0.07; // 向画布中心的引力，越大整体越向中心聚拢
  // └────────────────────────────────────────────────────────┘

  // 初始：均匀排列在大圆上
  const numC = clusterLayouts.length;
  const initGlobalR =
    numC === 1
      ? 0
      : Math.max(
          clusterLayouts[0].boundR +
            (clusterLayouts[1]?.boundR || 0) +
            GLOBAL_INIT_R_GAP,
          clusterLayouts.reduce(
            (s, c) => s + c.boundR * 2 + GLOBAL_INIT_R_CIRC,
            0,
          ) /
            (2 * Math.PI),
        );
  const superNodes = clusterLayouts.map((cl, ci) => ({
    x:
      cx +
      initGlobalR *
        Math.cos((ci / Math.max(numC, 1)) * 2 * Math.PI - Math.PI / 2),
    y:
      cy +
      initGlobalR *
        Math.sin((ci / Math.max(numC, 1)) * 2 * Math.PI - Math.PI / 2),
    r: cl.boundR,
  }));
  if (numC > 1) {
    runForceLayout(superNodes, {
      iterations: GLOBAL_ITERATIONS,
      repulsion: GLOBAL_REPULSION,
      damping: GLOBAL_DAMPING,
      // 不限制边界，让节点自由扩展，SVG 画布会在布局后自动撑大
      boundW: 0,
      boundH: 0,
      margin: 0,
      gravity: GLOBAL_GRAVITY,
      gcx: cx,
      gcy: cy,
      radiusWeighted: true,
    });
  } else {
    superNodes[0].x = cx;
    superNodes[0].y = cy;
  }

  // ── Step5: 合并坐标，生成最终节点列表 ────────────────────
  const result = [];
  clusterLayouts.forEach((cl, ci) => {
    const scx = superNodes[ci].x;
    const scy = superNodes[ci].y;
    cl.comp.forEach((n, ni) => {
      const p = cl.particles[ni];
      const mastery = Math.round((n.mastery_level || 0) * 100);
      result.push({
        ...n,
        label: n.title,
        subject: n.tags?.[0] || "其他",
        mastery,
        x: scx + p.x,
        y: scy + p.y,
        _scx: scx,
        _scy: scy, // 暂存簇中心，供后续计算用（不影响渲染）
        understanding: mastery,
        memoryPct: Math.min(100, Math.round((n.repetitions || 0) * 20)),
        connection: Math.min(100, (n.relations?.length || 0) * 25),
        lastStudied: formatLastStudied(n.last_review_at),
        decayWarning: calcDecayWarning(n.due_date),
        desc: n.description,
        emoji: SUBJECT_EMOJIS[n.tags?.[0]] || "💡",
        content: null,
        origins: [],
        logs: [],
      });
    });
  });

  // ── Step6: 根据节点实际范围动态扩展 SVG 画布 ─────────────
  const PADDING = 80; // 画布四周留白
  if (result.length > 0) {
    const xs = result.map((n) => n.x);
    const ys = result.map((n) => n.y);
    const minX = Math.min(...xs) - PADDING;
    const minY = Math.min(...ys) - PADDING;
    const maxX = Math.max(...xs) + PADDING;
    const maxY = Math.max(...ys) + PADDING;
    // 平移所有节点使左上角对齐到 (PADDING, PADDING)
    const offX = -minX;
    const offY = -minY;
    result.forEach((n) => {
      n.x += offX;
      n.y += offY;
    });
    // 更新 SVG 尺寸为实际内容大小（不小于视口）
    svgW.value = Math.max(svgW.value, maxX - minX);
    svgH.value = Math.max(svgH.value, maxY - minY);
  }

  return result;
}

// 从 relations 构建 edges
function buildEdges(rawNodes) {
  const edgeList = [];
  let eid = 1;
  const RELATION_TYPE_MAP = {
    prerequisite: "prereq",
    related: "related",
    extends: "extends",
    contrasts: "contrasts",
  };
  for (const node of rawNodes) {
    for (const rel of node.relations || []) {
      edgeList.push({
        id: eid++,
        source: node.id,
        target: rel.target_node_id,
        type: RELATION_TYPE_MAP[rel.relation_type] || "related",
      });
    }
  }
  return edgeList;
}

async function loadNodes() {
  loading.value = true;
  try {
    const raw = await nodeApi.getAll();
    nodes.value = layoutNodes(raw);
    edges.value = buildEdges(raw);
    // 动态更新 filters 的标签选项
    const tagSet = new Set(raw.flatMap((n) => n.tags || []));
    // 取全部 tag，不截断，让筛选器完整
    dynamicFilters.value = [...tagSet].map((t) => ({
      key: t,
      label: t,
      color: getTagColor(t),
    }));
  } catch (e) {
    console.warn("节点加载失败:", e.message);
  } finally {
    loading.value = false;
  }
}

// 点击节点时懒加载完整详情
async function loadNodeDetail(nodeId) {
  try {
    const detail = await nodeApi.getById(nodeId);
    const idx = nodes.value.findIndex((n) => n.id === nodeId);
    if (idx !== -1) {
      // 用 Object.assign 原地更新，避免引用断裂导致面板闪烁
      Object.assign(nodes.value[idx], {
        content: detail.content,
        origins: (detail.origins || []).map((o) => ({
          ...o,
          // 统一 source_type -> type，兼容模板图标
          // 后端只有 document / session 两种，模板里 generated 图标暂不使用
          type: o.source_type === "document" ? "upload" : "session",
          // 优先用后端返回的 source_title，否则降级显示截断 id
          doc_name:
            o.source_type === "document"
              ? o.source_title || `文档 ${o.source_id.slice(0, 8)}`
              : o.source_title || `会话 ${o.source_id.slice(0, 8)}`,
        })),
        // 同步更新 mastery（后端 review 后 mastery_level 可能已变化）
        mastery: Math.round(
          (detail.memory?.mastery_level ?? nodes.value[idx].mastery / 100) *
            100,
        ),
        // 从 memory 补充 repetitions（NodeBrief 没有，NodeSchema 有）
        repetitions:
          detail.memory?.repetitions ?? nodes.value[idx].repetitions ?? 0,
        last_review_at:
          detail.memory?.last_review_at ?? nodes.value[idx].last_review_at,
        due_date: detail.memory?.due_date ?? nodes.value[idx].due_date,
      });
      // 重新计算衍生字段（用 memoryPct 避免与后端 memory 对象字段名冲突）
      const n = nodes.value[idx];
      n.memoryPct = Math.min(100, Math.round((n.repetitions || 0) * 20));
      n.lastStudied = formatLastStudied(n.last_review_at);
      n.decayWarning = calcDecayWarning(n.due_date);
      // 同步 understanding（理解度 = 掌握度，mastery 更新后需一并更新）
      n.understanding = n.mastery;
      // selectedNode 指向同一对象，无需重新赋值
    }
  } catch (e) {
    console.warn("节点详情加载失败:", e.message);
  }
}

// applies 类型后端不存在，已移除；保留 contrasts/extends/prereq/related
const edgeColors = {
  prereq: "#6366f1",
  extends: "#10b981",
  contrasts: "#ef4444",
  related: "#6b7280",
};

const dynamicFilters = ref([]);

// ── Computed ────────────────────────────────────────────────────
const filteredNodes = computed(() => {
  let list = nodes.value;
  if (activeFilter.value !== "all")
    list = list.filter(
      (n) =>
        n.subject === activeFilter.value ||
        n.tags?.includes(activeFilter.value),
    );
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    list = list.filter(
      (n) =>
        n.label.toLowerCase().includes(q) ||
        n.desc?.toLowerCase().includes(q) ||
        n.tags?.some((t) => t.toLowerCase().includes(q)),
    );
  }
  return list;
});

// visibleNodes 是 filteredNodes 的别名，供模板直接使用
const visibleNodes = filteredNodes;
const visibleEdges = computed(() => {
  const ids = new Set(filteredNodes.value.map((n) => n.id));
  return edges.value.filter((e) => ids.has(e.source) && ids.has(e.target));
});

// 实际渲染的边：
// - 无选中时：只显示 prereq/extends 类型的强关系边（过滤掉大量 related 边）
// - 有选中时：显示与选中节点直接相连的所有边
const displayedEdges = computed(() => {
  const all = visibleEdges.value;
  if (selectedNode.value) {
    const sid = selectedNode.value.id;
    return all.filter((e) => e.source === sid || e.target === sid);
  }
  // 无选中：只保留强关系边，related 边太多太杂乱
  return all.filter((e) => e.type === "prereq" || e.type === "extends");
});

const sortedNodes = computed(() => {
  const list = [...filteredNodes.value];
  if (sortBy.value === "mastery-desc")
    list.sort((a, b) => b.mastery - a.mastery);
  else if (sortBy.value === "mastery-asc")
    list.sort((a, b) => a.mastery - b.mastery);
  else if (sortBy.value === "name")
    list.sort((a, b) => a.label.localeCompare(b.label));
  return list;
});

// listStats 统一用全量数据，避免节点全量/边过滤后语义不一致
const listStats = computed(() => [
  { val: nodes.value.length, label: "知识节点" },
  { val: edges.value.length, label: "关联边" },
  { val: nodes.value.filter((n) => n.mastery >= 80).length, label: "已掌握" },
  { val: nodes.value.filter((n) => n.mastery < 50).length, label: "待突破" },
]);

const masteryDist = computed(() => {
  const levels = [
    {
      label: "≥80%",
      color: "#10b981",
      count: nodes.value.filter((n) => n.mastery >= 80).length,
    },
    {
      label: "60-79%",
      color: "#f59e0b",
      count: nodes.value.filter((n) => n.mastery >= 60 && n.mastery < 80)
        .length,
    },
    {
      label: "40-59%",
      color: "#f97316",
      count: nodes.value.filter((n) => n.mastery >= 40 && n.mastery < 60)
        .length,
    },
    {
      label: "<40%",
      color: "#ef4444",
      count: nodes.value.filter((n) => n.mastery < 40).length,
    },
  ];
  const max = Math.max(...levels.map((l) => l.count), 1);
  return levels.map((l) => ({ ...l, pct: Math.round((l.count / max) * 100) }));
});

// ── Helpers ─────────────────────────────────────────────────────
function getSubjectColor(subject) {
  return getTagColor(subject);
}
function getNodeColor(node) {
  return getSubjectColor(node.subject);
}
function getNodeBg(node) {
  return getNodeColor(node) + "18";
}
function getNodeRadius(node) {
  return 16 + (node.mastery / 100) * 12;
}
function getMasteryColor(v) {
  if (v >= 80) return "#10b981";
  if (v >= 50) return "#f59e0b";
  return "#ef4444";
}
function getNode(id) {
  return nodes.value.find((n) => n.id === id);
}
function isConnected(edge, nodeId) {
  return edge.source === nodeId || edge.target === nodeId;
}
function isConnected2(nodeId, selectedId) {
  if (nodeId === selectedId) return true;
  return edges.value.some(
    (e) =>
      (e.source === selectedId && e.target === nodeId) ||
      (e.target === selectedId && e.source === nodeId),
  );
}
function getRelated(nodeId) {
  const ids = new Set();
  edges.value.forEach((e) => {
    if (e.source === nodeId) ids.add(e.target);
    if (e.target === nodeId) ids.add(e.source);
  });
  // 不受 activeFilter 限制，显示所有关联节点（点击可跨分组跳转）
  return nodes.value.filter((n) => ids.has(n.id));
}
function getNodeDims(node) {
  return [
    {
      label: "理解度",
      val: node.understanding + "%",
      color: getMasteryColor(node.understanding),
    },
    {
      label: "记忆度",
      val: node.memoryPct + "%",
      color: getMasteryColor(node.memoryPct),
    },
    {
      label: "连接度",
      val: node.connection + "%",
      color: getMasteryColor(node.connection),
    },
  ];
}
function selectNode(node) {
  if (selectedNode.value?.id === node.id) {
    selectedNode.value = null;
    return;
  }
  selectedNode.value = node;
  // 如果还没加载详情，懒加载
  if (!node.content) loadNodeDetail(node.id);
}
function studyNode() {
  router.push({ path: "/chat", query: { topic: selectedNode.value?.label } });
}

// ── 确认弹窗 ────────────────────────────────────────────────────
const confirmDialog = ref({ show: false, type: "" }); // type: 'study' | 'quiz'
function confirmAction(type) {
  confirmDialog.value = { show: true, type };
}
function doConfirm() {
  confirmDialog.value.show = false;
  if (confirmDialog.value.type === "study") {
    studyNode();
  } else {
    router.push({ path: "/quiz", query: { nodeId: selectedNode.value?.id } });
  }
}

// ── 图谱交互 ────────────────────────────────────────────────────
let isPanning = false,
  panStart = { x: 0, y: 0 };
let draggingNode = null,
  dragStart = { x: 0, y: 0 };

function onSvgMousedown(e) {
  if (e.button !== 0) return;
  isPanning = true;
  panStart = { x: e.clientX - pan.value.x, y: e.clientY - pan.value.y };
}
function onNodeMousedown(e, node) {
  draggingNode = node;
  dragStart = {
    x: (e.clientX - pan.value.x) / zoom.value - node.x,
    y: (e.clientY - pan.value.y) / zoom.value - node.y,
  };
  e.stopPropagation();
}
function onSvgMousemove(e) {
  if (draggingNode) {
    draggingNode.x = (e.clientX - pan.value.x) / zoom.value - dragStart.x;
    draggingNode.y = (e.clientY - pan.value.y) / zoom.value - dragStart.y;
    return;
  }
  if (isPanning)
    pan.value = { x: e.clientX - panStart.x, y: e.clientY - panStart.y };
}
function onSvgMouseup() {
  isPanning = false;
  draggingNode = null;
}
function onWheel(e) {
  const delta = e.deltaY > 0 ? -0.1 : 0.1;
  const newZoom = Math.max(0.2, Math.min(3, zoom.value + delta));
  // 以鼠标位置为缩放中心，调整 pan 避免画面漂移
  const rect = canvasWrap.value?.getBoundingClientRect();
  if (rect) {
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    pan.value = {
      x: mx - (mx - pan.value.x) * (newZoom / zoom.value),
      y: my - (my - pan.value.y) * (newZoom / zoom.value),
    };
  }
  zoom.value = newZoom;
}
function resetView() {
  zoom.value = 1;
  pan.value = { x: 0, y: 0 };
}

// ResizeObserver 实例，组件卸载时需要 disconnect 防内存泄漏
let _resizeObserver = null;
onUnmounted(() => {
  _resizeObserver?.disconnect();
  _resizeObserver = null;
});

// 用真实画布尺寸重新布局节点
function relayoutWithRealSize() {
  if (!canvasWrap.value || canvasWrap.value.clientWidth === 0) return;
  // 以视口尺寸作为布局中心基准，SVG 会在 layoutNodes 内根据实际内容自动扩展
  svgW.value = canvasWrap.value.clientWidth;
  svgH.value = canvasWrap.value.clientHeight;
  const raw = nodes.value.map((n) => ({
    id: n.id,
    title: n.label,
    description: n.desc,
    tags: n.tags,
    relations: n.relations,
    mastery_level: n.mastery / 100,
    repetitions: n.repetitions,
    due_date: n.due_date,
    last_review_at: n.last_review_at,
  }));
  const relayouted = layoutNodes(raw);
  // layoutNodes 内已更新 svgW/svgH，这里只需同步节点坐标
  const posMap = Object.fromEntries(
    relayouted.map((n) => [n.id, { x: n.x, y: n.y }]),
  );
  nodes.value.forEach((n) => {
    if (posMap[n.id]) {
      n.x = posMap[n.id].x;
      n.y = posMap[n.id].y;
    }
  });
}

onMounted(async () => {
  await loadNodes();

  // 如果路由带了 nodeId 参数，自动选中该节点
  const targetNodeId = route.query.nodeId;
  if (targetNodeId) {
    const target = nodes.value.find((n) => n.id === targetNodeId);
    if (target) {
      selectNode(target);
    }
  }

  if (viewMode.value !== "graph") return;
  // nextTick 确保 DOM 已渲染，再用 ResizeObserver 等待画布有实际尺寸
  await nextTick();
  if (canvasWrap.value && canvasWrap.value.clientWidth > 0) {
    relayoutWithRealSize();
  } else {
    // 画布尺寸还未就绪，用 ResizeObserver 等第一次有尺寸时触发
    _resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        if (entry.contentRect.width > 0) {
          _resizeObserver?.disconnect();
          _resizeObserver = null;
          relayoutWithRealSize();
          break;
        }
      }
    });
    if (canvasWrap.value) _resizeObserver.observe(canvasWrap.value);
  }
});
</script>

<style scoped>
.graph-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── 工具栏 ───────────────────────────────────────────────────── */
.graph-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 20px;
  height: 52px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-panel);
  flex-shrink: 0;
}
.gt-left {
  display: flex;
  align-items: center;
  gap: 12px;
}
.gt-center {
  flex: 1;
  max-width: 320px;
}
.gt-right {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

/* 视图切换 */
.view-switch {
  display: flex;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 2px;
  gap: 2px;
}
.vs-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: calc(var(--radius-md) - 2px);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
  transition: var(--transition);
}
.vs-btn:hover {
  color: var(--text-primary);
}
.vs-btn.active {
  background: var(--bg-card);
  color: var(--text-primary);
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.15);
}

.graph-stats {
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}

/* 加载 & 空状态 */
.graph-loading,
.graph-empty {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 12px;
  color: var(--text-dim);
  font-size: 13px;
  pointer-events: none;
}
.graph-empty {
  pointer-events: auto;
}
.ge-icon {
  font-size: 40px;
}
.ge-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-secondary);
}
.ge-desc {
  font-size: 12px;
  color: var(--text-dim);
  text-align: center;
  max-width: 260px;
  line-height: 1.6;
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.gl-spinner {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  border: 2px solid var(--border);
  border-top-color: var(--brand-light);
  animation: spin 0.8s linear infinite;
}

/* 搜索框 */
.search-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  transition: var(--transition);
  color: var(--text-muted);
  width: 100%;
}
.search-bar.focused {
  border-color: var(--border-active);
  background: var(--bg-card);
}
.search-bar input {
  flex: 1;
  background: none;
  border: none;
  outline: none;
  font-size: 13px;
  color: var(--text-primary);
}
.search-bar input::placeholder {
  color: var(--text-dim);
}

/* 筛选 */
.filter-group {
  display: flex;
  gap: 2px;
}
.filter-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  transition: var(--transition);
}
.filter-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.filter-btn.active {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: rgba(99, 102, 241, 0.2);
}
.filter-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
}

/* 排序/控制 */
.sort-select {
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
}
.graph-controls {
  display: flex;
  align-items: center;
  gap: 6px;
}
.ctrl-btn {
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  color: var(--text-secondary);
  transition: var(--transition);
}
.ctrl-btn:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
}
.zoom-val {
  font-size: 11px;
  color: var(--text-dim);
  min-width: 34px;
  text-align: center;
}

/* ── 主体 ─────────────────────────────────────────────────────── */
.graph-body {
  flex: 1;
  display: flex;
  overflow: hidden;
  position: relative; /* loading/empty 的 absolute 定位基准 */
}

/* ── 图谱画布 ─────────────────────────────────────────────────── */
.graph-canvas-wrap {
  flex: 1;
  position: relative;
  overflow: hidden;
  cursor: grab;
}
.graph-canvas-wrap:active {
  cursor: grabbing;
}
.graph-svg {
  width: 100%;
  height: 100%;
  display: block;
}

.node-group {
  cursor: pointer;
  transition: opacity 0.2s;
}
.node-group.dimmed {
  opacity: 0.15;
}
.node-group.selected {
  filter: drop-shadow(0 0 8px rgba(99, 102, 241, 0.5));
}

/* 图例 */
.graph-legend {
  position: absolute;
  bottom: 20px;
  left: 20px;
  display: flex;
  flex-direction: column;
  gap: 5px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 10px 14px;
  backdrop-filter: blur(8px);
}
.legend-item {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  color: var(--text-secondary);
}
.legend-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

/* ── 列表视图 ─────────────────────────────────────────────────── */
.list-view {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 20px 24px;
  gap: 16px;
  overflow-y: auto;
  /* 有详情面板时自然被挤压；无面板时占满全宽，不设 max-width */
  min-width: 0;
}

/* 统计条 */
.list-stats {
  display: flex;
  align-items: center;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 12px 20px;
  flex-shrink: 0;
}
.ls-item {
  flex: 1;
  text-align: center;
}
.ls-val {
  display: block;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.5px;
}
.ls-label {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 2px;
  display: block;
}
.ls-divider {
  width: 1px;
  height: 28px;
  background: var(--border);
  margin: 0 12px;
}
.ls-mastery {
  display: flex;
  align-items: center;
  gap: 10px;
}
.lsm-label {
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}
.lsm-bars {
  display: flex;
  align-items: flex-end;
  gap: 4px;
  height: 32px;
}
.lsm-bar {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  width: 20px;
}
.lsm-fill {
  width: 100%;
  border-radius: 2px;
  min-height: 4px;
  transition: height 0.4s;
}
.lsm-count {
  font-size: 9px;
  color: var(--text-dim);
}

/* 节点列表 */
.node-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.node-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition);
}
.node-card:hover {
  border-color: var(--border-hover);
  background: var(--bg-card);
}
.node-card.active {
  border-color: var(--brand);
  background: var(--brand-dim);
}
.nc-top {
  display: flex;
  align-items: center;
  gap: 12px;
}
.nc-emoji-wrap {
  width: 38px;
  height: 38px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.nc-emoji {
  font-size: 18px;
}
.nc-main {
  flex: 1;
  min-width: 0;
}
.nc-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 3px;
}
.nc-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-dim);
}
.nc-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}
.nc-sep {
  color: var(--text-dim);
}
.nc-mastery-val {
  font-size: 14px;
  font-weight: 700;
  flex-shrink: 0;
}
.nc-bottom {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.nc-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.nc-tag {
  padding: 2px 7px;
  border-radius: var(--radius-full);
  font-size: 10px;
  font-weight: 500;
  background: var(--bg-hover);
  color: var(--text-muted);
  border: 1px solid var(--border);
}
.list-empty {
  padding: 40px;
  text-align: center;
  color: var(--text-dim);
  font-size: 13px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

/* ── 右侧详情面板（共用）─────────────────────────────────────── */
.detail-panel {
  width: 32%;
  min-width: 320px;
  max-width: 520px;
  background: var(--bg-panel);
  border-left: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  overflow: hidden;
}

.panel-slide-enter-active,
.panel-slide-leave-active {
  transition: all 0.22s cubic-bezier(0.4, 0, 0.2, 1);
}
.panel-slide-enter-from,
.panel-slide-leave-to {
  transform: translateX(40px);
  opacity: 0;
}

.dp-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.dp-emoji {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}
.dp-title-wrap {
  flex: 1;
  min-width: 0;
}
.dp-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  letter-spacing: -0.3px;
  margin-bottom: 5px;
}
.dp-badges {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.dp-close {
  width: 26px;
  height: 26px;
  border-radius: var(--radius-sm);
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--text-dim);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
  flex-shrink: 0;
}
.dp-close:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.dp-body {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 掌握度 */
.dp-mastery {
  display: flex;
  align-items: center;
  gap: 14px;
}
.dpm-circle {
  flex-shrink: 0;
}
.dpm-dims {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dpmd-item {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.dpmd-top {
  display: flex;
  justify-content: space-between;
}
.dpmd-label {
  font-size: 11px;
  color: var(--text-secondary);
}
.dpmd-val {
  font-size: 11px;
  font-weight: 600;
}

/* 衰减提醒 */
.dp-decay {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  background: var(--yellow-dim);
  color: var(--yellow);
  font-size: 12px;
  line-height: 1.5;
}

/* section */
.dp-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.dp-section-title {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.dp-desc {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin: 0;
}

/* key points */
.key-points {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 0;
  margin: 0;
  list-style: none;
}
.kp-item {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.kp-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand-light);
  flex-shrink: 0;
  margin-top: 6px;
}

/* examples */
.example-block {
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  overflow: hidden;
}
.ex-title {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-secondary);
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
}
.ex-code {
  margin: 0;
  padding: 8px 10px;
  font-size: 10.5px;
  line-height: 1.6;
  color: var(--text-primary);
  font-family: "SF Mono", "Fira Code", monospace;
  overflow-x: auto;
  background: rgba(0, 0, 0, 0.18);
}
[data-theme="light"] .ex-code {
  background: #f0f0f4;
}
.ex-text {
  font-size: 12px;
  color: var(--text-secondary);
  padding: 8px 10px;
  margin: 0;
  line-height: 1.6;
}

/* mistakes */
.mistake-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 0;
  margin: 0;
  list-style: none;
}
.ml-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.ml-item svg {
  color: var(--red);
  flex-shrink: 0;
  margin-top: 3px;
}

/* related chips */
.related-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
.related-chip {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: var(--radius-full);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  font-size: 11px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: var(--transition);
}
.related-chip:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}
.rc-mastery {
  font-size: 10px;
  font-weight: 600;
}

/* 详情面板响应式：窄屏时限制最小宽度 */
@media (max-width: 1100px) {
  .detail-panel {
    width: 40%;
    min-width: 280px;
  }
}
@media (max-width: 800px) {
  .detail-panel {
    width: 100%;
    min-width: unset;
    border-left: none;
    border-top: 1px solid var(--border);
    max-height: 50vh;
  }
}

/* 来源定位 */
.origins-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
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
  gap: 8px;
  padding: 8px 10px;
}
.origin-icon {
  width: 24px;
  height: 24px;
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
  font-size: 11px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.origin-location {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 1px;
}
.origin-jump {
  width: 22px;
  height: 22px;
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
.origin-jump:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}
.origin-excerpt {
  border-top: 1px solid var(--border);
  padding: 7px 10px;
}
.origin-excerpt blockquote {
  margin: 0;
  font-size: 11px;
  color: var(--text-secondary);
  font-style: italic;
  line-height: 1.6;
  border-left: 2px solid var(--brand-dim);
  padding-left: 7px;
}

/* study log */
.study-log {
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.sl-item {
  display: flex;
  gap: 8px;
  padding: 5px 0;
}
.sl-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 4px;
  flex-shrink: 0;
}
.sl-dot.study {
  background: var(--brand-light);
}
.sl-dot.quiz {
  background: var(--green);
}
.sl-dot.review {
  background: var(--yellow);
}
.sl-content {
  flex: 1;
}
.sl-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.sl-date {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 2px;
}

/* 底部操作 */
.dp-footer {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}

/* 进度条（公用） */
.progress-bar {
  height: 4px;
  background: var(--bg-hover);
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  border-radius: 2px;
  transition: width 0.4s ease;
}

/* 确认弹窗 */
.confirm-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.confirm-box {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 28px 24px 20px;
  width: 320px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 10px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.25);
}
.confirm-icon {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: rgba(99, 102, 241, 0.12);
  color: var(--accent);
  display: flex;
  align-items: center;
  justify-content: center;
}
.confirm-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-primary);
}
.confirm-desc {
  font-size: 13px;
  color: var(--text-secondary);
  text-align: center;
  line-height: 1.6;
}
.confirm-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
  width: 100%;
}
.confirm-actions .btn {
  flex: 1;
  justify-content: center;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.18s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}
</style>
