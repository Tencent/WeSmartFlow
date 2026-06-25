<template>
  <div class="page-wrapper">
    <!-- Page header -->
    <div class="page-header">
      <div>
        <h1 class="page-title">文档管理</h1>
        <p class="page-subtitle">
          上传原始材料，Agent 自动提取知识节点，构建你的知识图谱
        </p>
      </div>
      <div class="header-right">
        <div class="search-bar">
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
          <input v-model="searchQuery" placeholder="搜索文档..." />
        </div>
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
          上传文档
        </button>
      </div>
    </div>

    <!-- Stats bar -->
    <div class="stats-bar">
      <div class="stat-item">
        <span class="stat-val">{{ docs.length }}</span>
        <span class="stat-label">文档总数</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-val" style="color: var(--green)">{{
          processedCount
        }}</span>
        <span class="stat-label">已处理</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-val" style="color: var(--yellow)">{{
          processingCount
        }}</span>
        <span class="stat-label">处理中</span>
      </div>
      <div class="stat-divider" />
      <div class="stat-item">
        <span class="stat-val text-gradient">{{ totalExtractedNodes }}</span>
        <span class="stat-label">提取节点数</span>
      </div>
    </div>

    <!-- Filter tabs -->
    <div class="filter-tabs">
      <button
        v-for="tab in filterTabs"
        :key="tab.value"
        class="filter-tab"
        :class="{ active: activeFilter === tab.value }"
        @click="activeFilter = tab.value"
      >
        {{ tab.label }}
        <span class="tab-count">{{ tab.count }}</span>
      </button>
    </div>

    <!-- Document list -->
    <div class="doc-list">
      <div
        v-for="doc in filteredDocs"
        :key="doc.id"
        class="doc-card"
        :class="{ selected: selectedDoc?.id === doc.id }"
        @click="selectDoc(doc)"
      >
        <!-- File icon -->
        <div class="doc-icon" :class="`type-${doc.renderType}`">
          <!-- pdf 家族 -->
          <svg
            v-if="doc.renderType === 'pdf'"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <path d="M9 13h6M9 17h3" />
          </svg>
          <!-- html_card 家族 -->
          <svg
            v-else-if="doc.renderType === 'html_card'"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <rect x="3" y="4" width="18" height="16" rx="2" />
            <line x1="3" y1="9" x2="21" y2="9" />
            <line x1="7" y1="13" x2="15" y2="13" />
            <line x1="7" y1="16" x2="12" y2="16" />
          </svg>
          <!-- viz 家族 -->
          <svg
            v-else-if="doc.renderType === 'viz'"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
          </svg>
          <!-- markdown 家族 -->
          <svg
            v-else-if="doc.renderType === 'markdown'"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
            <polyline points="8 13 10 15 8 17" />
            <line x1="12" y1="13" x2="14" y2="13" />
          </svg>
          <!-- json 家族 -->
          <svg
            v-else-if="doc.renderType === 'json'"
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <path d="M8 3H5a2 2 0 00-2 2v4M8 21H5a2 2 0 01-2-2v-4" />
            <path d="M16 3h3a2 2 0 012 2v4M16 21h3a2 2 0 002-2v-4" />
          </svg>
          <!-- text 其他家族（fallback） -->
          <svg
            v-else
            width="18"
            height="18"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="1.8"
          >
            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </div>

        <!-- Info -->
        <div class="doc-info">
          <div class="doc-name">
            {{ doc.name }}
          </div>
          <div class="doc-meta">
            <span class="source-tag" :class="doc.source">
              {{ doc.source === "uploaded" ? "📤 上传" : "🤖 AI生成" }}
            </span>
            <span class="type-tag">{{ doc.typeLabel }}</span>
            <span class="doc-size">{{ formatSize(doc.size_bytes) }}</span>
            <span class="doc-date">{{ formatDate(doc.uploaded_at) }}</span>
          </div>
        </div>

        <!-- Status -->
        <div class="doc-status">
          <div class="status-badge" :class="doc.status">
            <span class="status-dot" />
            {{ statusLabels[doc.status] }}
          </div>
          <div v-if="doc.status === 'processed'" class="extracted-info">
            提取 {{ doc.extracted_node_ids?.length || 0 }} 个节点
          </div>
          <div v-if="doc.status === 'processing'" class="processing-anim">
            <span /><span /><span />
          </div>
        </div>

        <!-- Actions -->
        <div class="doc-actions">
          <button
            class="icon-btn"
            title="查看内容"
            @click.stop="viewContent(doc)"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z" />
              <circle cx="12" cy="12" r="3" />
            </svg>
          </button>
          <button
            class="icon-btn"
            title="查看节点"
            @click.stop="viewNodes(doc)"
          >
            <svg
              width="14"
              height="14"
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
          </button>
          <button
            class="icon-btn"
            title="下载"
            @click.stop="downloadDocument(doc)"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </button>
          <button
            v-if="doc.source === 'uploaded'"
            class="icon-btn danger"
            title="删除"
            @click.stop="deleteDoc(doc)"
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <polyline points="3 6 5 6 21 6" />
              <path
                d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a1 1 0 011-1h4a1 1 0 011 1v2"
              />
            </svg>
          </button>
        </div>
      </div>

      <!-- Empty state -->
      <div v-if="filteredDocs.length === 0" class="empty-state">
        <div class="empty-icon">📁</div>
        <div class="empty-title">暂无文档</div>
        <div class="empty-desc">
          上传 PDF、Markdown 或其他学习材料<br />Agent
          会自动提取知识节点，充实你的知识图谱
        </div>
        <button class="btn btn-primary" @click="showUpload = true">
          上传第一份文档
        </button>
      </div>
    </div>

    <!-- Upload modal -->
    <div
      v-if="showUpload"
      class="modal-overlay"
      @click.self="showUpload = false"
    >
      <div class="modal">
        <div class="modal-header">
          <h3>上传文档</h3>
          <button class="icon-btn" @click="showUpload = false">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <!-- Drop zone -->
          <div
            class="drop-zone"
            :class="{ dragging: isDragging }"
            @dragover.prevent="isDragging = true"
            @dragleave="isDragging = false"
            @drop.prevent="handleDrop"
            @click="triggerFileInput"
          >
            <input
              ref="fileInput"
              type="file"
              accept=".pdf,.md,.txt,.docx"
              multiple
              style="display: none"
              @change="handleFileSelect"
            />
            <div class="drop-icon">
              <svg
                width="32"
                height="32"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
              >
                <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
            </div>
            <div class="drop-title">拖放文件到此处</div>
            <div class="drop-desc">支持 PDF、Markdown、TXT、DOCX</div>
            <div class="drop-or">或者</div>
            <button class="btn btn-ghost" @click.stop="triggerFileInput">
              选择文件
            </button>
          </div>

          <!-- Selected files -->
          <div v-if="pendingFiles.length > 0" class="selected-files">
            <div v-for="(f, i) in pendingFiles" :key="i" class="pending-file">
              <span class="pf-name">{{ f.name }}</span>
              <span class="pf-size">{{ formatSize(f.size) }}</span>
              <button class="icon-btn" @click="removeFile(i)">
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>

          <!-- Note -->
          <div class="upload-note">
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            上传后 Agent
            将自动分析文档内容，提取知识节点并构建到你的知识图谱中。
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showUpload = false">
            取消
          </button>
          <button
            class="btn btn-primary"
            :disabled="pendingFiles.length === 0"
            @click="uploadFiles"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            上传 {{ pendingFiles.length > 0 ? `(${pendingFiles.length})` : "" }}
          </button>
        </div>
      </div>
    </div>

    <!-- Document content modal -->
    <div
      v-if="showContentModal && selectedDoc"
      class="modal-overlay"
      @click.self="showContentModal = false"
    >
      <div
        class="modal"
        style="
          max-width: 800px;
          max-height: 80vh;
          display: flex;
          flex-direction: column;
        "
      >
        <div class="modal-header">
          <h3>{{ selectedDoc.name }} - 文档内容</h3>
          <button class="icon-btn" @click="showContentModal = false">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body" style="overflow-y: auto; flex: 1">
          <!-- 加载中 -->
          <div v-if="loadingContent" class="loading-content">
            <div class="loading-spinner" />
            <div>正在加载文档内容...</div>
          </div>

          <!-- HTML 知识卡片（html_card）：复用 HtmlCard 组件 -->
          <div
            v-else-if="selectedDoc?.renderType === 'html_card'"
            class="doc-preview-html"
          >
            <HtmlCard :file-id="selectedDoc.id" />
          </div>

          <!-- Viz 交互可视化：复用 VizCard 沙盒渲染 -->
          <div
            v-else-if="selectedDoc?.renderType === 'viz'"
            class="doc-preview-viz"
          >
            <VizCard :viz-id="selectedDoc.id" :title="selectedDoc.name" />
          </div>

          <!-- PDF 家族（pdf / pdf_card / chapter_pdf）：pdf.js 渲染 -->
          <div
            v-else-if="selectedDoc?.renderType === 'pdf'"
            class="doc-preview-pdf"
          >
            <div v-if="pdfState.totalPages > 0" class="pdf-viewer">
              <div class="pdf-toolbar">
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="pdfState.currentPage <= 1"
                  @click="pdfPrevPage"
                >
                  ← 上一页
                </button>
                <span class="pdf-page-info"
                  >{{ pdfState.currentPage }} / {{ pdfState.totalPages }}</span
                >
                <button
                  class="btn btn-ghost btn-sm"
                  :disabled="pdfState.currentPage >= pdfState.totalPages"
                  @click="pdfNextPage"
                >
                  下一页 →
                </button>
              </div>
              <div class="pdf-canvas-wrap">
                <canvas ref="pdfCanvasRef" class="pdf-canvas" />
              </div>
            </div>
            <div v-else class="no-content">PDF 加载失败</div>
          </div>

          <!-- Markdown 家族（md / md_note / course_plan / chapter_overview / chapter_exercises） -->
          <div
            v-else-if="selectedDoc?.renderType === 'markdown'"
            class="doc-preview-md"
          >
            <div
              v-if="rawText"
              class="markdown-body"
              v-html="renderMd(rawText)"
            ></div>
            <div
              v-else-if="documentContent"
              class="markdown-body"
              v-html="renderMd(documentContent.content || '')"
            ></div>
            <div v-else class="no-content">无法加载文档内容</div>
          </div>

          <!-- JSON 家族（course_outline / chapter_audio / chapter_notes） -->
          <div
            v-else-if="selectedDoc?.renderType === 'json'"
            class="doc-preview-json"
          >
            <pre v-if="rawText" class="json-block">{{ rawText }}</pre>
            <div v-else class="no-content">无法加载 JSON 内容</div>
          </div>

          <!-- 其他类型（txt / docx 等）：分段纯文本展示 -->
          <div v-else-if="documentContent" class="document-content">
            <div
              v-for="segment in documentContent.segments"
              :key="segment.segment_id"
              class="content-segment"
            >
              <h4 class="segment-title">
                {{ segment.title }}
              </h4>
              <div class="segment-content">
                {{ segment.content }}
              </div>
            </div>
          </div>

          <!-- 兜底：无内容 -->
          <div v-else class="no-content">无法加载文档内容</div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showContentModal = false">
            关闭
          </button>
          <button
            v-if="selectedDoc.status === 'failed'"
            class="btn btn-warning"
            @click="reprocessDocument(selectedDoc)"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M23 4v6h-6" />
              <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
            </svg>
            重新处理
          </button>
          <button class="btn btn-secondary" @click="openAddNodeModal">
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
            添加节点
          </button>
          <button
            class="btn btn-primary"
            @click="downloadDocument(selectedDoc)"
          >
            <svg
              width="13"
              height="13"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
            下载原文档
          </button>
        </div>
      </div>
    </div>

    <!-- Add node modal -->
    <div
      v-if="showAddNodeModal && selectedDoc"
      class="modal-overlay"
      @click.self="showAddNodeModal = false"
    >
      <div class="modal" style="max-width: 600px">
        <div class="modal-header">
          <div>
            <h3>为文档添加节点</h3>
            <p class="modal-subtitle">选择要关联到文档的现有知识节点</p>
          </div>
          <button class="icon-btn" @click="showAddNodeModal = false">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
        <div class="modal-body">
          <!-- Search bar -->
          <div class="search-container">
            <div class="search-bar">
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                v-model="nodeSearchQuery"
                placeholder="搜索节点标题或描述..."
                class="search-input"
                @input="filterNodes"
              />
            </div>
            <div class="search-stats">
              <span class="stats-text"
                >{{ filteredAvailableNodes.length }} 个可用节点</span
              >
            </div>
          </div>

          <!-- Node list -->
          <div class="node-list-container">
            <div v-if="filteredAvailableNodes.length > 0" class="node-list">
              <div
                v-for="node in filteredAvailableNodes"
                :key="node.id"
                class="node-card"
                :class="{ selected: selectedNodeId === node.id }"
                @click="selectedNodeId = node.id"
              >
                <div class="node-header">
                  <div class="node-emoji">💡</div>
                  <div class="node-info">
                    <div class="node-title">
                      {{ node.title }}
                    </div>
                    <div class="node-description">
                      {{ node.description || "暂无描述" }}
                    </div>
                  </div>
                  <div
                    class="node-mastery"
                    :style="{ color: getMasteryColor(node.mastery_level) }"
                  >
                    {{ Math.round((node.mastery_level || 0) * 100) }}%
                  </div>
                </div>
                <div v-if="node.tags && node.tags.length > 0" class="node-tags">
                  <span
                    v-for="tag in node.tags.slice(0, 3)"
                    :key="tag"
                    class="tag"
                  >
                    {{ tag }}
                  </span>
                  <span v-if="node.tags.length > 3" class="tag-more"
                    >+{{ node.tags.length - 3 }}</span
                  >
                </div>
                <div
                  v-if="node.relations && node.relations.length > 0"
                  class="node-relations"
                >
                  <span class="relations-count"
                    >关联 {{ node.relations.length }} 个节点</span
                  >
                </div>
              </div>
            </div>
            <div v-else class="empty-nodes">
              <div class="empty-icon">🔍</div>
              <div class="empty-title">未找到匹配的节点</div>
              <div class="empty-desc">
                {{
                  nodeSearchQuery
                    ? "尝试使用其他关键词搜索"
                    : "当前没有可用的节点"
                }}
              </div>
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button class="btn btn-ghost" @click="showAddNodeModal = false">
            取消
          </button>
          <button
            class="btn btn-primary"
            :disabled="!selectedNodeId"
            @click="addNodeToDocument"
          >
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
            添加节点
          </button>
        </div>
      </div>
    </div>

    <!-- Node preview panel -->
    <div v-if="showNodePanel && selectedDoc" class="node-panel">
      <div class="panel-header">
        <div>
          <div class="panel-title">
            {{ selectedDoc.name }}
          </div>
          <div class="panel-sub">
            提取了 {{ selectedDoc.extracted_node_ids?.length || 0 }} 个知识节点
          </div>
        </div>
        <button class="icon-btn" @click="showNodePanel = false">
          <svg
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
          >
            <line x1="18" y1="6" x2="6" y2="18" />
            <line x1="6" y1="6" x2="18" y2="18" />
          </svg>
        </button>
      </div>
      <div class="panel-nodes">
        <div
          v-for="node in previewNodes"
          :key="node.id"
          class="extracted-node"
          @click="
            $router.push({ path: '/knowledge', query: { nodeId: node.id } })
          "
        >
          <span class="en-emoji">{{ node.emoji }}</span>
          <div class="en-info">
            <div class="en-title">
              {{ node.title }}
            </div>
            <div class="en-subject">
              {{ node.subject }}
            </div>
          </div>
          <div
            class="en-mastery"
            :style="{ color: masteryColor(node.mastery.overall) }"
          >
            {{ node.mastery.overall }}%
          </div>
        </div>
      </div>
      <div class="panel-actions">
        <button
          class="btn btn-ghost"
          style="width: 100%"
          @click="
            $router.push({
              path: '/graph',
              query: { nodeId: selectedDoc?.extracted_node_ids?.[0] },
            })
          "
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
          在知识图谱中查看
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from "vue";
import { documentApi, nodeApi } from "@/api";
import { api, BASE_URL, authHeaders } from "@/api/base.js";
import { HtmlCard } from "@/components/HtmlCard";
import { VizCard } from "@/components/VizCard";
import { renderMd } from "@/composables/useMarkdown.js";
import * as pdfjsLib from "pdfjs-dist/webpack.mjs";

const searchQuery = ref("");
const activeFilter = ref("all");
const showUpload = ref(false);
const showNodePanel = ref(false);
const showContentModal = ref(false);
const showAddNodeModal = ref(false);
const selectedDoc = ref(null);
const isDragging = ref(false);
const pendingFiles = ref([]);
const fileInput = ref(null);
const uploading = ref(false);
const documentContent = ref(null);
const rawText = ref("");
const loadingContent = ref(false);
const selectedNodeId = ref("");
const availableNodes = ref([]);
const nodeSearchQuery = ref("");

// ── 数据（从后端加载）──────────────────────────────────────────
const docs = ref([]);

// 后端 file_type → 前端渲染家族的映射
//   pdf       —— 用 pdf.js 渲染
//   html_card —— 用 HtmlCard 组件渲染（迭代码调 /raw）
//   viz       —— 用 VizCard 沙盒渲染
//   markdown  —— 拉 raw 文本后用 marked 渲染
//   json      —— 拉 raw 后以样式化 JSON 收边展示
//   text      —— fallback，走分段抽取
const RENDER_TYPE_MAP = {
  // 原始 / 上传
  pdf: "pdf",
  md: "markdown",
  markdown: "markdown",
  txt: "text",
  docx: "text",
  // AI 生成 — 对话式
  html_card: "html_card",
  viz: "viz",
  pdf_card: "pdf",
  md_note: "markdown",
  // AI 生成 — 沉浸式
  course_outline: "json",
  course_plan: "markdown",
  chapter_overview: "markdown",
  chapter_pdf: "pdf",
  chapter_exercises: "markdown",
  chapter_audio: "json",
  chapter_notes: "json",
};

// file_type 人读标签
const FILE_TYPE_LABEL = {
  pdf: "PDF",
  md: "Markdown",
  markdown: "Markdown",
  txt: "纯文本",
  docx: "Word 文档",
  html_card: "HTML 知识卡片",
  viz: "交互可视化",
  pdf_card: "PDF 知识卡片",
  md_note: "Markdown 笔记",
  course_outline: "课程大纲",
  course_plan: "学习建议",
  chapter_overview: "章节预习手册",
  chapter_pdf: "章节讲义",
  chapter_exercises: "章节习题",
  chapter_audio: "章节音频包",
  chapter_notes: "章节讲解稿",
};

// 后端字段 → 模板字段的适配
function adaptDoc(raw) {
  const fileType = raw.file_type || "pdf";
  const renderType = RENDER_TYPE_MAP[fileType] || "text";
  return {
    ...raw,
    name: raw.title + (raw.file_type ? `.${raw.file_type}` : ""),
    type: fileType, // 保留原始后端 file_type
    renderType, // 渲染家族
    typeLabel: FILE_TYPE_LABEL[fileType] || fileType.toUpperCase(),
    size_bytes: raw.file_size || 0,
    status: raw.status === "ready" ? "processed" : raw.status,
    extracted_node_ids: raw.node_ids || [],
    uploaded_at: raw.created_at,
  };
}

async function loadDocs() {
  try {
    const raw = await documentApi.getAll();
    docs.value = raw.map(adaptDoc);
  } catch (e) {
    console.warn("文档列表加载失败:", e.message);
  }
}

onMounted(loadDocs);

// previewNodes：点击"查看节点"时加载
const previewNodes = ref([]);
async function viewNodes(doc) {
  selectedDoc.value = doc;
  showNodePanel.value = true;
  if (doc.extracted_node_ids?.length) {
    try {
      // 批量加载节点简要信息
      const all = await nodeApi.getAll();
      const idSet = new Set(doc.extracted_node_ids);
      previewNodes.value = all
        .filter((n) => idSet.has(n.id))
        .map((n) => ({
          id: n.id,
          title: n.title,
          emoji: "💡",
          subject: n.tags?.[0] || "其他",
          mastery: { overall: Math.round((n.mastery_level || 0) * 100) },
        }));
    } catch (e) {
      console.warn("加载节点列表失败:", e.message);
    }
  } else {
    previewNodes.value = [];
  }
}

// 查看文档内容
const pdfCanvasRef = ref(null);
const pdfState = ref({ currentPage: 1, totalPages: 0 });
let pdfDoc = null;

async function viewContent(doc) {
  selectedDoc.value = doc;
  showContentModal.value = true;
  loadingContent.value = true;
  documentContent.value = null;
  rawText.value = "";
  pdfDoc = null;
  pdfState.value = { currentPage: 1, totalPages: 0 };

  const renderType = doc.renderType;

  // html_card / viz 不需要加载文本内容，直接交给组件
  if (renderType === "html_card" || renderType === "viz") {
    loadingContent.value = false;
    return;
  }

  // pdf 家族：用 pdf.js 渲染
  if (renderType === "pdf") {
    try {
      const pdfUrl = `${BASE_URL}/api/documents/${doc.id}/raw`;
      const pdfDocument = await pdfjsLib.getDocument({
        url: pdfUrl,
        httpHeaders: authHeaders(),
        cMapUrl: "https://unpkg.com/pdfjs-dist@5.6.205/cmaps/",
        cMapPacked: true,
      }).promise;
      pdfDoc = pdfDocument;
      pdfState.value = { currentPage: 1, totalPages: pdfDocument.numPages };
      loadingContent.value = false;
      await nextTick();
      await renderPdfPage(1);
    } catch (e) {
      console.warn("PDF 加载失败:", e.message);
      loadingContent.value = false;
    }
    return;
  }

  // markdown / json 家族：直接拉 raw 原始文本
  if (renderType === "markdown" || renderType === "json") {
    try {
      const res = await api.getRaw(`/api/documents/${doc.id}/raw`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      let text = await res.text();
      // JSON 尝试美化
      if (renderType === "json") {
        try {
          text = JSON.stringify(JSON.parse(text), null, 2);
        } catch (e) {
          // 保持原文
          console.warn("JSON 格式化失败:", e.message);
        }
      }
      rawText.value = text;
    } catch (e) {
      console.warn("加载原始文本失败:", e.message);
    } finally {
      loadingContent.value = false;
    }
    return;
  }

  // 其他（txt / docx / fallback）：走分段接口
  try {
    const content = await documentApi.getContent(doc.id);
    documentContent.value = content;
  } catch (e) {
    console.warn("加载文档内容失败:", e.message);
  } finally {
    loadingContent.value = false;
  }
}

async function renderPdfPage(pageNum) {
  if (!pdfDoc || !pdfCanvasRef.value) return;
  const page = await pdfDoc.getPage(pageNum);
  const scale = 1.5;
  const viewport = page.getViewport({ scale });
  const canvas = pdfCanvasRef.value;
  const ctx = canvas.getContext("2d");
  canvas.width = viewport.width;
  canvas.height = viewport.height;
  await page.render({ canvasContext: ctx, viewport }).promise;
}

function pdfPrevPage() {
  if (pdfState.value.currentPage <= 1) return;
  pdfState.value.currentPage--;
  renderPdfPage(pdfState.value.currentPage);
}

function pdfNextPage() {
  if (pdfState.value.currentPage >= pdfState.value.totalPages) return;
  pdfState.value.currentPage++;
  renderPdfPage(pdfState.value.currentPage);
}

// 下载文档（带鉴权）
async function downloadDocument(doc) {
  try {
    const res = await api.getRaw(`/api/documents/${doc.id}/raw?download=1`);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = doc.name || `document_${doc.id}`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (e) {
    console.warn("下载文档失败:", e.message);
  }
}

// 重新处理文档
async function reprocessDocument(doc) {
  try {
    await documentApi.extract(doc.id);
    // 重新加载文档列表
    await loadDocs();
    showContentModal.value = false;
    // 可以添加一个提示消息
  } catch (e) {
    console.warn("重新处理失败:", e.message);
  }
}

const statusLabels = {
  uploaded: "等待处理",
  pending: "等待处理",
  processing: "处理中",
  processed: "已完成",
  ready: "已完成",
  failed: "处理失败",
};

const filterTabs = computed(() => [
  { label: "全部", value: "all", count: docs.value.length },
  {
    label: "用户上传",
    value: "uploaded",
    count: docs.value.filter((d) => d.source === "uploaded").length,
  },
  {
    label: "AI 生成",
    value: "generated",
    count: docs.value.filter((d) => d.source === "generated").length,
  },
  {
    label: "处理中",
    value: "processing",
    count: docs.value.filter((d) => d.status === "processing").length,
  },
]);

const filteredDocs = computed(() => {
  let result = docs.value;
  if (activeFilter.value === "uploaded")
    result = result.filter((d) => d.source === "uploaded");
  else if (activeFilter.value === "generated")
    result = result.filter((d) => d.source === "generated");
  else if (activeFilter.value === "processing")
    result = result.filter((d) => d.status === "processing");
  if (searchQuery.value) {
    const q = searchQuery.value.toLowerCase();
    result = result.filter((d) => d.name.toLowerCase().includes(q));
  }
  return result;
});

const processedCount = computed(
  () => docs.value.filter((d) => d.status === "processed").length,
);
const processingCount = computed(
  () => docs.value.filter((d) => d.status === "processing").length,
);
const totalExtractedNodes = computed(() => {
  const ids = new Set();
  docs.value.forEach((d) => d.extracted_node_ids?.forEach((id) => ids.add(id)));
  return ids.size;
});

function selectDoc(doc) {
  selectedDoc.value = doc;
  showNodePanel.value = false;
}

async function deleteDoc(doc) {
  try {
    await documentApi.delete(doc.id);
    docs.value = docs.value.filter((d) => d.id !== doc.id);
    if (selectedDoc.value?.id === doc.id) selectedDoc.value = null;
  } catch (e) {
    console.warn("删除失败:", e.message);
  }
}

function triggerFileInput() {
  fileInput.value?.click();
}

function handleFileSelect(e) {
  const files = Array.from(e.target.files);
  pendingFiles.value = [...pendingFiles.value, ...files];
}

function handleDrop(e) {
  isDragging.value = false;
  const files = Array.from(e.dataTransfer.files);
  pendingFiles.value = [...pendingFiles.value, ...files];
}

function removeFile(index) {
  pendingFiles.value.splice(index, 1);
}

async function uploadFiles() {
  if (!pendingFiles.value.length) return;
  uploading.value = true;
  try {
    for (const file of pendingFiles.value) {
      const doc = await documentApi.upload(file);
      docs.value.unshift(adaptDoc(doc));
    }
  } catch (e) {
    console.warn("上传失败:", e.message);
  } finally {
    uploading.value = false;
    pendingFiles.value = [];
    showUpload.value = false;
  }
}

function formatSize(bytes) {
  if (!bytes) return "--";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(iso) {
  if (!iso) return "--";
  const d = new Date(iso);
  const now = new Date();
  const diff = Math.floor((now - d) / 1000 / 60);
  if (diff < 60) return `${diff}分钟前`;
  if (diff < 1440) return `${Math.floor(diff / 60)}小时前`;
  return `${Math.floor(diff / 1440)}天前`;
}

function masteryColor(v) {
  if (v >= 70) return "var(--green)";
  if (v >= 40) return "var(--yellow)";
  return "var(--red)";
}

// 过滤后的可用节点
const filteredAvailableNodes = computed(() => {
  if (!nodeSearchQuery.value) {
    return availableNodes.value;
  }
  const query = nodeSearchQuery.value.toLowerCase();
  return availableNodes.value.filter(
    (node) =>
      node.title.toLowerCase().includes(query) ||
      (node.description && node.description.toLowerCase().includes(query)) ||
      (node.tags && node.tags.some((tag) => tag.toLowerCase().includes(query))),
  );
});

// 获取掌握程度颜色
function getMasteryColor(masteryLevel) {
  if (masteryLevel >= 0.8) return "var(--green)";
  if (masteryLevel >= 0.5) return "var(--yellow)";
  return "var(--red)";
}

// 过滤节点
function filterNodes() {
  // 计算属性会自动更新，这里只需要清空选择
  selectedNodeId.value = "";
}

// 打开添加节点模态框
async function openAddNodeModal() {
  showAddNodeModal.value = true;
  selectedNodeId.value = "";
  nodeSearchQuery.value = "";

  try {
    // 加载所有可用节点
    const allNodes = await nodeApi.getAll();
    // 过滤掉已经关联到当前文档的节点
    const currentDocNodeIds = new Set(
      selectedDoc.value?.extracted_node_ids || [],
    );
    availableNodes.value = allNodes.filter(
      (node) => !currentDocNodeIds.has(node.id),
    );
  } catch (e) {
    console.warn("加载节点列表失败:", e.message);
    availableNodes.value = [];
  }
}

async function addNodeToDocument() {
  if (!selectedDoc.value || !selectedNodeId.value) return;
  try {
    await documentApi.addNode(selectedDoc.value.id, selectedNodeId.value);
    // 重新加载文档列表
    await loadDocs();
    showAddNodeModal.value = false;
    // 可以添加一个提示消息
  } catch (e) {
    console.warn("添加节点失败:", e.message);
  }
}
</script>

<style scoped>
@import "@/styles/page-list.css";

/* ===== DocumentsView 独有样式 ===== */

/* 补充：用户在页内的空态需要比公共版更大的 padding */
.empty-state {
  padding: 64px 32px;
  gap: 12px;
}
.empty-state .empty-title {
  font-size: 16px;
}

/* Filter tabs */
.filter-tabs {
  display: flex;
  gap: 4px;
}
.filter-tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 14px;
  border-radius: var(--radius-sm);
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  background: transparent;
  border: 1px solid transparent;
  cursor: pointer;
  transition: var(--transition);
}
.filter-tab:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}
.filter-tab.active {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: rgba(99, 102, 241, 0.2);
}
.tab-count {
  padding: 1px 6px;
  border-radius: var(--radius-full);
  background: var(--bg-hover);
  font-size: 10px;
  color: var(--text-muted);
}
.filter-tab.active .tab-count {
  background: rgba(99, 102, 241, 0.15);
  color: var(--brand-light);
}

/* Doc list */
.doc-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.doc-card {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 14px 16px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: var(--transition);
}
.doc-card:hover {
  border-color: var(--border-hover);
  background: var(--bg-card);
}
.doc-card.selected {
  border-color: var(--brand);
  background: var(--brand-dim);
}

/* File icon */
.doc-icon {
  width: 40px;
  height: 40px;
  border-radius: var(--radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.doc-icon.type-pdf {
  background: rgba(239, 68, 68, 0.1);
  color: var(--red);
}
.doc-icon.type-markdown {
  background: rgba(99, 102, 241, 0.1);
  color: var(--brand-light);
}
.doc-icon.type-html_card {
  background: rgba(34, 197, 94, 0.1);
  color: var(--green);
}
.doc-icon.type-viz {
  background: rgba(168, 85, 247, 0.12);
  color: #c084fc;
}
.doc-icon.type-json {
  background: rgba(234, 179, 8, 0.1);
  color: var(--yellow);
}
.doc-icon.type-text {
  background: var(--bg-hover);
  color: var(--text-muted);
}

/* 类型标签（人读 file_type） */
.type-tag {
  display: inline-block;
  padding: 1px 7px;
  border-radius: var(--radius-sm);
  font-size: 11px;
  color: var(--text-secondary);
  background: var(--bg-hover);
  white-space: nowrap;
}

/* JSON 预览块 */
.doc-preview-json {
  height: 100%;
}
.doc-preview-json .json-block {
  margin: 0;
  padding: 14px 16px;
  font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
  font-size: 12.5px;
  line-height: 1.55;
  color: var(--text-primary);
  background: var(--bg-hover);
  border-radius: var(--radius-md);
  white-space: pre-wrap;
  word-break: break-all;
  overflow: auto;
  max-height: calc(80vh - 180px);
}

/* Doc info */
.doc-info {
  flex: 1;
  min-width: 0;
}
.doc-name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  margin-bottom: 5px;
}
.doc-meta {
  display: flex;
  align-items: center;
  gap: 10px;
}
.source-tag {
  font-size: 10px;
  font-weight: 500;
  padding: 2px 7px;
  border-radius: var(--radius-full);
}
.source-tag.uploaded {
  background: var(--blue-dim);
  color: var(--blue);
}
.source-tag.generated {
  background: var(--brand-dim);
  color: var(--brand-light);
}
.doc-size,
.doc-date {
  font-size: 11px;
  color: var(--text-dim);
}

/* Status */
.doc-status {
  flex-shrink: 0;
  text-align: right;
}
.status-badge {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  font-weight: 500;
  padding: 3px 8px;
  border-radius: var(--radius-full);
}
.status-badge.processed {
  background: var(--green-dim);
  color: var(--green);
}
.status-badge.processing {
  background: var(--yellow-dim);
  color: var(--yellow);
}
.status-badge.uploaded {
  background: var(--bg-hover);
  color: var(--text-muted);
}
.status-badge.failed {
  background: var(--red-dim);
  color: var(--red);
}
.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
}
.status-badge.processing .status-dot {
  animation: pulse 1.2s ease infinite;
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.3;
  }
}

.extracted-info {
  font-size: 10px;
  color: var(--text-dim);
  margin-top: 3px;
  text-align: right;
}

.processing-anim {
  display: flex;
  gap: 3px;
  justify-content: flex-end;
  margin-top: 4px;
}
.processing-anim span {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--yellow);
  animation: bounce 1s ease infinite;
}
.processing-anim span:nth-child(2) {
  animation-delay: 0.15s;
}
.processing-anim span:nth-child(3) {
  animation-delay: 0.3s;
}
@keyframes bounce {
  0%,
  100% {
    transform: translateY(0);
  }
  50% {
    transform: translateY(-4px);
  }
}

/* Actions */
.doc-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  opacity: 0;
  transition: var(--transition);
}
.doc-card:hover .doc-actions {
  opacity: 1;
}

.icon-btn {
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
.icon-btn:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}
.icon-btn.danger:hover {
  background: var(--red-dim);
  color: var(--red);
  border-color: rgba(220, 38, 38, 0.3);
}

/* Empty state 已合并至公共样式及顶部补充 */

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal {
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  width: 480px;
  box-shadow: var(--shadow-lg);
  overflow: hidden;
}
.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 18px 20px 14px;
  border-bottom: 1px solid var(--border);
}
.modal-header h3 {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
}
.modal-body {
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
}

/* Drop zone */
.drop-zone {
  border: 2px dashed var(--border);
  border-radius: var(--radius-lg);
  padding: 36px 24px;
  text-align: center;
  cursor: pointer;
  transition: var(--transition);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.drop-zone:hover,
.drop-zone.dragging {
  border-color: var(--brand);
  background: var(--brand-dim);
}
.drop-icon {
  color: var(--text-dim);
  margin-bottom: 4px;
}
.drop-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}
.drop-desc {
  font-size: 12px;
  color: var(--text-muted);
}
.drop-or {
  font-size: 11px;
  color: var(--text-dim);
  margin: 4px 0;
}

/* Selected files */
.selected-files {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.pending-file {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
}
.pf-name {
  flex: 1;
  font-size: 12px;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.pf-size {
  font-size: 11px;
  color: var(--text-dim);
  flex-shrink: 0;
}

.upload-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  background: var(--brand-dim);
  border: 1px solid rgba(99, 102, 241, 0.15);
  border-radius: var(--radius-sm);
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}

/* Node panel */
.node-panel {
  position: fixed;
  right: 24px;
  top: 50%;
  transform: translateY(-50%);
  width: 280px;
  background: var(--bg-panel);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl);
  box-shadow: var(--shadow-lg);
  overflow: hidden;
  z-index: 100;
}
.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px;
  border-bottom: 1px solid var(--border);
}
.panel-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 180px;
}
.panel-sub {
  font-size: 11px;
  color: var(--text-dim);
  margin-top: 2px;
}
.panel-nodes {
  padding: 10px;
  max-height: 320px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.extracted-node {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition);
}
.extracted-node:hover {
  background: var(--bg-hover);
}
.en-emoji {
  font-size: 18px;
  flex-shrink: 0;
}
.en-info {
  flex: 1;
  min-width: 0;
}
.en-title {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
}
.en-subject {
  font-size: 10px;
  color: var(--text-dim);
}
.en-mastery {
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.panel-actions {
  padding: 10px;
  border-top: 1px solid var(--border);
}

/* Document content styles */
.document-content {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* HTML 卡片预览 */
.doc-preview-html {
  width: 100%;
  height: 60vh;
  position: relative;
}

/* Viz 可视化预览 */
.doc-preview-viz {
  width: 100%;
  height: 60vh;
  border-radius: var(--radius-md);
  overflow: hidden;
}

/* PDF 预览 */
.doc-preview-pdf {
  width: 100%;
}
.pdf-viewer {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.pdf-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  position: sticky;
  top: 0;
  background: var(--bg-card);
  z-index: 1;
  width: 100%;
  justify-content: center;
}
.pdf-page-info {
  font-size: 13px;
  color: var(--text-secondary);
  min-width: 60px;
  text-align: center;
}
.pdf-canvas-wrap {
  width: 100%;
  display: flex;
  justify-content: center;
  overflow: auto;
}
.pdf-canvas {
  max-width: 100%;
  height: auto;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  border-radius: 4px;
}

/* Markdown 预览 */
.doc-preview-md {
  padding: 16px;
}
.markdown-body {
  font-size: 14px;
  line-height: 1.7;
  color: var(--text-primary);
}
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin-top: 1.2em;
  margin-bottom: 0.6em;
  font-weight: 600;
}
.markdown-body :deep(p) {
  margin-bottom: 0.8em;
}
.markdown-body :deep(code) {
  background: var(--bg-hover);
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 0.9em;
}
.markdown-body :deep(pre) {
  background: var(--bg-hover);
  padding: 12px 16px;
  border-radius: var(--radius-md);
  overflow-x: auto;
  margin-bottom: 1em;
}
.markdown-body :deep(pre code) {
  background: none;
  padding: 0;
}
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  padding-left: 1.5em;
  margin-bottom: 0.8em;
}
.markdown-body :deep(blockquote) {
  border-left: 3px solid var(--brand);
  padding-left: 12px;
  color: var(--text-secondary);
  margin: 0.8em 0;
}
.markdown-body :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin-bottom: 1em;
}
.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid var(--border);
  padding: 8px 12px;
  text-align: left;
}
.markdown-body :deep(th) {
  background: var(--bg-hover);
  font-weight: 600;
}
.content-segment {
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  padding: 16px;
}
.segment-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.segment-content {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  white-space: pre-wrap;
}

.loading-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 40px;
  color: var(--text-dim);
}
.loading-spinner {
  width: 24px;
  height: 24px;
  border: 2px solid var(--border);
  border-top: 2px solid var(--brand);
  border-radius: 50%;
  animation: spin 1s linear infinite;
}
@keyframes spin {
  0% {
    transform: rotate(0deg);
  }
  100% {
    transform: rotate(360deg);
  }
}

.no-content {
  text-align: center;
  padding: 40px;
  color: var(--text-dim);
  font-size: 14px;
}

.btn-warning {
  background: var(--yellow-dim);
  color: var(--yellow);
  border: 1px solid rgba(245, 158, 11, 0.2);
}
.btn-warning:hover {
  background: var(--yellow);
  color: white;
  border-color: var(--yellow);
}

/* Add node modal styles */
.search-container {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}

/* 节点弹窗里的 search-bar 需要填充宽度，而非固定 180px */
.search-container .search-bar {
  flex: 1;
  padding: 8px 12px;
  border-radius: var(--radius-md);
}
.search-container .search-bar input {
  width: 100%;
}

.search-input {
  background: none;
  border: none;
  outline: none;
  font-size: 13px;
  color: var(--text-primary);
  width: 100%;
}

.search-input::placeholder {
  color: var(--text-dim);
}

.search-stats {
  flex-shrink: 0;
}

.stats-text {
  font-size: 12px;
  color: var(--text-dim);
  padding: 4px 8px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
}

.node-list-container {
  max-height: 400px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  background: var(--bg-panel);
}

.node-list {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--border);
}

.node-card {
  background: var(--bg-panel);
  padding: 16px;
  cursor: pointer;
  transition: var(--transition);
  border: 2px solid transparent;
}

.node-card:hover {
  background: var(--bg-card);
  border-color: var(--border-hover);
}

.node-card.selected {
  background: var(--brand-dim);
  border-color: var(--brand);
}

.node-header {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 8px;
}

.node-emoji {
  font-size: 20px;
  flex-shrink: 0;
  margin-top: 2px;
}

.node-info {
  flex: 1;
  min-width: 0;
}

.node-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
  line-height: 1.3;
}

.node-description {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.4;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.node-mastery {
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
  padding: 2px 6px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
}

.node-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.tag {
  font-size: 10px;
  padding: 2px 6px;
  background: var(--bg-hover);
  color: var(--text-muted);
  border-radius: var(--radius-sm);
}

.tag-more {
  font-size: 10px;
  color: var(--text-dim);
  padding: 2px 4px;
}

.node-relations {
  font-size: 11px;
  color: var(--text-dim);
}

.relations-count {
  padding: 2px 6px;
  background: var(--bg-hover);
  border-radius: var(--radius-sm);
}

.empty-nodes {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 40px 20px;
  text-align: center;
}

/* 节点弹窗空态中的 icon/title/desc：由于这里的字号比公共版稍小，在此局部收紧 */
.empty-nodes .empty-icon {
  font-size: 32px;
  margin-bottom: 8px;
}

.empty-nodes .empty-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  margin-bottom: 4px;
}

.empty-nodes .empty-desc {
  font-size: 12px;
  color: var(--text-dim);
}
</style>
