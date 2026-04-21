<template>
  <div class="chat-layout">
    <!-- ══════ 状态1：输入主题 ══════ -->
    <transition name="fade">
      <div v-if="phase === 'idle'" class="topic-entry">
        <div class="te-bg-grid" />
        <div class="te-bg-glow te-bg-glow-1" />
        <div class="te-bg-glow te-bg-glow-2" />

        <!-- 飘散的推荐主题云朵 -->
        <div class="te-clouds" aria-hidden="true">
          <button
            v-for="c in clouds"
            :key="c.text"
            class="te-cloud"
            :class="[`te-cloud-${c.size}`, { active: topicInput === c.text }]"
            :style="c.style"
            @click="topicInput = c.text"
          >
            <span class="te-cloud-emoji">{{ c.emoji }}</span>
            <span class="te-cloud-text">{{ c.text }}</span>
          </button>
        </div>

        <div class="te-container">
          <!-- 顶部标题 -->
          <header class="te-head">
            <div class="te-tag">
              <span class="te-dot" />
              A Learning Companion · Just For You
            </div>
            <h1 class="te-title">
              这一刻，<br />
              <span class="te-title-grad">世界安静下来，只为你的学习。</span>
            </h1>
            <p class="te-sub">
              在这里，没有铺天盖地的课程推送，没有被算法喂养的干扰。<br />
              只有一位懂你的
              Agent，陪你把一个主题，<em>真正学懂、学深、学透</em>。
            </p>
            <p class="te-sub te-sub-2">
              告诉它，你心里那个一直想搞明白的东西 —— 它会用尽全力，只为你学会。
            </p>
          </header>

          <!-- 输入框 -->
          <div
            class="te-input-wrap"
            :class="{ focused: topicFocused, filled: topicInput.trim() }"
          >
            <div class="te-input-ico">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <path d="M12 2a5 5 0 0 1 5 5c0 2-1 3.5-2.5 5S12 15 12 17" />
                <circle cx="12" cy="20" r="1" fill="currentColor" />
              </svg>
            </div>
            <input
              ref="topicInputEl"
              v-model="topicInput"
              class="te-input"
              placeholder="此刻，你最想学的是什么？"
              autofocus
              @keydown.enter="startLearning"
              @focus="topicFocused = true"
              @blur="topicFocused = false"
            />
            <div v-if="!topicInput.trim()" class="te-input-hint">
              <span>✨</span> 或从周围的灵感中，拾取一个
            </div>
            <div v-else class="te-input-hint ok">
              <span>💫</span> 选择一种陪伴方式 ↓
            </div>
          </div>

          <!-- 两种模式 -->
          <div class="te-modes">
            <!-- 人机交互 -->
            <button
              class="te-mode te-mode-a"
              :class="{ ready: topicInput.trim() }"
              :disabled="!topicInput.trim()"
              @click="startLearning"
            >
              <div class="te-mode-icon">🤝</div>
              <div class="te-mode-body">
                <div class="te-mode-title">
                  与我对话
                  <span class="te-mode-tag">你来主导</span>
                </div>
                <div class="te-mode-desc">
                  像一场促膝长谈，你来发问，我来回应。<br />
                  一起把这个主题，聊到你真正"懂了"为止。
                </div>
                <ul class="te-mode-feats">
                  <li>💬 自由的节奏，不被任何人催促</li>
                  <li>🧩 所思所想，自动凝结成卡片</li>
                  <li>🗺️ 一点一点，拼出你专属的知识地图</li>
                </ul>
              </div>
              <div class="te-mode-cta">
                开启这场对话
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                >
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </div>
            </button>

            <!-- AI 主导 -->
            <button
              class="te-mode te-mode-b"
              :class="{ ready: topicInput.trim() }"
              :disabled="!topicInput.trim()"
              @click="startImmersive"
            >
              <div class="te-mode-icon">🤖</div>
              <div class="te-mode-body">
                <div class="te-mode-title">
                  交给我吧
                  <span class="te-mode-tag hot">一心一意</span>
                </div>
                <div class="te-mode-desc">
                  让我为你铺好整条路。<br />
                  从第一页讲义，到最后一道习题，我把一切准备到最好，只等你来。
                </div>
                <ul class="te-mode-feats">
                  <li>📚 完整大纲，由浅入深</li>
                  <li>🎧 讲义、PDF、语音，一一奉上</li>
                  <li>✍️ 习题与答案，陪你走到最后</li>
                </ul>
              </div>
              <div class="te-mode-cta alt">
                让我为你启程
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2.5"
                >
                  <polyline points="9 18 15 12 9 6" />
                </svg>
              </div>
            </button>
          </div>

          <div class="te-foot">
            <span>🌙 无论夜多深，有我陪你一起。</span>
          </div>
        </div>
      </div>
    </transition>

    <!-- ══════ 状态2+3：学习中（左右分栏） ══════ -->
    <transition name="fade">
      <div v-if="phase !== 'idle'" class="learn-wrap">
        <!-- 左侧展示区 -->
        <div class="slide-panel">
          <!-- 工具栏 -->
          <div class="slide-toolbar">
            <div class="st-left">
              <button
                class="back-btn"
                title="重新选择主题"
                @click="resetToIdle"
              >
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <polyline points="15 18 9 12 15 6" />
                </svg>
              </button>
              <div class="st-topic-badge">
                <span class="st-topic-icon">{{
                  learningMode === "immersive" ? "🤖" : "🎓"
                }}</span>
                <span class="st-topic-name">{{ currentTopic }}</span>
              </div>
              <!-- 人机交互模式 badge -->
              <template v-if="learningMode === 'chat'">
                <span v-if="phase === 'generating'" class="badge badge-brand">
                  <span class="gen-pulse" /> 连接中
                </span>
                <span v-else-if="pdfCards.length > 0" class="badge badge-green">
                  {{ pdfCards.length }} 张卡片
                </span>
              </template>
              <!-- AI主导模式 badge -->
              <template v-else>
                <span v-if="imGenerating" class="badge badge-brand">
                  <span class="gen-pulse" />
                  {{ imStatusMessage || "生成中" }}
                </span>
                <span v-else-if="imCompleted" class="badge badge-green"
                  >✅ 全部完成</span
                >
                <span
                  v-else-if="imChapters.length > 0"
                  class="badge badge-green"
                  >{{ imChapters.length }} 章</span
                >
              </template>
            </div>
            <div class="st-right">
              <!-- 人机交互模式：卡片导航 + 导出 -->
              <template v-if="learningMode === 'chat'">
                <div v-if="pdfCards.length > 1" class="st-nav">
                  <button
                    class="nav-btn"
                    :disabled="currentPdfIndex === 0"
                    @click="selectCard(currentPdfIndex - 1)"
                  >
                    <svg
                      width="13"
                      height="13"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <polyline points="15 18 9 12 15 6" />
                    </svg>
                  </button>
                  <span class="slide-counter"
                    >{{ currentPdfIndex + 1 }} / {{ pdfCards.length }}</span
                  >
                  <button
                    class="nav-btn"
                    :disabled="currentPdfIndex === pdfCards.length - 1"
                    @click="selectCard(currentPdfIndex + 1)"
                  >
                    <svg
                      width="13"
                      height="13"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2"
                    >
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </button>
                </div>
                <button
                  v-if="pdfCards.length > 0"
                  class="export-btn"
                  :disabled="isExporting"
                  @click="exportSlides"
                >
                  <svg
                    v-if="!isExporting"
                    width="13"
                    height="13"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                  >
                    <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
                    <polyline points="7 10 12 15 17 10" />
                    <line x1="12" y1="15" x2="12" y2="3" />
                  </svg>
                  <svg
                    v-else
                    width="13"
                    height="13"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2"
                    class="spin-icon"
                  >
                    <path d="M21 12a9 9 0 11-6.219-8.56" />
                  </svg>
                  {{ isExporting ? "合并中..." : "导出全部 PDF" }}
                </button>
              </template>
            </div>
          </div>

          <!-- AI主导模式：阶段进度条 -->
          <div
            v-if="learningMode === 'immersive' && imGenerating"
            class="im-progress-wrap"
          >
            <div class="im-progress-bar">
              <div
                class="im-progress-fill"
                :style="{ width: imProgress + '%' }"
              />
            </div>
            <div class="im-stage-indicators">
              <div
                v-for="s in imStages"
                :key="s.key"
                class="im-stage-item"
                :class="{
                  active: imCurrentStage === s.key,
                  done: isImStageComplete(s.key),
                }"
              >
                <span class="im-stage-icon">{{ s.icon }}</span>
                <span class="im-stage-name">{{ s.name }}</span>
              </div>
            </div>
          </div>

          <!-- 卡片舞台 -->
          <div class="slide-stage">
            <!-- ═══ 人机交互模式内容 ═══ -->
            <template v-if="learningMode === 'chat'">
              <!-- 连接中骨架 -->
              <div v-if="phase === 'generating'" class="outline-generating">
                <div class="og-header">
                  <div class="og-spinner">
                    <div class="agent-avatar" style="width: 44px; height: 44px">
                      <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="white"
                        stroke-width="2"
                      >
                        <path d="M12 2a10 10 0 100 20A10 10 0 0012 2z" />
                        <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
                        <line x1="12" y1="17" x2="12.01" y2="17" />
                      </svg>
                    </div>
                    <div class="og-ring" />
                  </div>
                  <div>
                    <div class="og-title">正在连接「{{ currentTopic }}」</div>
                    <div class="og-sub">正在创建学习会话，请稍候...</div>
                  </div>
                </div>
                <div class="gen-progress-bar">
                  <div
                    class="gen-progress-fill"
                    :style="{ width: genProgress + '%' }"
                  />
                </div>
              </div>
              <!-- 无卡片时的空状态 -->
              <div
                v-else-if="pdfCards.length === 0 && phase === 'learning'"
                class="no-card-hint"
              >
                <div class="nch-icon">📄</div>
                <div class="nch-title">暂无知识卡片</div>
                <div class="nch-desc">
                  在右侧对话中让 Agent 生成卡片，例如：<br />「帮我生成一张关于{{
                    currentTopic
                  }}的知识卡片」
                </div>
              </div>
              <!-- PDF 主展示区 -->
              <div v-if="pdfCards.length > 0" class="pdf-main-view">
                <canvas ref="pdfMainCanvas" class="pdf-main-canvas" />
                <div v-if="currentCardPages > 0" class="pdf-page-nav">
                  <button
                    class="ppn-btn"
                    :disabled="currentPageIndex === 0"
                    @click="gotoPage(currentPageIndex - 1)"
                  >
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                    >
                      <polyline points="15 18 9 12 15 6" />
                    </svg>
                  </button>
                  <span class="ppn-label"
                    >{{ currentPageIndex + 1 }} / {{ currentCardPages }}</span
                  >
                  <button
                    class="ppn-btn"
                    :disabled="currentPageIndex === currentCardPages - 1"
                    @click="gotoPage(currentPageIndex + 1)"
                  >
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                    >
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </button>
                  <button
                    v-if="cardAudioUrl"
                    class="ppn-btn im-audio-btn"
                    :class="{ playing: cardIsPlaying }"
                    @click="playCardAudio"
                  >
                    {{ cardIsPlaying ? "⏸" : "🔊" }}
                  </button>
                </div>
              </div>
            </template>

            <!-- ═══ AI主导模式内容 ═══ -->
            <template v-else>
              <!-- 生成中 + 无章节：全屏进度 -->
              <div
                v-if="imChapters.length === 0 && imGenerating"
                class="im-generating"
              >
                <div class="im-gen-icon">
                  {{ imStageIcon }}
                </div>
                <div class="im-gen-title">正在生成课件</div>
                <div class="im-gen-topic">
                  {{ currentTopic }}
                </div>
                <div class="im-gen-msg">
                  {{ imStatusMessage }}
                </div>
              </div>
              <!-- 无章节 + 未生成 -->
              <div
                v-else-if="imChapters.length === 0 && !imGenerating"
                class="no-card-hint"
              >
                <div class="nch-icon">📚</div>
                <div class="nch-title">等待课件生成...</div>
              </div>
              <!-- 有章节：PDF 渲染 -->
              <div v-if="imChapters.length > 0" class="pdf-main-view">
                <canvas ref="imPdfCanvas" class="pdf-main-canvas" />
                <div v-if="imCurrentChapter" class="pdf-page-nav">
                  <button
                    class="ppn-btn"
                    :disabled="imCurrentPage <= 1"
                    @click="imGotoPage(imCurrentPage - 1)"
                  >
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                    >
                      <polyline points="15 18 9 12 15 6" />
                    </svg>
                  </button>
                  <span class="ppn-label"
                    >{{ imCurrentPage }} / {{ imTotalPages }}</span
                  >
                  <button
                    class="ppn-btn"
                    :disabled="imCurrentPage >= imTotalPages"
                    @click="imGotoPage(imCurrentPage + 1)"
                  >
                    <svg
                      width="12"
                      height="12"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="currentColor"
                      stroke-width="2.5"
                    >
                      <polyline points="9 18 15 12 9 6" />
                    </svg>
                  </button>
                  <button
                    v-if="imCurrentAudioUrl"
                    class="ppn-btn im-audio-btn"
                    :class="{ playing: imIsPlaying }"
                    @click="imPlayAudio"
                  >
                    {{ imIsPlaying ? "⏸" : "🔊" }}
                  </button>
                </div>
              </div>
            </template>
          </div>

          <!-- 人机交互模式：缩略图行 -->
          <div
            v-if="
              learningMode === 'chat' &&
              pdfCards.length > 0 &&
              currentCardPages > 0
            "
            class="thumb-strip"
          >
            <div class="ts-scroll">
              <div
                v-for="(thumb, pi) in pdfCards[currentPdfIndex]?.thumbs || []"
                :key="pi"
                class="ts-thumb"
                :class="{ active: pi === currentPageIndex }"
                @click="gotoPage(pi)"
              >
                <canvas
                  :ref="(el) => setThumbCanvas(el, pi)"
                  class="ts-canvas"
                />
                <span class="ts-page">{{ pi + 1 }}</span>
              </div>
              <div
                v-if="(pdfCards[currentPdfIndex]?.thumbs || []).length === 0"
                class="ts-thumb ts-loading"
              >
                <div class="ts-spinner" />
              </div>
            </div>
          </div>

          <!-- 人机交互模式：底部选卡栏 -->
          <div
            v-if="learningMode === 'chat' && pdfCards.length > 0"
            class="card-selector"
          >
            <div class="cs-scroll">
              <div
                v-for="(card, i) in pdfCards"
                :key="card.fileId"
                class="cs-item"
                :class="{ active: i === currentPdfIndex }"
                @click="selectCard(i)"
              >
                <span class="cs-dot" />
                <span class="cs-label">{{ card.title }}</span>
                <span v-if="card.thumbs" class="cs-pages"
                  >{{ card.thumbs.length }}页</span
                >
              </div>
            </div>
          </div>

          <!-- AI主导模式：章节选择条 -->
          <div
            v-if="learningMode === 'immersive' && imChapters.length > 0"
            class="card-selector"
          >
            <div class="cs-scroll">
              <div
                v-for="(ch, i) in imChapters"
                :key="ch.chapter_id"
                class="cs-item"
                :class="{ active: i === imCurrentChapterIndex }"
                @click="imSelectChapter(i)"
              >
                <span class="cs-dot" :class="{ done: ch.pdf_exists }" />
                <span class="cs-label">{{ ch.title }}</span>
                <span v-if="ch.audio_files?.length" class="cs-pages"
                  >🔊{{ ch.audio_files.length }}</span
                >
              </div>
              <div
                v-if="imGenerating && imGeneratingChapterTitle"
                class="cs-item generating"
              >
                <span class="gen-pulse" style="width: 6px; height: 6px" />
                <span class="cs-label">{{ imGeneratingChapterTitle }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 分隔线 -->
        <div
          class="resizer"
          :class="{ dragging: isDragging }"
          @mousedown="startResize"
        />

        <!-- 右侧面板 -->
        <div
          class="chat-panel"
          :style="chatWidth ? { width: chatWidth + 'px' } : { width: '45%' }"
        >
          <!-- ═══ 人机交互模式：对话区 ═══ -->
          <template v-if="learningMode === 'chat'">
            <!-- Agent 顶栏 -->
            <div class="agent-topbar">
              <div class="at-agent">
                <div class="at-avatar-wrap">
                  <div
                    class="at-avatar-ring"
                    :class="{ active: isThinking || phase === 'generating' }"
                  />
                  <div class="agent-avatar" style="width: 34px; height: 34px">
                    <svg
                      width="14"
                      height="14"
                      viewBox="0 0 24 24"
                      fill="none"
                      stroke="white"
                      stroke-width="2"
                    >
                      <path d="M12 2a10 10 0 100 20A10 10 0 0012 2z" />
                      <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
                      <line x1="12" y1="17" x2="12.01" y2="17" />
                    </svg>
                  </div>
                </div>
                <div>
                  <div class="at-name">智流辅导 Agent</div>
                  <div class="at-status">
                    <span
                      class="at-dot"
                      :class="{
                        thinking: isThinking || phase === 'generating',
                      }"
                    />
                    {{
                      phase === "generating"
                        ? "正在生成卡片..."
                        : isThinking
                          ? "正在思考..."
                          : "在线"
                    }}
                  </div>
                </div>
              </div>
            </div>

            <!-- 上下文条 -->
            <div
              v-if="pdfCards.length > 0 && phase === 'learning'"
              class="context-strip"
            >
              <span>📄</span>
              <span class="cs-title">{{
                pdfCards[currentPdfIndex]?.title
              }}</span>
              <span class="cs-hint">针对当前卡片提问</span>
            </div>

            <!-- 消息流 -->
            <div ref="messagesRef" class="messages-flow">
              <div
                v-if="messages.length === 0 && phase === 'learning'"
                class="welcome-flow"
              >
                <p class="wf-text">
                  卡片已生成！有任何疑问随时问我，<br />我会结合<strong>当前卡片内容</strong>来解答。
                </p>
                <div class="quick-list">
                  <button
                    v-for="q in contextQuicks"
                    :key="q"
                    class="quick-item"
                    @click="sendMessage(q)"
                  >
                    {{ q }}
                  </button>
                </div>
              </div>
              <template v-else>
                <div
                  v-for="(msg, i) in messages"
                  :key="i"
                  class="msg-row"
                  :class="msg.role"
                >
                  <div v-if="msg.role === 'assistant'" class="msg-av">
                    <div class="agent-avatar" style="width: 24px; height: 24px">
                      <svg
                        width="10"
                        height="10"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="white"
                        stroke-width="2.5"
                      >
                        <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
                        <line x1="12" y1="17" x2="12.01" y2="17" />
                      </svg>
                    </div>
                  </div>
                  <div class="msg-col">
                    <div class="msg-bubble" :class="msg.role">
                      <div v-if="msg.thinking" class="typing-dots">
                        <span /><span /><span />
                      </div>
                      <template v-else>
                        <!-- 工具调用进度 -->
                        <div
                          v-if="msg.steps && msg.steps.length"
                          class="msg-steps"
                        >
                          <div
                            v-for="(s, si) in msg.steps"
                            :key="si"
                            class="ms-item"
                            :class="s.status"
                          >
                            <span class="ms-icon">
                              <svg
                                v-if="s.status === 'done'"
                                width="10"
                                height="10"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="3"
                              >
                                <polyline points="20 6 9 17 4 12" />
                              </svg>
                              <span
                                v-else-if="s.status === 'running'"
                                class="ms-spin"
                              />
                              <svg
                                v-else
                                width="10"
                                height="10"
                                viewBox="0 0 24 24"
                                fill="none"
                                stroke="currentColor"
                                stroke-width="2"
                              >
                                <circle cx="12" cy="12" r="10" />
                              </svg>
                            </span>
                            <span class="ms-label">{{ s.label }}</span>
                          </div>
                        </div>
                        <!-- 正文 -->
                        <div
                          v-if="msg.content"
                          class="msg-text"
                          v-html="msg.html || msg.content"
                        />
                        <!-- 业务事件标签 -->
                        <div
                          v-if="msg.events && msg.events.length"
                          class="msg-events"
                        >
                          <span
                            v-for="(ev, ei) in msg.events"
                            :key="ei"
                            class="me-tag"
                            :class="ev.type"
                            :style="
                              ev.type === 'node_created' ||
                              ev.type === 'node_exists'
                                ? 'cursor:pointer'
                                : ''
                            "
                            @click="
                              ev.type === 'node_created' ||
                              ev.type === 'node_exists'
                                ? $router.push('/graph')
                                : null
                            "
                          >
                            <template v-if="ev.type === 'node_created'"
                              >🧠 新节点：{{ ev.title }}</template
                            >
                            <template v-else-if="ev.type === 'node_exists'"
                              >🧠 节点已存在：{{ ev.title }}</template
                            >
                            <template v-else-if="ev.type === 'file_created'"
                              >📄 生成文件</template
                            >
                            <template v-else-if="ev.type === 'mastery_updated'"
                              >📈 掌握度 +{{
                                (ev.delta * 100).toFixed(0)
                              }}%</template
                            >
                          </span>
                        </div>
                      </template>
                    </div>
                    <div class="msg-meta">
                      <span v-if="msg.newCard" class="msg-card-tag">
                        <svg
                          width="9"
                          height="9"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="2"
                        >
                          <rect x="3" y="3" width="18" height="18" rx="2" />
                        </svg>
                        新卡片：{{ msg.newCard }}
                      </span>
                      <span class="msg-time">{{ msg.time }}</span>
                    </div>
                  </div>
                  <div v-if="msg.role === 'user'" class="msg-av user-av">
                    <div
                      class="avatar"
                      style="
                        width: 24px;
                        height: 24px;
                        font-size: 10px;
                        font-weight: 700;
                      "
                    >
                      袁
                    </div>
                  </div>
                </div>
              </template>
            </div>

            <!-- 快捷提问 -->
            <div
              v-if="phase === 'learning' && messages.length > 0"
              class="quick-bar"
            >
              <button
                v-for="q in contextQuicks.slice(0, 2)"
                :key="q"
                class="qb-chip"
                @click="sendMessage(q)"
              >
                {{ q }}
              </button>
            </div>

            <!-- 输入区 -->
            <div class="input-zone">
              <div class="iz-input-wrap" :class="{ focused: inputFocused }">
                <textarea
                  ref="inputBox"
                  v-model="inputText"
                  class="iz-input"
                  :placeholder="
                    isGenerating || phase === 'generating'
                      ? 'Agent 正在生成，请稍候...'
                      : '问我任何学习问题...'
                  "
                  :disabled="isGenerating || phase === 'generating'"
                  rows="1"
                  @keydown.enter.exact.prevent="sendMessage(inputText)"
                  @input="autoResize"
                  @focus="inputFocused = true"
                  @blur="inputFocused = false"
                />
                <button
                  class="iz-send"
                  :class="{
                    active: inputText.trim() && phase !== 'generating',
                  }"
                  @click="sendMessage(inputText)"
                >
                  <svg
                    width="14"
                    height="14"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                  >
                    <line x1="22" y1="2" x2="11" y2="13" />
                    <polygon points="22 2 15 22 11 13 2 9 22 2" />
                  </svg>
                </button>
              </div>
              <div class="iz-hint">Enter 发送 · Shift+Enter 换行</div>
            </div>
          </template>

          <!-- ═══ AI主导模式：大纲 + 习题 + 日志 ═══ -->
          <template v-else>
            <div class="im-sidebar-inner">
              <div class="im-tabs">
                <button
                  :class="{ active: imTab === 'outline' }"
                  @click="imTab = 'outline'"
                >
                  📋 大纲
                </button>
                <button
                  :class="{ active: imTab === 'exercises' }"
                  @click="imTab = 'exercises'"
                >
                  ✏️ 习题
                </button>
                <button
                  :class="{ active: imTab === 'agent' }"
                  @click="imTab = 'agent'"
                >
                  🤖 智流Agent
                  <span v-if="imAgentMessages.length" class="im-log-count">{{
                    imAgentMessages.length
                  }}</span>
                </button>
                <button
                  :class="{ active: imTab === 'log' }"
                  @click="imTab = 'log'"
                >
                  📝 日志
                  <span v-if="imLogs.length" class="im-log-count">{{
                    imLogs.length
                  }}</span>
                </button>
              </div>
              <div class="im-tab-content">
                <!-- 大纲 -->
                <div v-if="imTab === 'outline'" class="im-outline">
                  <div v-if="!imOutline" class="im-placeholder">
                    大纲生成中...
                  </div>
                  <template v-else>
                    <h3
                      style="
                        font-size: 16px;
                        font-weight: 700;
                        color: var(--text-primary);
                        margin: 0 0 8px;
                      "
                    >
                      {{ imOutline.topic }}
                    </h3>
                    <p
                      style="
                        font-size: 13px;
                        color: var(--text-secondary);
                        line-height: 1.7;
                        margin-bottom: 16px;
                      "
                    >
                      {{ imOutline.overview }}
                    </p>
                    <div
                      v-for="ch in imOutline.chapters"
                      :key="ch.chapter_id"
                      style="
                        padding: 10px 0;
                        border-top: 1px solid var(--border);
                      "
                    >
                      <div
                        style="
                          font-size: 13px;
                          font-weight: 600;
                          color: var(--text-primary);
                          margin-bottom: 4px;
                        "
                      >
                        {{
                          isImChapterDone(ch.chapter_id)
                            ? "✅"
                            : isImChapterCurrent(ch.chapter_id)
                              ? "⏳"
                              : "○"
                        }}
                        {{ ch.title }}
                      </div>
                      <div
                        style="
                          font-size: 12px;
                          color: var(--text-muted);
                          margin-bottom: 6px;
                        "
                      >
                        {{ ch.description }}
                      </div>
                      <div style="display: flex; flex-wrap: wrap; gap: 4px">
                        <span
                          v-for="kp in ch.knowledge_points"
                          :key="kp"
                          style="
                            font-size: 10px;
                            padding: 2px 7px;
                            border-radius: 4px;
                            background: var(--brand-dim);
                            color: var(--brand-light);
                            border: 1px solid rgba(99, 102, 241, 0.15);
                          "
                          >{{ kp }}</span
                        >
                      </div>
                    </div>
                  </template>
                </div>

                <!-- 习题（美化版：逐题显示 + 统一AI判分） -->
                <div v-if="imTab === 'exercises'" class="im-exercises">
                  <div
                    v-if="!imCurrentChapter?.exercises_exists"
                    class="im-placeholder"
                  >
                    {{
                      imChapters.length > 0 ? "本章暂无习题" : "等待课件生成..."
                    }}
                  </div>
                  <div v-else class="im-quiz-container">
                    <!-- 未提交：逐题作答模式 -->
                    <template v-if="!imQuizSubmitted">
                      <!-- 顶部进度条 -->
                      <div class="imq-progress-bar">
                        <div class="imq-progress-dots">
                          <div
                            v-for="(q, i) in imParsedQuizzes"
                            :key="i"
                            class="imq-dot"
                            :class="{
                              active: i === imQuizCurrent,
                              answered:
                                q.userAnswer !== null || q.userText.trim(),
                            }"
                            @click="imQuizCurrent = i"
                          >
                            {{ i + 1 }}
                          </div>
                        </div>
                        <div class="imq-progress-text">
                          {{ imQuizAnsweredCount }} /
                          {{ imParsedQuizzes.length }} 已作答
                        </div>
                      </div>

                      <!-- 当前题目卡片 -->
                      <div v-if="imParsedQuizzes.length > 0" class="imq-card">
                        <div class="imq-card-header">
                          <span
                            class="imq-card-type"
                            :class="
                              currentQuiz?.type === 'choice'
                                ? 'choice'
                                : currentQuiz?.type === 'fill'
                                  ? 'fill'
                                  : 'text'
                            "
                          >
                            {{
                              currentQuiz?.type === "choice"
                                ? "选择题"
                                : currentQuiz?.type === "fill"
                                  ? "填空题"
                                  : "简答题"
                            }}
                          </span>
                          <span class="imq-card-section">{{
                            currentQuiz?.sectionTitle || ""
                          }}</span>
                          <span class="imq-card-num"
                            >第 {{ imQuizCurrent + 1 }} /
                            {{ imParsedQuizzes.length }} 题</span
                          >
                        </div>
                        <div
                          class="imq-card-question"
                          v-html="renderMd(currentQuiz?.question || '')"
                        />

                        <!-- 选择题选项 -->
                        <div
                          v-if="
                            currentQuiz?.type === 'choice' &&
                            currentQuiz?.options?.length > 0
                          "
                          class="imq-card-options"
                        >
                          <div
                            v-for="(opt, oi) in currentQuiz.options"
                            :key="oi"
                            class="imq-card-opt"
                            :class="{ selected: currentQuiz.userAnswer === oi }"
                            @click="currentQuiz.userAnswer = oi"
                          >
                            <span
                              class="imq-card-opt-letter"
                              :class="{
                                selected: currentQuiz.userAnswer === oi,
                              }"
                              >{{
                                currentQuiz.optionLabels?.[oi] ||
                                String.fromCharCode(65 + oi)
                              }}</span
                            >
                            <span
                              class="imq-card-opt-text"
                              v-html="renderMd(opt)"
                            />
                          </div>
                        </div>

                        <!-- 填空/简答题输入 -->
                        <div v-else class="imq-card-input">
                          <textarea
                            v-model="currentQuiz.userText"
                            :placeholder="
                              currentQuiz?.type === 'fill'
                                ? '填入答案（多个空用逗号分隔）...'
                                : '请详细作答...'
                            "
                            :rows="currentQuiz?.type === 'fill' ? 2 : 5"
                          />
                        </div>

                        <!-- 翻页按钮 -->
                        <div class="imq-card-nav">
                          <button
                            class="imq-nav-btn"
                            :disabled="imQuizCurrent <= 0"
                            @click="imQuizCurrent--"
                          >
                            ← 上一题
                          </button>
                          <button
                            v-if="imQuizCurrent < imParsedQuizzes.length - 1"
                            class="imq-nav-btn primary"
                            @click="imQuizCurrent++"
                          >
                            下一题 →
                          </button>
                          <button
                            v-else
                            class="imq-nav-btn submit"
                            :disabled="
                              imQuizAnsweredCount < imParsedQuizzes.length ||
                              imQuizJudging
                            "
                            @click="submitAllQuizzes"
                          >
                            {{
                              imQuizJudging
                                ? "🤖 AI 判题中..."
                                : "📝 提交全部，AI 统一判分"
                            }}
                          </button>
                        </div>
                        <!-- 还没做完时的提示 -->
                        <div
                          v-if="
                            imQuizCurrent === imParsedQuizzes.length - 1 &&
                            imQuizAnsweredCount < imParsedQuizzes.length
                          "
                          class="imq-unanswered-hint"
                        >
                          还有
                          {{ imParsedQuizzes.length - imQuizAnsweredCount }}
                          题未作答，请完成后提交
                        </div>
                      </div>
                    </template>

                    <!-- 已提交：判分结果页 -->
                    <template v-else>
                      <div class="imq-result">
                        <!-- 总分概览 -->
                        <div class="imq-result-summary">
                          <div
                            class="imq-score-circle"
                            :class="imQuizScoreLevel"
                          >
                            <span class="imq-score-num">{{
                              imQuizStats.correct
                            }}</span>
                            <span class="imq-score-total"
                              >/ {{ imParsedQuizzes.length }}</span
                            >
                          </div>
                          <div class="imq-score-label">
                            {{
                              imQuizScoreLevel === "great"
                                ? "🎉 太棒了！"
                                : imQuizScoreLevel === "good"
                                  ? "👍 不错！"
                                  : "💪 继续加油！"
                            }}
                          </div>
                          <div class="imq-score-bar">
                            <span class="imq-stat correct"
                              >✅ {{ imQuizStats.correct }} 正确</span
                            >
                            <span class="imq-stat wrong"
                              >❌ {{ imQuizStats.wrong }} 错误</span
                            >
                          </div>
                        </div>

                        <!-- 每题详细分析 -->
                        <div class="imq-result-list">
                          <div
                            v-for="(q, qi) in imParsedQuizzes"
                            :key="qi"
                            class="imq-result-item"
                            :class="{
                              correct: q.judgeResult === true,
                              wrong: q.judgeResult === false,
                            }"
                          >
                            <div class="imq-result-num">
                              <span
                                :class="
                                  q.judgeResult ? 'icon-correct' : 'icon-wrong'
                                "
                                >{{ q.judgeResult ? "✅" : "❌" }}</span
                              >
                              第 {{ qi + 1 }} 题
                            </div>
                            <div
                              class="imq-result-question"
                              v-html="renderMd(q.question)"
                            />
                            <div class="imq-result-answer">
                              <span class="label">你的答案：</span>
                              <span class="value">{{
                                typeof q.userAnswer === "number"
                                  ? (q.optionLabels?.[q.userAnswer] ||
                                      String.fromCharCode(65 + q.userAnswer)) +
                                    ". " +
                                    (q.options?.[q.userAnswer] || "")
                                  : q.userText || "未作答"
                              }}</span>
                            </div>
                            <div
                              v-if="q.judgeResult === false && q.answer"
                              class="imq-result-correct"
                            >
                              <span class="label">正确答案：</span>
                              <span class="value">{{ q.answer }}</span>
                            </div>
                            <div
                              v-if="q.feedback"
                              class="imq-result-feedback"
                              v-html="renderMd(q.feedback)"
                            />
                          </div>
                        </div>

                        <!-- AI 综合学习建议 -->
                        <div v-if="imQuizAdvice" class="imq-result-advice">
                          <div class="imq-advice-title">📚 AI 学习建议</div>
                          <div
                            class="imq-advice-content"
                            v-html="renderMd(imQuizAdvice)"
                          />
                        </div>

                        <!-- 重做按钮 -->
                        <button class="imq-retry-btn" @click="retryQuiz">
                          🔄 重新做题
                        </button>
                      </div>
                    </template>

                    <!-- 无法解析时 fallback 到原始 markdown -->
                    <div
                      v-if="imParsedQuizzes.length === 0 && imExercisesHtml"
                      class="im-ex-content"
                      v-html="imExercisesHtml"
                    />
                  </div>
                </div>

                <!-- 智流 Agent 对话 -->
                <div v-if="imTab === 'agent'" class="im-agent-chat">
                  <div ref="imAgentMsgRef" class="im-agent-messages">
                    <div
                      v-if="imAgentMessages.length === 0"
                      class="im-agent-welcome"
                    >
                      <div class="im-agent-welcome-icon">🤖</div>
                      <div class="im-agent-welcome-title">智流 Agent</div>
                      <div class="im-agent-welcome-desc">
                        有任何关于课程内容的问题，随时问我！
                      </div>
                      <div class="im-agent-quick-list">
                        <button
                          class="im-agent-quick"
                          @click="sendImAgentMsg('帮我总结当前章节的要点')"
                        >
                          📝 总结当前章节
                        </button>
                        <button
                          class="im-agent-quick"
                          @click="sendImAgentMsg('这个知识点有什么实际应用？')"
                        >
                          🔍 实际应用场景
                        </button>
                        <button
                          class="im-agent-quick"
                          @click="sendImAgentMsg('帮我出几道练习题测试一下')"
                        >
                          ✏️ 出练习题
                        </button>
                      </div>
                    </div>
                    <div
                      v-for="(m, mi) in imAgentMessages"
                      :key="mi"
                      class="im-agent-msg"
                      :class="m.role"
                    >
                      <div
                        v-if="m.role === 'assistant'"
                        class="im-agent-msg-av"
                      >
                        <div
                          class="agent-avatar"
                          style="width: 22px; height: 22px"
                        >
                          <svg
                            width="9"
                            height="9"
                            viewBox="0 0 24 24"
                            fill="none"
                            stroke="white"
                            stroke-width="2.5"
                          >
                            <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
                            <line x1="12" y1="17" x2="12.01" y2="17" />
                          </svg>
                        </div>
                      </div>
                      <div class="im-agent-msg-bubble" :class="m.role">
                        <div v-if="m.thinking" class="typing-dots">
                          <span /><span /><span />
                        </div>
                        <div
                          v-else
                          class="msg-text"
                          v-html="m.html || m.content"
                        />
                      </div>
                    </div>
                  </div>
                  <div class="im-agent-input-zone">
                    <div class="im-agent-input-wrap">
                      <textarea
                        v-model="imAgentInput"
                        class="im-agent-input"
                        placeholder="问我关于课程内容的问题..."
                        :disabled="imAgentGenerating"
                        rows="1"
                        @keydown.enter.exact.prevent="
                          sendImAgentMsg(imAgentInput)
                        "
                        @input="
                          (e) => {
                            e.target.style.height = 'auto';
                            e.target.style.height =
                              Math.min(e.target.scrollHeight, 80) + 'px';
                          }
                        "
                      />
                      <button
                        class="im-agent-send"
                        :class="{ active: imAgentInput.trim() }"
                        @click="sendImAgentMsg(imAgentInput)"
                      >
                        <svg
                          width="12"
                          height="12"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="2.5"
                        >
                          <line x1="22" y1="2" x2="11" y2="13" />
                          <polygon points="22 2 15 22 11 13 2 9 22 2" />
                        </svg>
                      </button>
                    </div>
                  </div>
                </div>

                <!-- 日志 -->
                <div v-if="imTab === 'log'" ref="imLogRef" class="im-log">
                  <div
                    v-for="(log, i) in imLogs"
                    :key="i"
                    class="im-log-item"
                    :class="log.level"
                  >
                    <span class="im-log-time">{{ log.time }}</span>
                    <span class="im-log-msg">{{ log.message }}</span>
                  </div>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from "vue";
import { useRoute } from "vue-router";
import { sessionApi, BASE_URL } from "@/api";
import { marked } from "marked";
import DOMPurify from "dompurify";
import katex from "katex";
import "katex/dist/katex.min.css";
import * as pdfjsLib from "pdfjs-dist/webpack.mjs";
import { PDFDocument } from "pdf-lib";

// 使用 npm 包内嵌的 Worker 方案，webpack.mjs 会自动配置 Worker
// 配置 PDF.js 字体支持
pdfjsLib.GlobalWorkerOptions.fontFamily =
  "'PingFang SC', 'Noto Sans CJK SC', 'Source Han Sans SC', 'FandolSong-Regular', 'Droid Sans Fallback', 'SimSun', 'Microsoft YaHei', sans-serif";

// 强制PDF.js使用系统字体渲染
pdfjsLib.GlobalWorkerOptions.useSystemFonts = true;

// 配置CMap用于中文字符映射
pdfjsLib.GlobalWorkerOptions.cMapUrl =
  "https://unpkg.com/pdfjs-dist@5.6.205/cmaps/";
pdfjsLib.GlobalWorkerOptions.cMapPacked = true;

// 添加字体映射配置，确保中文字体正确显示
if (typeof window !== "undefined") {
  document.addEventListener("DOMContentLoaded", () => {
    // 为PDF canvas添加字体样式
    const style = document.createElement("style");
    style.textContent = `
      .pdf-main-canvas, .ts-canvas {
        font-family: 'PingFang SC', 'Noto Sans CJK SC', 'Source Han Sans SC',
                     'FandolSong-Regular', 'Droid Sans Fallback', 'SimSun',
                     'Microsoft YaHei', sans-serif !important;
      }

      /* 确保文本层使用正确字体 */
      .textLayer {
        font-family: 'PingFang SC', 'Noto Sans CJK SC', 'Source Han Sans SC',
                     'FandolSong-Regular', 'Droid Sans Fallback', 'SimSun',
                     'Microsoft YaHei', sans-serif !important;
      }
    `;
    document.head.appendChild(style);

    // 预加载常用中文字体
    const fonts = [
      "PingFang SC",
      "Noto Sans CJK SC",
      "Source Han Sans SC",
      "Microsoft YaHei",
      "SimSun",
    ];

    fonts.forEach((font) => {
      if (document.fonts.check(`12px "${font}"`)) {
        console.log(`字体 ${font} 已可用`);
      }
    });
  });
}

// 配置 marked
marked.setOptions({ breaks: true, gfm: true });

/**
 * 将 LaTeX 公式渲染为 KaTeX HTML，再交给 marked 处理 markdown。
 * 支持的公式语法：
 *   行内：$...$  或  \(...\)
 *   块级：$$...$$  或  \[...\]
 */
function renderLatex(text) {
  if (!text) return "";

  // 占位符映射，避免 marked 破坏 KaTeX 输出的 HTML
  const placeholders = [];
  function hold(html) {
    const id = `%%KATEX_${placeholders.length}%%`;
    placeholders.push(html);
    return id;
  }

  // 1. 块级公式：$$...$$ （可跨行）
  let result = text.replace(/\$\$(\s*[\s\S]+?\s*)\$\$/g, (_, expr) => {
    try {
      return hold(
        katex.renderToString(expr.trim(), {
          displayMode: true,
          throwOnError: false,
        }),
      );
    } catch {
      return _;
    }
  });

  // 2. 块级公式：\[...\] （可跨行）
  result = result.replace(/\\\[([\s\S]+?)\\\]/g, (_, expr) => {
    try {
      return hold(
        katex.renderToString(expr.trim(), {
          displayMode: true,
          throwOnError: false,
        }),
      );
    } catch {
      return _;
    }
  });

  // 3. 行内公式：\(...\)
  result = result.replace(/\\\((.+?)\\\)/g, (_, expr) => {
    try {
      return hold(
        katex.renderToString(expr.trim(), {
          displayMode: false,
          throwOnError: false,
        }),
      );
    } catch {
      return _;
    }
  });

  // 4. 行内公式：$...$ （不匹配 $$，不跨行）
  result = result.replace(
    /(?<!\$)\$(?!\$)([^\n$]+?)(?<!\$)\$(?!\$)/g,
    (_, expr) => {
      try {
        return hold(
          katex.renderToString(expr.trim(), {
            displayMode: false,
            throwOnError: false,
          }),
        );
      } catch {
        return _;
      }
    },
  );

  // 5. 还原占位符
  for (let i = 0; i < placeholders.length; i++) {
    result = result.replace(`%%KATEX_${i}%%`, placeholders[i]);
  }

  return result;
}

// 将 markdown + LaTeX 转为安全 HTML
function renderMd(text) {
  if (!text) return "";
  // 先处理 LaTeX 公式，再渲染 markdown
  const withLatex = renderLatex(text);
  // DOMPurify 需要放行 KaTeX 的 HTML 标签和属性
  return DOMPurify.sanitize(marked.parse(withLatex), {
    ADD_TAGS: [
      "span",
      "math",
      "semantics",
      "mrow",
      "mi",
      "mo",
      "mn",
      "msup",
      "msub",
      "mfrac",
      "mtext",
      "annotation",
      "mover",
      "munder",
      "mtable",
      "mtr",
      "mtd",
      "mspace",
      "msqrt",
      "mroot",
      "menclose",
    ],
    ADD_ATTR: [
      "class",
      "style",
      "mathvariant",
      "encoding",
      "displaystyle",
      "scriptlevel",
      "xmlns",
      "aria-hidden",
      "role",
    ],
  });
}

const route = useRoute();

// ── 学习模式 ─────────────────────────────────────────────────────
// 'chat' = 人机交互学习, 'immersive' = AI 主导学习
const learningMode = ref("chat");

// ── AI 主导学习：跳转改为本页启动 ────────────────────────────────
function startImmersive() {
  if (!topicInput.value.trim()) return;
  learningMode.value = "immersive";
  currentTopic.value = topicInput.value.trim();
  phase.value = "immersive";
  imStartGenerate();
}

// ══════════════════════════════════════════════════════════════
// AI 主导学习（沉浸式）所有状态
// ══════════════════════════════════════════════════════════════
const imGenerating = ref(false);
const imCompleted = ref(false);
const imProgress = ref(0);
const imCurrentStage = ref("");
const imStatusMessage = ref("");
const imOutline = ref(null);
const imChapters = ref([]);
const imCurrentChapterIndex = ref(0);
const imCurrentPage = ref(1);
const imTotalPages = ref(0);
const imTab = ref("log");
const imLogs = ref([]);
const imPdfCanvas = ref(null);
const imLogRef = ref(null);
const imIsPlaying = ref(false);
const imExercisesHtml = ref("");
const imGeneratingChapterId = ref(0);
const imGeneratingChapterTitle = ref("");

const imPdfDocMap = new Map();
let imCurrentAudio = null;

// ── 智流 Agent 对话（AI 主导模式内） ─────────────────────────────
const imAgentMessages = ref([]);
const imAgentInput = ref("");
const imAgentGenerating = ref(false);
const imAgentMsgRef = ref(null);

async function sendImAgentMsg(text) {
  if (!text || !text.trim() || imAgentGenerating.value) return;
  imAgentGenerating.value = true;
  imAgentMessages.value.push({ role: "user", content: text, time: now() });
  imAgentInput.value = "";
  await nextTick();
  if (imAgentMsgRef.value)
    imAgentMsgRef.value.scrollTop = imAgentMsgRef.value.scrollHeight;

  // thinking 占位
  imAgentMessages.value.push({
    role: "assistant",
    thinking: true,
    content: "",
    html: "",
    time: "",
  });
  await nextTick();
  if (imAgentMsgRef.value)
    imAgentMsgRef.value.scrollTop = imAgentMsgRef.value.scrollHeight;

  // 构建上下文：当前章节信息 + 大纲
  const ch = imCurrentChapter.value;
  const contextInfo = ch
    ? `当前正在学习「${currentTopic.value}」第${ch.chapter_id}章「${ch.title}」`
    : `当前正在学习「${currentTopic.value}」`;

  try {
    // 使用后端 immersive agent chat API（如果有的话），否则用人机交互的 session
    // 这里复用已有的 session SSE
    if (currentSessionId.value) {
      const agentText = `[智流Agent] ${contextInfo}\n\n用户问题：${text}`;
      const idx = imAgentMessages.value.length - 1;
      let fullContent = "";

      sessionApi.streamMessage(currentSessionId.value, agentText, {
        onTextReply: (text) => {
          fullContent += text;
          imAgentMessages.value[idx] = {
            role: "assistant",
            thinking: false,
            content: fullContent,
            html: renderMd(fullContent),
            time: now(),
          };
          if (imAgentMsgRef.value)
            imAgentMsgRef.value.scrollTop = imAgentMsgRef.value.scrollHeight;
        },
        onDone: () => {
          imAgentMessages.value[idx] = {
            role: "assistant",
            thinking: false,
            content: fullContent,
            html: renderMd(fullContent),
            time: now(),
          };
          imAgentGenerating.value = false;
        },
        onError: (err) => {
          imAgentMessages.value[idx] = {
            role: "assistant",
            thinking: false,
            content: `连接失败: ${err.message}`,
            html: `连接失败: ${err.message}`,
            time: now(),
          };
          imAgentGenerating.value = false;
        },
      });
    } else {
      // 没有 session 时用简单提示
      const idx = imAgentMessages.value.length - 1;
      imAgentMessages.value[idx] = {
        role: "assistant",
        thinking: false,
        content: "课程尚未生成完成，请等待课件完成后再提问。",
        html: "课程尚未生成完成，请等待课件完成后再提问。",
        time: now(),
      };
      imAgentGenerating.value = false;
    }
  } catch (e) {
    const idx = imAgentMessages.value.length - 1;
    imAgentMessages.value[idx] = {
      role: "assistant",
      thinking: false,
      content: `错误: ${e.message}`,
      html: `错误: ${e.message}`,
      time: now(),
    };
    imAgentGenerating.value = false;
  }
}

// ── 习题交互系统 ────────────────────────────────────────────────
const imParsedQuizzes = ref([]);
const imQuizJudging = ref(false);
const imQuizCurrent = ref(0); // 当前显示第几题
const imQuizSubmitted = ref(false); // 是否已提交判分
const imQuizAdvice = ref(""); // AI 综合学习建议

const currentQuiz = computed(
  () => imParsedQuizzes.value[imQuizCurrent.value] || null,
);

const imQuizAnsweredCount = computed(() => {
  return imParsedQuizzes.value.filter(
    (q) => q.userAnswer !== null || q.userText.trim(),
  ).length;
});

const imQuizStats = computed(() => {
  const qs = imParsedQuizzes.value;
  return {
    correct: qs.filter((q) => q.judgeResult === true).length,
    wrong: qs.filter((q) => q.judgeResult === false).length,
    pending: qs.filter((q) => q.judgeResult === null).length,
  };
});

const imQuizScoreLevel = computed(() => {
  const total = imParsedQuizzes.value.length;
  if (total === 0) return "low";
  const ratio = imQuizStats.value.correct / total;
  if (ratio >= 0.8) return "great";
  if (ratio >= 0.5) return "good";
  return "low";
});

// 解析习题 markdown 为结构化数据
function parseExercises(mdText) {
  if (!mdText) return [];
  const quizzes = [];

  // ══════════════════════════════════════════════════════════════
  // 通用解析器：兼容多种 AI 生成的习题格式
  // 格式1: ## 习题 X：类型题  （旧格式，内含子题）
  // 格式2: ## 题目 X（类型题）：标题  （每题独立，含 <details>）
  // 格式3: ## 一、选择题 → ### 1. 题干  （大类 + 子题）
  // 格式4: ### 题目 X: 选择题  （### 级标题）
  // 格式5: ### 1. 选择题  （直接编号）
  // 核心策略：按 <details> 块分割独立题目，自动检测题型
  // ══════════════════════════════════════════════════════════════

  // ── 辅助函数 ──
  function detectType(text) {
    // 有 A/B/C/D 选项 → 选择题
    if (/(?:^|\n)\s*[A-D][.、)]\s*.+/m.test(text)) return "choice";
    // 有下划线空位 → 填空题
    if (/_{2,}/.test(text)) return "fill";
    // 标题中明确写了类型
    const header = text.split("\n")[0] || "";
    if (/选择/.test(header)) return "choice";
    if (/填空/.test(header)) return "fill";
    if (/判断/.test(header)) return "choice";
    return "text"; // 简答 / 综合 / 其他
  }

  function extractAnswer(detailsContent) {
    if (!detailsContent) return { answer: "", explanation: "" };
    const cleaned = detailsContent.replace(/<\/?summary[^>]*>/g, "").trim();

    // 提取答案：**答案：X** 或 答案：X
    let answer = "";
    const ansMatch = cleaned.match(
      /\*{0,2}(?:参考)?答案[：:]\s*\*{0,2}\s*([\s\S]*?)(?=\n\*{0,2}(?:解析|说明)[：:]|\n---|\n\n|$)/i,
    );
    if (ansMatch) {
      answer = ansMatch[1]
        .trim()
        .replace(/\*{1,2}/g, "")
        .trim();
    }

    // 提取解析
    let explanation = "";
    const explMatch = cleaned.match(
      /\*{0,2}(?:解析|说明)[：:]\s*\*{0,2}\s*([\s\S]*?)$/i,
    );
    if (explMatch) {
      explanation = explMatch[1].trim();
    }
    // 如果没有明确的解析标记，用答案后面的所有内容
    if (!explanation && ansMatch) {
      const afterAnswer = cleaned
        .substring(cleaned.indexOf(ansMatch[0]) + ansMatch[0].length)
        .trim();
      if (afterAnswer.length > 10) explanation = afterAnswer;
    }
    // 兜底：整段作为答案+解析
    if (!answer && !explanation) {
      answer = cleaned.length < 200 ? cleaned : cleaned.substring(0, 200);
      explanation = cleaned;
    }
    return { answer, explanation };
  }

  function extractOptions(questionText) {
    const opts = [];
    // 匹配 "A. xxx" / "A、xxx" / "A) xxx" / "- A. xxx"，兼容 **加粗**
    const optRegex =
      /(?:^|\n)\s*[-\s]*([A-D])[.、)]\s*\*{0,2}(.+?)\*{0,2}\s*$/gm;
    let om;
    while ((om = optRegex.exec(questionText)) !== null) {
      opts.push({ label: om[1], text: om[2].trim() });
    }
    return opts;
  }

  function extractStem(questionText, opts) {
    if (opts.length === 0) {
      // 去掉标题行，剩下就是题干
      return questionText.replace(/^#{1,4}\s*.+$/m, "").trim();
    }
    // 选项之前的部分
    const firstOptIdx = questionText.search(/(?:^|\n)\s*[-\s]*[A-D][.、)]/);
    const raw =
      firstOptIdx > 0 ? questionText.substring(0, firstOptIdx) : questionText;
    return raw.replace(/^#{1,4}\s*.+$/m, "").trim();
  }

  function extractTitle(headerLine) {
    // 从标题行提取题号和类型描述
    return headerLine.replace(/^#{1,4}\s*/, "").trim();
  }

  function correctLetterFromAnswer(answerStr) {
    const m = answerStr.match(/^([A-D])/i);
    return m ? m[1].toUpperCase() : null;
  }

  // ── 主逻辑：按 <details> 块分割独立题目 ──
  // 每个 <details> 对应一道题的答案，它前面的内容就是题目
  const detailsRegex = /<details[^>]*>([\s\S]*?)<\/details>/gi;
  const detailsBlocks = [];
  let dm;
  while ((dm = detailsRegex.exec(mdText)) !== null) {
    detailsBlocks.push({
      index: dm.index,
      end: dm.index + dm[0].length,
      content: dm[1],
    });
  }

  if (detailsBlocks.length > 0) {
    // 有 <details> 块：每个块前面的内容是一道题
    for (let di = 0; di < detailsBlocks.length; di++) {
      const db = detailsBlocks[di];
      const prevEnd = di > 0 ? detailsBlocks[di - 1].end : 0;
      const questionBlock = mdText.substring(prevEnd, db.index).trim();
      if (!questionBlock || questionBlock.length < 5) continue;

      const type = detectType(questionBlock);
      const { answer, explanation } = extractAnswer(db.content);
      const opts = type === "choice" ? extractOptions(questionBlock) : [];
      const stem = extractStem(questionBlock, opts);
      const title = extractTitle(
        (questionBlock.match(/^#{1,4}\s*.+$/m) || [""])[0],
      );

      if (type === "choice" && opts.length > 0) {
        const letter = correctLetterFromAnswer(answer);
        const correctIndex = letter ? letter.charCodeAt(0) - 65 : -1;
        quizzes.push({
          sectionTitle: title,
          subNum: di + 1,
          question: stem || title,
          type: "choice",
          options: opts.map((o) => o.text),
          optionLabels: opts.map((o) => o.label),
          answer,
          correctIndex,
          explanation,
          userAnswer: null,
          userText: "",
          judgeResult: null,
          feedback: "",
        });
      } else if (type === "fill") {
        quizzes.push({
          sectionTitle: title,
          subNum: di + 1,
          question: stem || title,
          type: "fill",
          options: [],
          optionLabels: [],
          answer,
          correctIndex: -1,
          explanation,
          userAnswer: null,
          userText: "",
          judgeResult: null,
          feedback: "",
        });
      } else {
        quizzes.push({
          sectionTitle: title,
          subNum: di + 1,
          question: stem || title,
          type: "text",
          options: [],
          optionLabels: [],
          answer,
          correctIndex: -1,
          explanation,
          userAnswer: null,
          userText: "",
          judgeResult: null,
          feedback: "",
        });
      }
    }
  }

  // ── 兜底：没有 <details> 块时，按 ## / ### 标题分割 ──
  if (quizzes.length === 0) {
    const headingRegex = /^#{2,3}\s+.+$/gm;
    const headings = [];
    let hm;
    while ((hm = headingRegex.exec(mdText)) !== null) {
      headings.push({ index: hm.index, text: hm[0] });
    }
    for (let hi = 0; hi < headings.length; hi++) {
      const start = headings[hi].index;
      const end =
        hi + 1 < headings.length ? headings[hi + 1].index : mdText.length;
      const block = mdText.substring(start, end).trim();
      if (block.length < 20) continue;

      const type = detectType(block);
      const opts = type === "choice" ? extractOptions(block) : [];
      const stem = extractStem(block, opts);
      const title = extractTitle(headings[hi].text);
      if (!stem || stem.length < 5) continue;

      quizzes.push({
        sectionTitle: title,
        subNum: hi + 1,
        question: stem,
        type:
          type === "choice" && opts.length > 0
            ? "choice"
            : type === "fill"
              ? "fill"
              : "text",
        options: opts.map((o) => o.text),
        optionLabels: opts.map((o) => o.label),
        answer: "",
        correctIndex: -1,
        explanation: "",
        userAnswer: null,
        userText: "",
        judgeResult: null,
        feedback: "",
      });
    }
  }

  return quizzes;
}

function retryQuiz() {
  imQuizSubmitted.value = false;
  imQuizCurrent.value = 0;
  imQuizAdvice.value = "";
  for (const q of imParsedQuizzes.value) {
    q.userAnswer = null;
    q.userText = "";
    q.judgeResult = null;
    q.feedback = "";
  }
}

async function submitAllQuizzes() {
  if (!currentSessionId.value) return;
  imQuizJudging.value = true;

  // Step 1: 选择题本地判
  for (const q of imParsedQuizzes.value) {
    if (
      q.options.length > 0 &&
      q.correctIndex >= 0 &&
      typeof q.userAnswer === "number"
    ) {
      q.judgeResult = q.userAnswer === q.correctIndex;
      q.feedback = q.judgeResult
        ? `✅ 正确！${q.explanation || ""}`
        : `正确答案是 **${String.fromCharCode(65 + q.correctIndex)}**。${q.explanation || ""}`;
    }
  }

  // Step 2: 填空/简答题用 AI 批量判
  const needAI = imParsedQuizzes.value.filter((q) => q.judgeResult === null);
  if (needAI.length > 0) {
    const questionsStr = needAI
      .map((q, i) => {
        console.log(i);
        const userAns =
          typeof q.userAnswer === "number"
            ? String.fromCharCode(65 + q.userAnswer)
            : q.userText || q.userAnswer || "未作答";
        return `【第${imParsedQuizzes.value.indexOf(q) + 1}题】\n题目：${q.question}\n参考答案：${q.answer || "（无）"}\n学生答案：${userAns}`;
      })
      .join("\n\n");

    const prompt = `请批量判断以下 ${needAI.length} 道题的答案是否正确。

${questionsStr}

请以 JSON 数组回复，每个元素格式：{"index": 题号, "correct": true/false, "feedback": "针对该题的分析（50字内）"}
只回复 JSON 数组，不要其他文字。`;

    try {
      let fullContent = "";
      await new Promise((resolve) => {
        sessionApi.streamMessage(currentSessionId.value, prompt, {
          onTextReply: (text) => {
            fullContent += text;
          },
          onDone: () => resolve(),
          onError: () => resolve(),
        });
      });
      const jsonMatch = fullContent.match(/\[[\s\S]*\]/);
      if (jsonMatch) {
        const results = JSON.parse(jsonMatch[0]);
        for (const r of results) {
          const idx = (r.index || 1) - 1;
          const q = imParsedQuizzes.value[idx];
          if (q && q.judgeResult === null) {
            q.judgeResult = !!r.correct;
            q.feedback = r.feedback || (r.correct ? "正确！" : "不正确。");
          }
        }
      }
    } catch {
      // AI 判题失败时标记为错误
      for (const q of needAI) {
        if (q.judgeResult === null) {
          q.judgeResult = false;
          q.feedback = "AI 判题失败，请重试。";
        }
      }
    }
  }

  // Step 3: 生成综合学习建议（只针对错题）
  const wrongQuizzes = imParsedQuizzes.value.filter(
    (q) => q.judgeResult === false,
  );
  if (wrongQuizzes.length > 0) {
    const wrongStr = wrongQuizzes
      .map((q, i) => {
        console.log(i);
        const userAns =
          typeof q.userAnswer === "number"
            ? String.fromCharCode(65 + q.userAnswer)
            : q.userText || q.userAnswer || "未作答";
        return `- 题目：${q.question.slice(0, 80)}\n  正确答案：${q.answer || "见解析"}\n  学生答案：${userAns}`;
      })
      .join("\n");

    const advicePrompt = `学生在「${imCurrentChapter.value?.title || "本章"}」的习题中答错了以下题目：

${wrongStr}

请给出 100-200 字的综合学习建议，包括：
1. 哪些知识点薄弱
2. 建议重点复习的方向
3. 简短的鼓励
直接回复建议文本，不需要格式标记。`;

    try {
      let advice = "";
      await new Promise((resolve) => {
        sessionApi.streamMessage(currentSessionId.value, advicePrompt, {
          onTextReply: (text) => {
            advice += text;
          },
          onDone: () => resolve(),
          onError: () => resolve(),
        });
      });
      imQuizAdvice.value = advice;
    } catch {
      imQuizAdvice.value = "AI 生成建议失败，请重试。";
    }
  }

  imQuizSubmitted.value = true;
  imQuizJudging.value = false;
}

const imCurrentChapter = computed(
  () => imChapters.value[imCurrentChapterIndex.value] || null,
);

const imCurrentAudioUrl = computed(() => {
  const ch = imCurrentChapter.value;
  if (!ch?.audio_files?.length) return "";
  const af = ch.audio_files.find((f) => {
    const m = f.filename?.match(/frame_(\d+)\.wav/);
    return m && parseInt(m[1]) === imCurrentPage.value;
  });
  if (!af) return "";
  // 优先用 url 字段，没有则从 pdf_path 推导 audio 目录
  if (af.url) return af.url;
  if (ch.pdf_path) {
    const audioDir = ch.pdf_path.replace(/\/[^/]+\.pdf$/, "/audio/");
    return `${BASE_URL}/api/immersive/files/${audioDir}${af.filename}`;
  }
  return "";
});

// 阶段指示器
const imStages = [
  { key: "planner", icon: "📋", name: "Planner" },
  { key: "researcher", icon: "🔍", name: "Researcher" },
  { key: "tex", icon: "📄", name: "TexWriter" },
  { key: "exercises", icon: "✏️", name: "Exercises" },
  { key: "tts", icon: "🔊", name: "TTS" },
];
const imStageOrder = {
  init: -1,
  planner: 0,
  researcher: 1,
  tex: 2,
  exercises: 3,
  tts: 4,
  nodes: 5,
  done: 6,
};
const imStageIcon = computed(() => {
  const s = imStages.find((s) => s.key === imCurrentStage.value);
  return s?.icon || "⚙️";
});
function isImStageComplete(key) {
  return (imStageOrder[imCurrentStage.value] || 0) > (imStageOrder[key] || 0);
}
function isImChapterDone(chId) {
  return imChapters.value.some((c) => c.chapter_id === chId);
}
function isImChapterCurrent(chId) {
  return imGeneratingChapterId.value === chId;
}

function imAddLog(msg, level = "info") {
  const t = new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
  imLogs.value.push({ time: t, message: msg, level });
  nextTick(() => {
    if (imLogRef.value) imLogRef.value.scrollTop = imLogRef.value.scrollHeight;
  });
}

// SSE 连接
async function imStartGenerate() {
  imGenerating.value = true;
  imCompleted.value = false;
  imProgress.value = 0;
  imCurrentStage.value = "init";
  imStatusMessage.value = "正在初始化...";
  imAddLog(`🚀 开始生成课件：${currentTopic.value}`);

  try {
    const res = await fetch(`${BASE_URL}/api/immersive/generate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic: currentTopic.value }),
    });
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith("data: ")) continue;
        try {
          imHandleSSE(JSON.parse(line.slice(6).trim()));
        } catch {
          console.error("[SSE]", line);
        }
      }
    }
  } catch (e) {
    imAddLog(`❌ 连接失败: ${e.message}`, "error");
  } finally {
    imGenerating.value = false;
    imGeneratingChapterTitle.value = "";
    imGeneratingChapterId.value = 0;
  }
}

function imHandleSSE(data) {
  let logLevel;
  let logMessage;
  const agentType = data.agent_type || "unknown";
  const eventType = data.event_type || "unknown";
  const step = data.step || 0;

  let content =
    data.content.length > 15
      ? data.content.substring(0, 15) + "..."
      : data.content;

  if (window.debug) console.log("[SSE]", data.type, data);
  switch (data.type) {
    case "progress":
      imProgress.value = data.pct || 0;
      imStatusMessage.value = data.message || "";
      if (data.stage) imCurrentStage.value = data.stage;
      imAddLog(data.message);
      break;
    case "outline":
      imOutline.value = data.data;
      imTab.value = "outline";
      imAddLog(
        `✅ 大纲生成完成，共 ${data.data?.chapters?.length || 0} 章`,
        "success",
      );
      break;
    case "chapter_start":
      imGeneratingChapterId.value = data.chapter_id;
      imGeneratingChapterTitle.value = data.title;
      imAddLog(`📖 开始${data.title}`);
      break;
    case "chapter_done": {
      const ch = data.data;
      if (!imChapters.value.some((c) => c.chapter_id === ch.chapter_id)) {
        imChapters.value.push(ch);
      }
      imGeneratingChapterTitle.value = "";
      imGeneratingChapterId.value = 0;
      const badges = [
        ch.pdf_exists ? "PDF✓" : "",
        ch.exercises_exists ? "习题✓" : "",
        ch.audio_files?.length ? `语音${ch.audio_files.length}段` : "",
      ]
        .filter(Boolean)
        .join(" ");
      imAddLog(`✅ ${ch.title} 完成 [${badges}]`, "success");
      if (imChapters.value.length === 1) nextTick(() => imSelectChapter(0));
      break;
    }
    case "nodes_extracted":
      imAddLog(
        `🧠 知识图谱：${data.nodes?.length || 0} 个节点（${data.new_count || 0} 个新建）`,
        "success",
      );
      break;
    case "done":
      imCompleted.value = true;
      // ★ 设置 session_id，否则智流 Agent 对话会被阻止
      if (data.session_id) {
        currentSessionId.value = data.session_id;
        sessionStartTime = Date.now();
      }
      imAddLog(`🎉 全部完成！共 ${imChapters.value.length} 章`, "success");
      break;
    case "error":
      imAddLog(`❌ ${data.message}`, "error");
      break;
    case "agent_event":
      // console.log('agent_event详细数据:', data)

      switch (eventType) {
        case "start":
          logMessage = `🤖 ${agentType} 开始执行: ${content}`;
          logLevel = "info";
          break;
        case "think":
          // 简化思考内容，避免日志过长
          // const thought = data.content.length > 200 ? data.content.substring(0, 200) + '...' : data.content
          logMessage = `💭 ${agentType} 思考 (步骤${step}): ${content}`;
          logLevel = "info";
          break;
        case "tool_call":
          logMessage = `🛠️ ${agentType} : ${content}`;
          logLevel = "info";
          break;
        case "tool_result":
          logMessage = `✅ ${agentType} : ${content}`;
          logLevel = "success";
          break;
        case "finish":
          logMessage = `🏁 ${agentType} : ${content}`;
          logLevel = "success";
          break;
        default:
          logMessage = `🔍 ${agentType} : ${eventType} - ${content}`;
          logLevel = "info";
      }

      imAddLog(logMessage, logLevel);
      break;
    default:
      imAddLog(`🔍 收到未知事件: ${data.type}`, "info");
      // console.log('SSE Handle: ', data)
      break;
  }
}

// PDF 渲染
async function imSelectChapter(idx) {
  imCurrentChapterIndex.value = idx;
  imCurrentPage.value = 1;
  // 重置习题状态
  imQuizCurrent.value = 0;
  imQuizSubmitted.value = false;
  imQuizAdvice.value = "";
  const ch = imChapters.value[idx];
  if (!ch?.pdf_exists || !ch.pdf_path) return;
  if (ch.exercises_exists && ch.exercises_path) {
    try {
      const exRes = await fetch(
        `${BASE_URL}/api/immersive/files/${ch.exercises_path}`,
      );
      const md = await exRes.text();
      imExercisesHtml.value = renderMd(md);
      // 同时解析为可交互的结构化习题
      imParsedQuizzes.value = parseExercises(md);
    } catch {
      imExercisesHtml.value = "";
      imParsedQuizzes.value = [];
    }
  } else {
    imExercisesHtml.value = "";
    imParsedQuizzes.value = [];
  }
  const pdfUrl = `${BASE_URL}/api/immersive/files/${ch.pdf_path}`;
  if (!imPdfDocMap.has(pdfUrl)) {
    try {
      const doc = await pdfjsLib.getDocument({
        url: pdfUrl,
        cMapUrl: "https://unpkg.com/pdfjs-dist@5.6.205/cmaps/",
        cMapPacked: true,
      }).promise;
      imPdfDocMap.set(pdfUrl, doc);
    } catch (e) {
      imAddLog(`PDF 加载失败: ${e.message}`, "error");
      return;
    }
  }
  const doc = imPdfDocMap.get(pdfUrl);
  imTotalPages.value = doc.numPages;
  await imRenderPage(doc, 1);
}

async function imRenderPage(doc, pageNum) {
  if (!imPdfCanvas.value) return;
  const page = await doc.getPage(pageNum);
  const canvas = imPdfCanvas.value;
  const container = canvas.parentElement;
  const dpr = window.devicePixelRatio || 2;
  const viewport = page.getViewport({ scale: 1 });
  const containerW = (container?.clientWidth || 800) - 48;
  const containerH = (container?.clientHeight || 500) - 48;
  const scale = Math.min(
    containerW / viewport.width,
    containerH / viewport.height,
  );
  const scaledVp = page.getViewport({ scale });
  canvas.width = Math.round(scaledVp.width * dpr);
  canvas.height = Math.round(scaledVp.height * dpr);
  canvas.style.width = `${scaledVp.width}px`;
  canvas.style.height = `${scaledVp.height}px`;
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  await page.render({ canvasContext: ctx, viewport: scaledVp }).promise;
  imCurrentPage.value = pageNum;
}

async function imGotoPage(num) {
  const ch = imChapters.value[imCurrentChapterIndex.value];
  if (!ch?.pdf_path) return;
  const pdfUrl = `${BASE_URL}/api/immersive/files/${ch.pdf_path}`;
  const doc = imPdfDocMap.get(pdfUrl);
  if (doc) await imRenderPage(doc, num);
}

function imPlayAudio() {
  if (!imCurrentAudioUrl.value) return;
  if (imIsPlaying.value && imCurrentAudio) {
    imCurrentAudio.pause();
    imIsPlaying.value = false;
    return;
  }
  if (imCurrentAudio) imCurrentAudio.pause();
  imCurrentAudio = new Audio(imCurrentAudioUrl.value);
  imCurrentAudio.play();
  imIsPlaying.value = true;
  imCurrentAudio.onended = () => {
    imIsPlaying.value = false;
  };
  imCurrentAudio.onerror = () => {
    imIsPlaying.value = false;
  };
}

watch(imCurrentPage, () => {
  if (imCurrentAudio) {
    imCurrentAudio.pause();
    imCurrentAudio = null;
  }
  imIsPlaying.value = false;
});

// ── 阶段状态 ────────────────────────────────────────────────────
// idle → generating → learning
const phase = ref("idle");
const currentTopic = ref("");
const topicInput = ref("");
const topicFocused = ref(false);
const topicInputEl = ref(null);
const genProgress = ref(0);
const genStage = ref(-1);

// 消费来自知识图谱页面的 topic 参数（如 /chat?topic=递归算法）
// 或来自学习历史页面的 session_id 参数（如 /chat?session_id=xxx，恢复历史会话）
onMounted(async () => {
  const sessionId = route.query.session_id;
  const topic = route.query.topic;

  if (sessionId) {
    // 恢复历史会话
    try {
      const detail = await sessionApi.getById(sessionId);
      currentSessionId.value = detail.id;
      sessionStartTime = Date.now();
      currentTopic.value = detail.topic || detail.title || "历史会话";

      // 判断是否为 AI 主导学习会话
      const isImmersiveSession = (detail.title || "").startsWith("[AI课程]");

      if (isImmersiveSession) {
        // ── 恢复 AI 主导学习 ──
        learningMode.value = "immersive";
        phase.value = "immersive";
        imCompleted.value = true;
        imGenerating.value = false;
        currentTopic.value =
          detail.topic || detail.title?.replace("[AI课程] ", "") || "历史课程";

        // 尝试加载大纲（topic 需要 slugify，与后端 _slugify 一致）
        try {
          const courseSlug =
            (currentTopic.value || "")
              .replace(/[^a-zA-Z0-9\u4e00-\u9fff]+/g, "_")
              .replace(/^_|_$/g, "")
              .slice(0, 60) || "untitled";
          const outlineRes = await fetch(
            `${BASE_URL}/api/immersive/files/courses/${encodeURIComponent(courseSlug)}/outline.json`,
          );
          if (outlineRes.ok) {
            imOutline.value = await outlineRes.json();
            imAddLog(
              `大纲已加载，共 ${imOutline.value?.chapters?.length || 0} 章`,
            );
          }
        } catch (ex) {
          console.error("加载大纲失败", ex);
        }

        // 从 files 恢复章节列表（只加载 courses/ 开头的课程 PDF，排除卡片）
        if (detail.files && detail.files.length > 0) {
          for (const f of detail.files) {
            if (
              f.file_type === "pdf" &&
              f.file_id &&
              f.file_id.startsWith("courses/")
            ) {
              const chIdx = imChapters.value.length;
              const chId = chIdx + 1;
              // file_id 格式: courses/递归算法/chapter_01/chapter_01.pdf
              const filePath = f.file_id;
              const chapterDir = filePath.replace(/\/[^/]+\.pdf$/, "");

              // 检查是否有习题
              const exPath = `${chapterDir}/chapter_${String(chId).padStart(2, "0")}_exercises.md`;
              let hasExercises = false;
              try {
                const exRes = await fetch(
                  `${BASE_URL}/api/immersive/files/${exPath}`,
                );
                hasExercises = exRes.ok;
              } catch (ex) {
                console.error("检查习题文件失败", ex);
              }

              // 检查是否有语音讲解
              const notesPath = `${chapterDir}/speaker_notes.json`;
              let audioFiles = [];
              try {
                const notesRes = await fetch(
                  `${BASE_URL}/api/immersive/files/${notesPath}`,
                );
                if (notesRes.ok) {
                  const notes = await notesRes.json();
                  if (Array.isArray(notes)) {
                    audioFiles = notes.map((_, i) => ({
                      filename: `frame_${String(i + 1).padStart(3, "0")}.wav`,
                      success: true,
                    }));
                  }
                }
              } catch (e) {
                console.error("加载 speaker_notes.json 失败", e);
              }

              imChapters.value.push({
                chapter_id: chId,
                title: f.title || `第${chId}章`, // 数据库已存完整标题，不再加"第X章"前缀
                pdf_exists: true,
                pdf_path: filePath,
                exercises_exists: hasExercises,
                exercises_path: hasExercises ? exPath : "",
                speaker_notes_count: audioFiles.length,
                audio_files: audioFiles,
                images: [],
              });
            }
          }
          // 自动选中第一章
          if (imChapters.value.length > 0) {
            await nextTick();
            await nextTick();
            imSelectChapter(0);
          }
        }
        imAddLog(
          `已恢复课程「${currentTopic.value}」，共 ${imChapters.value.length} 章`,
        );
        imTab.value = "outline"; // 默认显示大纲

        // 从持久化消息中恢复智流 Agent 对话记录
        // 后端 append_message 会保存所有消息（包含 [智流Agent] 前缀的）
        if (detail.messages && detail.messages.length > 0) {
          const agentMsgs = [];
          for (let i = 0; i < detail.messages.length; i++) {
            const m = detail.messages[i];
            if (
              m.role === "user" &&
              m.content &&
              m.content.startsWith("[智流Agent]")
            ) {
              // 提取用户原始问题（去掉 [智流Agent] 前缀和上下文信息）
              const match = m.content.match(/用户问题：(.+)$/s);
              const userText = match
                ? match[1].trim()
                : m.content.replace(/^\[智流Agent\].*?\n\n/, "");
              const timeStr = m.created_at
                ? new Date(m.created_at).toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "";
              agentMsgs.push({
                role: "user",
                content: userText,
                time: timeStr,
              });
              // 下一条应该是 assistant 回复
              if (
                i + 1 < detail.messages.length &&
                detail.messages[i + 1].role === "assistant"
              ) {
                const am = detail.messages[i + 1];
                const aTimeStr = am.created_at
                  ? new Date(am.created_at).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "";
                agentMsgs.push({
                  role: "assistant",
                  thinking: false,
                  content: am.content,
                  html: renderMd(am.content),
                  time: aTimeStr,
                });
                i++; // 跳过已处理的 assistant 消息
              }
            }
          }
          if (agentMsgs.length > 0) {
            imAgentMessages.value = agentMsgs;
            imAddLog(`已恢复 ${agentMsgs.length} 条智流 Agent 对话`);
          }
        }
      } else {
        // ── 恢复人机交互学习 ──
        phase.value = "learning";

        // 还原消息列表（assistant 消息渲染 markdown）
        messages.value = (detail.messages || []).map((m) => ({
          role: m.role,
          content: m.content,
          html: m.role === "assistant" ? renderMd(m.content) : m.content,
          time: m.created_at
            ? new Date(m.created_at).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              })
            : "",
          steps: [],
          events: [],
        }));

        // 恢复历史卡片
        if (detail.files && detail.files.length > 0) {
          await nextTick();
          await loadSessionCards(detail.files);
        }
      }

      await nextTick();
      scrollBottom();
    } catch (e) {
      console.warn("恢复会话失败:", e.message);
      if (topic) {
        topicInput.value = String(topic);
        nextTick(() => startLearning());
      }
    }
  } else if (topic) {
    topicInput.value = String(topic);
    // 如果 mode=immersive，直接启动 AI 主导学习
    if (route.query.mode === "immersive") {
      nextTick(() => startImmersive());
    } else {
      nextTick(() => startLearning());
    }
  }
});

// ── 起始页：漂浮云朵主题（V1 设计） ─────────────────────────────────
const rawSuggestions = [
  { text: "递归算法", emoji: "🌀", size: "md" },
  { text: "微积分", emoji: "∫", size: "xl" },
  { text: "机器学习", emoji: "🤖", size: "lg" },
  { text: "量子力学", emoji: "⚛️", size: "md" },
  { text: "英语写作", emoji: "✍️", size: "xs" },
  { text: "操作系统", emoji: "💻", size: "lg" },
  { text: "数据结构", emoji: "🧩", size: "sm" },
  { text: "线性代数", emoji: "📐", size: "xs" },
  { text: "编译原理", emoji: "⚙️", size: "md" },
  { text: "概率论", emoji: "🎲", size: "sm" },
  { text: "神经网络", emoji: "🧠", size: "xl" },
  { text: "哲学导论", emoji: "💭", size: "sm" },
];

const layoutPositions = [
  { top: "8%", left: "4%" },
  { top: "22%", left: "1%" },
  { top: "42%", left: "3%" },
  { top: "62%", left: "1%" },
  { top: "78%", left: "5%" },
  { top: "90%", left: "12%" },
  { top: "6%", right: "6%" },
  { top: "24%", right: "2%" },
  { top: "44%", right: "4%" },
  { top: "64%", right: "1%" },
  { top: "80%", right: "6%" },
  { top: "92%", right: "14%" },
];

// 伪随机：同档内再加一点差异，视觉不整齐划一
function pseudoRand(i, seed = 1) {
  const x = Math.sin((i + 1) * 9301 + seed * 49297) * 233280;
  return x - Math.floor(x);
}

const clouds = computed(() =>
  rawSuggestions.map((s, i) => {
    const pos = layoutPositions[i % layoutPositions.length];
    const delay = (i * 0.37) % 5;
    const dur = 6 + pseudoRand(i, 2) * 5;
    const jitter = 0.88 + pseudoRand(i, 3) * 0.28;
    const rot = (pseudoRand(i, 4) - 0.5) * 6;
    return {
      ...s,
      style: {
        ...pos,
        "--jitter": jitter,
        "--rot": `${rot}deg`,
        animationDelay: `-${delay}s`,
        animationDuration: `${dur}s`,
      },
    };
  }),
);

// ── 会话状态 ─────────────────────────────────────────────────────
const currentSessionId = ref(null);
let sessionStartTime = null; // 进入会话时记录，离开时计算时长
let sseController = null; // 用于取消 SSE 请求

async function startLearning() {
  if (!topicInput.value.trim()) return;
  currentTopic.value = topicInput.value.trim();
  phase.value = "generating";
  genStage.value = 0;
  genProgress.value = 0;

  // 进度动画（创建会话期间）
  const progressAnim = animateProgress(0, 80, 1200);

  // 创建后端会话
  try {
    const session = await sessionApi.create({ topic: currentTopic.value });
    currentSessionId.value = session.id;
    sessionStartTime = Date.now();
  } catch (e) {
    console.warn("创建会话失败:", e.message);
    phase.value = "idle";
    return;
  }

  await progressAnim;
  genStage.value = 2;
  genProgress.value = 100;
  await delay(300);

  phase.value = "learning";

  // 发送首条消息，让 Agent 开始介绍主题
  await nextTick();
  await sendMessage(
    `我想学习「${currentTopic.value}」，请先帮我介绍一下这个主题的核心内容和学习要点。`,
  );
}

function animateProgress(from, to, duration) {
  return new Promise((resolve) => {
    const step = (to - from) / (duration / 16);
    const timer = setInterval(() => {
      genProgress.value = Math.min(to, genProgress.value + step);
      if (genProgress.value >= to) {
        clearInterval(timer);
        resolve();
      }
    }, 16);
  });
}

// ── PDF 卡片（file_created 事件追加）────────────────────────────
// pdfCards: [{ fileId, title, url, thumbs: [] }]
// 注意：pdfDoc 对象不能放进 Vue 响应式（ref/reactive），否则 Proxy 会破坏 pdfjs 私有字段
const pdfCards = ref([]);
const pdfDocMap = new Map(); // fileId -> PDFDocumentProxy（原生对象，不经过 Vue 响应式）
const currentPdfIndex = ref(0);
const currentPageIndex = ref(0);
const pdfMainCanvas = ref(null);
const thumbCanvasMap = ref({}); // { pageIndex: canvasEl }

const currentCardPages = computed(() => {
  const card = pdfCards.value[currentPdfIndex.value];
  return card?.thumbs?.length ?? 0;
});

// ── 卡片音频播放 ─────────────────────────────────────────────────
const cardIsPlaying = ref(false);
let cardCurrentAudio = null;

const cardAudioUrl = computed(() => {
  const card = pdfCards.value[currentPdfIndex.value];
  if (!card?.fileId) return "";
  // fileId 可能带 .pdf 后缀（如 "xxx.pdf"），音频目录名是 "xxx_audio"
  const cardId = card.fileId.replace(/\.pdf$/i, "");
  const frameNum = String(currentPageIndex.value + 1).padStart(3, "0");
  return `${BASE_URL}/files/cards/${cardId}_audio/frame_${frameNum}.wav`;
});

function playCardAudio() {
  if (!cardAudioUrl.value) return;
  if (cardIsPlaying.value && cardCurrentAudio) {
    cardCurrentAudio.pause();
    cardIsPlaying.value = false;
    return;
  }
  if (cardCurrentAudio) cardCurrentAudio.pause();
  cardCurrentAudio = new Audio(cardAudioUrl.value);
  cardCurrentAudio.play().catch(() => {
    cardIsPlaying.value = false;
  });
  cardIsPlaying.value = true;
  cardCurrentAudio.onended = () => {
    cardIsPlaying.value = false;
  };
  cardCurrentAudio.onerror = () => {
    cardIsPlaying.value = false;
  };
}

// 切页时停止音频
watch(currentPageIndex, () => {
  if (cardCurrentAudio) {
    cardCurrentAudio.pause();
    cardCurrentAudio = null;
  }
  cardIsPlaying.value = false;
});
watch(currentPdfIndex, () => {
  if (cardCurrentAudio) {
    cardCurrentAudio.pause();
    cardCurrentAudio = null;
  }
  cardIsPlaying.value = false;
});

function setThumbCanvas(el, pi) {
  if (el) thumbCanvasMap.value[pi] = el;
}

async function addPdfCard(fileId, title) {
  console.log("[PDF] addPdfCard", fileId, title);
  const url = `${BASE_URL}/files/cards/${fileId}`;
  pdfCards.value.push({ fileId, title: title || fileId, url, thumbs: [] });
  const idx = pdfCards.value.length - 1;
  // 等 DOM 渲染（v-if="pdfCards.length > 0" 触发后 canvas 才存在）
  await nextTick();
  await nextTick(); // 双 tick 确保 canvas 完全挂载
  console.log("[PDF] nextTick 后 pdfMainCanvas=", pdfMainCanvas.value);
  await selectCard(idx);
}

async function selectCard(idx) {
  console.log("[PDF] selectCard", idx);
  currentPdfIndex.value = idx;
  currentPageIndex.value = 0;
  thumbCanvasMap.value = {};
  const card = pdfCards.value[idx];
  if (!card) return;

  // 加载 PDF，pdfDoc 存入普通 Map，不经过 Vue 响应式
  if (!pdfDocMap.has(card.fileId)) {
    try {
      console.log("[PDF] 开始加载 PDF:", card.url);
      const pdfDoc = await pdfjsLib.getDocument({
        url: card.url,
        cMapUrl: "https://unpkg.com/pdfjs-dist@5.6.205/cmaps/",
        cMapPacked: true,
      }).promise;
      console.log("[PDF] PDF 加载成功，页数:", pdfDoc.numPages);
      pdfDocMap.set(card.fileId, pdfDoc);
    } catch (e) {
      console.warn("[PDF] PDF 加载失败:", e);
      return;
    }
  }

  const pdfDoc = pdfDocMap.get(card.fileId);
  const numPages = pdfDoc.numPages;
  // 初始化 thumbs 数组（只存普通数据，不存 pdfDoc）
  pdfCards.value[idx] = { ...card, thumbs: new Array(numPages).fill(null) };

  // 先渲染主视图第1页
  await renderMainPage(card.fileId, 0);
  // 异步渲染所有缩略图
  for (let i = 0; i < numPages; i++) {
    await renderThumb(card.fileId, i, idx);
  }
}

async function gotoPage(pi) {
  currentPageIndex.value = pi;
  const card = pdfCards.value[currentPdfIndex.value];
  if (card && pdfDocMap.has(card.fileId)) await renderMainPage(card.fileId, pi);
}

async function renderMainPage(fileId, pageIndex) {
  const pdfDoc = pdfDocMap.get(fileId);
  console.log("[PDF] renderMainPage", {
    canvas: pdfMainCanvas.value,
    hasPdfDoc: !!pdfDoc,
    pageIndex,
  });
  if (!pdfMainCanvas.value || !pdfDoc) {
    console.warn(
      "[PDF] renderMainPage 跳过：canvas=",
      pdfMainCanvas.value,
      "pdfDoc=",
      pdfDoc,
    );
    return;
  }
  const page = await pdfDoc.getPage(pageIndex + 1);
  const canvas = pdfMainCanvas.value;
  const container = canvas.parentElement;
  if (!container) {
    console.warn("[PDF] canvas 没有 parentElement");
    return;
  }
  const containerW = container.clientWidth || 800;
  const containerH = container.clientHeight || 500;
  console.log("[PDF] 容器尺寸", containerW, "x", containerH);

  // 考虑设备像素比以获得更清晰的渲染
  const dpr = window.devicePixelRatio || 1;

  const viewport = page.getViewport({ scale: 1 });
  const scaleW = (containerW - 48) / viewport.width;
  const scaleH = (containerH - 48) / viewport.height;
  const scale = Math.min(scaleW, scaleH);
  const scaledVp = page.getViewport({ scale });

  // 设置canvas尺寸考虑DPI
  canvas.width = Math.round(scaledVp.width * dpr);
  canvas.height = Math.round(scaledVp.height * dpr);
  canvas.style.width = `${scaledVp.width}px`;
  canvas.style.height = `${scaledVp.height}px`;

  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);

  // 改进的渲染配置
  const renderContext = {
    canvasContext: ctx,
    viewport: scaledVp,
    // 启用文本层渲染，有助于字体显示
    enableTextLayer: true,
    // 强制使用系统字体
    useSystemFonts: true,
  };

  await page.render(renderContext).promise;
  console.log(
    "[PDF] 主视图渲染完成",
    canvas.width,
    "x",
    canvas.height,
    "DPI:",
    dpr,
  );
}

async function renderThumb(fileId, pageIndex, cardIdx) {
  const pdfDoc = pdfDocMap.get(fileId);
  if (!pdfDoc) return;
  const page = await pdfDoc.getPage(pageIndex + 1);
  // 缩略图固定宽 160px，考虑DPI
  const dpr = window.devicePixelRatio || 1;
  const viewport = page.getViewport({ scale: 1 });
  const scale = 160 / viewport.width;
  const scaledVp = page.getViewport({ scale });
  const offscreen = document.createElement("canvas");
  offscreen.width = Math.round(scaledVp.width * dpr);
  offscreen.height = Math.round(scaledVp.height * dpr);
  offscreen.style.width = `${scaledVp.width}px`;
  offscreen.style.height = `${scaledVp.height}px`;
  const ctx = offscreen.getContext("2d");
  ctx.scale(dpr, dpr);

  // 改进的渲染配置
  const renderContext = {
    canvasContext: ctx,
    viewport: scaledVp,
    // 启用文本层渲染，有助于字体显示
    enableTextLayer: true,
    // 强制使用系统字体
    useSystemFonts: true,
  };

  await page.render(renderContext).promise;
  if (pdfCards.value[cardIdx]?.fileId === fileId) {
    // 从最新的响应式对象取 thumbs（避免用旧快照）
    const newThumbs = [...(pdfCards.value[cardIdx].thumbs || [])];
    newThumbs[pageIndex] = offscreen;
    pdfCards.value[cardIdx] = { ...pdfCards.value[cardIdx], thumbs: newThumbs };
    // 等 DOM 更新后把 offscreen 内容绘制到 ts-canvas
    await nextTick();
    const thumbEl = thumbCanvasMap.value[pageIndex];
    if (thumbEl) {
      thumbEl.width = offscreen.width;
      thumbEl.height = offscreen.height;
      thumbEl.getContext("2d").drawImage(offscreen, 0, 0);
    }
  }
}

// 恢复历史会话时加载已有卡片
async function loadSessionCards(files) {
  for (const f of files) {
    if (f.file_type === "pdf") {
      await addPdfCard(f.file_id, f.title);
    }
  }
}

// 窗口 resize 时重新渲染主视图
function onWindowResize() {
  const card = pdfCards.value[currentPdfIndex.value];
  if (card && pdfDocMap.has(card.fileId))
    renderMainPage(card.fileId, currentPageIndex.value);
}

// ── 幻灯片（保留 quiz 卡片交互状态）────────────────────────────
const slides = ref([]);
const currentIndex = ref(0);

const currentSlide = computed(() => slides.value[currentIndex.value] || null);

// ── 重置 ─────────────────────────────────────────────────────────
function resetToIdle() {
  if (currentSessionId.value && sessionStartTime) {
    const minutes = Math.max(
      1,
      Math.round((Date.now() - sessionStartTime) / 60000),
    );
    sessionApi.recordDuration(currentSessionId.value, minutes).catch(() => {});
    sessionStartTime = null;
  }
  currentSessionId.value = null;
  if (sseController) {
    sseController.abort();
    sseController = null;
  }
  phase.value = "idle";
  learningMode.value = "chat";
  slides.value = [];
  pdfCards.value = [];
  currentPdfIndex.value = 0;
  currentPageIndex.value = 0;
  thumbCanvasMap.value = {};
  messages.value = [];
  currentIndex.value = 0;
  topicInput.value = "";
  genProgress.value = 0;
  genStage.value = -1;
  // AI 主导模式清理
  if (imCurrentAudio) {
    imCurrentAudio.pause();
    imCurrentAudio = null;
  }
  imGenerating.value = false;
  imCompleted.value = false;
  imProgress.value = 0;
  imCurrentStage.value = "";
  imStatusMessage.value = "";
  imOutline.value = null;
  imChapters.value = [];
  imCurrentChapterIndex.value = 0;
  imCurrentPage.value = 1;
  imTotalPages.value = 0;
  imTab.value = "log";
  imLogs.value = [];
  imIsPlaying.value = false;
  imExercisesHtml.value = "";
  imGeneratingChapterId.value = 0;
  imGeneratingChapterTitle.value = "";
  imPdfDocMap.clear();
}

onMounted(() => {
  window.addEventListener("resize", onWindowResize);
});
onUnmounted(() => {
  if (sseController) sseController.abort();
  window.removeEventListener("resize", onWindowResize);
  // 离开页面时上报本次会话学习时长
  if (currentSessionId.value && sessionStartTime) {
    const minutes = Math.max(
      1,
      Math.round((Date.now() - sessionStartTime) / 60000),
    );
    sessionApi.recordDuration(currentSessionId.value, minutes).catch(() => {});
  }
});

// ── 导出 ─────────────────────────────────────────────────────────
const isExporting = ref(false);

async function exportSlides() {
  if (isExporting.value || pdfCards.value.length === 0) return;

  // 只有一张卡片时直接下载，无需合并
  if (pdfCards.value.length === 1) {
    const a = document.createElement("a");
    a.href = pdfCards.value[0].url;
    a.download = `${pdfCards.value[0].title || "slides"}.pdf`;
    a.click();
    return;
  }

  isExporting.value = true;
  try {
    const merged = await PDFDocument.create();
    for (const card of pdfCards.value) {
      const res = await fetch(card.url);
      const bytes = await res.arrayBuffer();
      const src = await PDFDocument.load(bytes);
      const pages = await merged.copyPages(src, src.getPageIndices());
      pages.forEach((p) => merged.addPage(p));
    }
    const mergedBytes = await merged.save();
    const blob = new Blob([mergedBytes], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `${currentTopic.value || "slides"}_全部卡片.pdf`;
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 5000);
  } catch (e) {
    console.error("PDF 合并失败:", e);
    // 降级：逐个打开
    pdfCards.value.forEach((card) => window.open(card.url, "_blank"));
  } finally {
    isExporting.value = false;
  }
}
// ── 对话 ────────────────────────────────────────────────────────
const inputText = ref("");
const inputFocused = ref(false);
const isThinking = ref(false);
const isGenerating = ref(false); // AI 回复生成中（锁定发送）
const messagesRef = ref(null);
const inputBox = ref(null);
const messages = ref([]);

const contextQuicks = computed(() => {
  const type = currentSlide.value?.type;
  return (
    {
      cover: ["帮我讲解这个主题", "有哪些学习难点？", "预计要学多久？"],
      concept: ["能举个例子吗？", "这个概念的难点是什么？", "出一道相关练习题"],
      code: [
        "逐行解释这段代码",
        "有更简洁的写法吗？",
        "这段代码的复杂度是多少？",
      ],
      plan: ["哪个阶段最难？", "如何调整学习顺序？"],
      quiz: ["解释这道题的思路", "相关知识点还有哪些？"],
      summary: ["深入讲解某个知识点", "出5道综合练习题", "生成复习计划"],
    }[type] || ["帮我解释当前内容", "出一道练习题", "有什么学习建议？"]
  );
});

async function sendMessage(text) {
  if (!text.trim() || phase.value === "generating" || isGenerating.value)
    return;
  isGenerating.value = true;
  messages.value.push({ role: "user", content: text, time: now() });
  inputText.value = "";
  if (inputBox.value) inputBox.value.style.height = "auto";
  await nextTick();
  scrollBottom();

  // 添加 thinking 占位
  isThinking.value = true;
  messages.value.push({
    role: "assistant",
    thinking: true,
    content: "",
    html: "",
    time: "",
  });
  await nextTick();
  scrollBottom();

  // 有后端会话才能发送
  if (currentSessionId.value) {
    await sendWithSSE(text);
  } else {
    await sendLocal("会话未创建，请重新开始学习。");
  }

  isThinking.value = false;
  isGenerating.value = false;
  await nextTick();
  scrollBottom();
}

// 真实 SSE 流式请求
async function sendWithSSE(text) {
  return new Promise((resolve) => {
    let fullContent = "";
    const idx = messages.value.length - 1;

    // 初始化消息结构
    messages.value[idx] = {
      role: "assistant",
      thinking: false,
      content: "",
      html: "",
      time: now(),
      steps: [], // 工具调用进度
      events: [], // 业务事件标签
    };

    // 检查是否启用 debug 模式
    const debugMode = window.debug === true;
    if (debugMode) {
      console.log(
        "[DEBUG] 开始 SSE 请求，会话ID:",
        currentSessionId.value,
        "消息:",
        text,
      );
    }

    // 取消上一个请求
    if (sseController) sseController.abort();

    // 辅助：更新当前消息
    const updateMsg = (patch) => {
      messages.value[idx] = { ...messages.value[idx], ...patch };
    };

    sseController = sessionApi.streamMessage(currentSessionId.value, text, {
      onThinking: (content, step) => {
        if (debugMode) {
          console.log("[DEBUG] onThinking:", {
            step,
            content:
              content.slice(0, 100) + (content.length > 100 ? "..." : ""),
          });
        }
        // 思考步骤：更新或追加 steps 中的 thinking 条目
        const steps = [...(messages.value[idx].steps || [])];
        const existing = steps.find(
          (s) => s.type === "thinking" && s.step === step,
        );
        if (existing) {
          existing.label = `思考中：${content.slice(0, 40)}${content.length > 40 ? "…" : ""}`;
        } else {
          steps.push({
            type: "thinking",
            step,
            status: "running",
            label: `思考中：${content.slice(0, 40)}${content.length > 40 ? "…" : ""}`,
          });
        }
        updateMsg({ steps });
        scrollBottom();
      },
      onToolCall: (tool, args, step) => {
        if (debugMode) {
          console.log("[DEBUG] onToolCall:", {
            tool,
            step,
            args:
              typeof args === "string"
                ? args.slice(0, 200) + (args.length > 200 ? "..." : "")
                : args,
          });
        }
        const steps = [...(messages.value[idx].steps || [])];
        const toolLabels = {
          search_nodes: "搜索知识节点",
          get_node: "获取节点详情",
          create_node: "创建知识节点",
          update_node: "更新节点",
          update_mastery: "更新掌握度",
          create_quiz: "生成测验题",
          generate_card: "生成学习卡片",
          tavily_search: "网络搜索",
          arxiv_search: "搜索论文",
          web_fetch: "获取网页",
          read_file: "读取文件",
          list_dir: "列出目录",
        };
        steps.push({
          type: "tool",
          tool,
          step,
          status: "running",
          label: `调用工具：${toolLabels[tool] || tool}`,
        });
        updateMsg({ steps });
        scrollBottom();
      },
      onToolResult: (tool, result, step) => {
        if (debugMode) {
          console.log("[DEBUG] onToolResult:", {
            tool,
            step,
            result:
              typeof result === "string"
                ? result.slice(0, 200) + (result.length > 200 ? "..." : "")
                : result,
          });
        }
        const steps = [...(messages.value[idx].steps || [])];
        const s = steps.find(
          (s) => s.type === "tool" && s.tool === tool && s.step === step,
        );
        if (s) s.status = "done";
        // 同时把 thinking 步骤也标为 done
        steps
          .filter((s) => s.type === "thinking" && s.step === step)
          .forEach((s) => (s.status = "done"));
        updateMsg({ steps });
        // create_node 返回 created:false 时（节点已存在），也给用户一个提示
        if (tool === "create_node") {
          try {
            const data =
              typeof result === "string" ? JSON.parse(result) : result;
            if (data && data.created === false) {
              const events = [...(messages.value[idx].events || [])];
              events.push({
                type: "node_exists",
                nodeId: data.node_id,
                title: data.message?.match(/「(.+)」/)?.[1] || "",
              });
              updateMsg({ events });
            }
          } catch {
            console.error("create_node result 解析失败:", result);
          }
        }
      },
      onTextReply: (text) => {
        if (debugMode) {
          console.log("[DEBUG] onTextReply:", { text });
        }
        fullContent += text;
        updateMsg({
          content: fullContent,
          html: renderMd(fullContent),
          time: now(),
        });
        scrollBottom();
      },
      onFileCreated: (fileId) => {
        if (debugMode) {
          console.log("[DEBUG] onFileCreated:", { fileId });
        }
        // 追加 PDF 卡片到左侧展示区
        addPdfCard(fileId, `${currentTopic.value} 卡片`);
        const events = [...(messages.value[idx].events || [])];
        events.push({ type: "file_created", fileId });
        updateMsg({ events });
        // 更新 context-strip 显示
        nextTick();
      },
      onNodeCreated: (nodeId, title) => {
        if (debugMode) {
          console.log("[DEBUG] onNodeCreated:", { nodeId, title });
        }
        const events = [...(messages.value[idx].events || [])];
        events.push({ type: "node_created", nodeId, title });
        updateMsg({ events });
      },
      onMasteryUpdated: (nodeId, delta) => {
        if (debugMode) {
          console.log("[DEBUG] onMasteryUpdated:", { nodeId, delta });
        }
        const events = [...(messages.value[idx].events || [])];
        // 合并同一节点的多次更新
        const existing = events.find(
          (e) => e.type === "mastery_updated" && e.nodeId === nodeId,
        );
        if (existing) {
          existing.delta = (existing.delta || 0) + delta;
        } else {
          events.push({ type: "mastery_updated", nodeId, delta });
        }
        updateMsg({ events });
      },
      onDone: () => {
        if (debugMode) {
          console.log("[DEBUG] onDone: 请求完成");
        }
        // 把所有 running 步骤标为 done
        const steps = (messages.value[idx].steps || []).map((s) => ({
          ...s,
          status: "done",
        }));
        updateMsg({ steps });
        sseController = null;
        resolve();
      },
      onError: async (err) => {
        if (debugMode) {
          console.log("[DEBUG] onError:", { error: err.message });
        }
        console.warn("SSE 错误:", err.message);
        await sendLocal(err.message);
        resolve();
      },
    });
  });
}

// 连接失败时的错误提示
async function sendLocal(errMsg) {
  const idx = messages.value.length - 1;
  const tip =
    typeof errMsg === "string" && errMsg
      ? `连接失败：${errMsg}`
      : "连接失败，请检查后端服务是否启动。";
  messages.value[idx] = {
    role: "assistant",
    thinking: false,
    content: tip,
    html: tip,
    time: now(),
    steps: [],
    events: [],
  };
}

function scrollBottom() {
  if (messagesRef.value)
    messagesRef.value.scrollTop = messagesRef.value.scrollHeight;
}
function autoResize(e) {
  e.target.style.height = "auto";
  e.target.style.height = Math.min(e.target.scrollHeight, 100) + "px";
}
function now() {
  return new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
}
function delay(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

// ── 拖拽 ─────────────────────────────────────────────────────────
const chatWidth = ref(0); // 0 表示使用百分比（45%），拖拽后变为固定 px
const isDragging = ref(false);
let startX = 0,
  startW = 0,
  containerW = 0;
function startResize(e) {
  // 拖拽开始时先把当前实际宽度固定下来
  const panel = document.querySelector(".chat-panel");
  const wrap = document.querySelector(".learn-wrap");
  containerW = wrap ? wrap.getBoundingClientRect().width : window.innerWidth;
  if (panel) startW = panel.getBoundingClientRect().width;
  else startW = chatWidth.value || Math.round(containerW * 0.45);
  chatWidth.value = startW;
  isDragging.value = true;
  startX = e.clientX;
  document.addEventListener("mousemove", onResize);
  document.addEventListener("mouseup", stopResize);
}
function onResize(e) {
  if (!isDragging.value) return;
  // 拖拽范围：45% ± 15%，即 30% ~ 60%
  const minW = Math.round(containerW * 0.3);
  const maxW = Math.round(containerW * 0.6);
  chatWidth.value = Math.max(
    minW,
    Math.min(maxW, startW + (startX - e.clientX)),
  );
}
function stopResize() {
  isDragging.value = false;
  document.removeEventListener("mousemove", onResize);
  document.removeEventListener("mouseup", stopResize);
}
onUnmounted(() => {
  document.removeEventListener("mousemove", onResize);
  document.removeEventListener("mouseup", stopResize);
});
</script>

<style scoped>
/* ═══ AI 主导模式新增样式 ═══ */
.im-progress-wrap {
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  padding: 8px 16px;
  flex-shrink: 0;
}
.im-progress-bar {
  height: 3px;
  background: var(--bg-hover);
  border-radius: 2px;
  overflow: hidden;
}
.im-progress-fill {
  height: 100%;
  background: var(--gradient-brand);
  transition: width 0.3s ease;
}
.im-stage-indicators {
  display: flex;
  gap: 16px;
  margin-top: 6px;
  justify-content: center;
}
.im-stage-item {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-dim);
  opacity: 0.4;
  transition: all 0.3s;
}
.im-stage-item.active {
  opacity: 1;
  color: var(--brand-light);
  transform: scale(1.05);
}
.im-stage-item.done {
  opacity: 0.65;
  color: var(--text-muted);
}
.im-stage-icon {
  font-size: 14px;
}
.im-stage-name {
  font-weight: 600;
}

.im-generating {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 14px;
}
.im-gen-icon {
  font-size: 3rem;
  animation: pulse 1.5s ease infinite;
}
.im-gen-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.im-gen-topic {
  font-size: 13px;
  color: var(--brand-light);
  background: var(--brand-dim);
  padding: 3px 14px;
  border-radius: 20px;
}
.im-gen-msg {
  font-size: 12px;
  color: var(--text-muted);
}

.im-audio-btn {
  background: rgba(16, 185, 129, 0.15) !important;
  color: #10b981 !important;
  border-color: rgba(16, 185, 129, 0.3) !important;
  min-width: 28px;
}
.im-audio-btn.playing {
  background: rgba(239, 68, 68, 0.15) !important;
  color: #ef4444 !important;
}

.cs-dot.done {
  background: #10b981;
}
.cs-item.generating {
  color: var(--brand-light);
}

/* 右侧面板：大纲+习题+日志 tabs */
.im-sidebar-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
}
.im-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.im-tabs button {
  flex: 1;
  padding: 10px;
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  color: var(--text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: var(--transition);
  position: relative;
}
.im-tabs button.active {
  color: var(--brand-light);
  border-bottom-color: var(--brand);
}
.im-log-count {
  position: absolute;
  top: 4px;
  right: 8px;
  font-size: 9px;
  background: var(--brand);
  color: white;
  padding: 0 4px;
  border-radius: 8px;
  min-width: 16px;
  text-align: center;
}
.im-tab-content {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
}
.im-placeholder {
  color: var(--text-dim);
  font-size: 13px;
  text-align: center;
  padding: 40px 0;
}

.im-ex-content {
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-primary);
}
.im-ex-content h1,
.im-ex-content h2,
.im-ex-content h3 {
  font-weight: 600;
  margin: 12px 0 6px;
}
.im-ex-content code {
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
}

.im-log {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.im-log-item {
  display: flex;
  gap: 8px;
  font-size: 11px;
  padding: 3px 0;
  border-bottom: 1px solid var(--border);
}
.im-log-item.success .im-log-msg {
  color: #10b981;
}
.im-log-item.error .im-log-msg {
  color: #ef4444;
}
.im-log-time {
  color: var(--text-dim);
  flex-shrink: 0;
  font-family: monospace;
}
.im-log-msg {
  color: var(--text-secondary);
}
.chat-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-base);
  position: relative;
}

/* ══════ 主题输入态（V1 设计：云朵 + 走心文案） ══════ */
.topic-entry {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  z-index: 10;
  background: var(--bg-base);
  color: var(--text-primary);
  overflow: hidden;
}
.te-bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.025) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.025) 1px, transparent 1px);
  background-size: 42px 42px;
  mask-image: radial-gradient(ellipse at center, #000 35%, transparent 75%);
  pointer-events: none;
}
.te-bg-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  opacity: 0.22;
  pointer-events: none;
  animation: te-drift 18s ease-in-out infinite;
}
.te-bg-glow-1 {
  width: 500px;
  height: 500px;
  background: #6366f1;
  top: -100px;
  left: 10%;
}
.te-bg-glow-2 {
  width: 420px;
  height: 420px;
  background: #a855f7;
  bottom: -80px;
  right: 8%;
  animation-delay: -9s;
}
@keyframes te-drift {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }
  50% {
    transform: translate(30px, -20px) scale(1.08);
  }
}

/* 飘散云朵 */
.te-clouds {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 1;
}
.te-cloud {
  pointer-events: auto;
  position: absolute;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 10px 18px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-secondary);
  font-weight: 500;
  cursor: pointer;
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  box-shadow:
    0 8px 30px rgba(99, 102, 241, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
  transition:
    border-color 0.25s,
    color 0.25s,
    background 0.25s,
    box-shadow 0.25s;
  animation: te-float ease-in-out infinite;
  will-change: transform;
  white-space: nowrap;
  transform: scale(var(--jitter, 1)) rotate(var(--rot, 0deg));
}
.te-cloud::before {
  content: "";
  position: absolute;
  inset: 0;
  border-radius: inherit;
  background: radial-gradient(
    circle at 30% 20%,
    rgba(255, 255, 255, 0.12),
    transparent 60%
  );
  pointer-events: none;
}
.te-cloud-xs {
  font-size: 11px;
  padding: 5px 11px;
  opacity: 0.6;
}
.te-cloud-sm {
  font-size: 12.5px;
  padding: 7px 14px;
  opacity: 0.78;
}
.te-cloud-md {
  font-size: 14px;
  padding: 10px 18px;
  opacity: 0.9;
}
.te-cloud-lg {
  font-size: 16px;
  padding: 13px 24px;
  opacity: 0.95;
  font-weight: 600;
}
.te-cloud-xl {
  font-size: 19px;
  padding: 16px 30px;
  opacity: 1;
  font-weight: 700;
}
.te-cloud-xs .te-cloud-emoji {
  font-size: 13px;
}
.te-cloud-sm .te-cloud-emoji {
  font-size: 14px;
}
.te-cloud-md .te-cloud-emoji {
  font-size: 16px;
}
.te-cloud-lg .te-cloud-emoji {
  font-size: 20px;
}
.te-cloud-xl .te-cloud-emoji {
  font-size: 24px;
}
.te-cloud:hover {
  color: var(--text-primary);
  border-color: var(--border-active);
  background: var(--brand-dim);
  transform: translateY(-4px) scale(calc(var(--jitter, 1) * 1.08)) rotate(0deg) !important;
  animation-play-state: paused;
  box-shadow: 0 14px 40px rgba(99, 102, 241, 0.25);
  opacity: 1 !important;
  z-index: 3;
}
.te-cloud.active {
  color: #fff;
  background: var(--gradient-brand);
  border-color: transparent;
  box-shadow: 0 10px 32px rgba(99, 102, 241, 0.45);
  opacity: 1 !important;
}
@keyframes te-float {
  0% {
    transform: translate(0, 0) scale(var(--jitter, 1)) rotate(var(--rot, 0deg));
  }
  25% {
    transform: translate(6px, -10px) scale(var(--jitter, 1))
      rotate(var(--rot, 0deg));
  }
  50% {
    transform: translate(-4px, -16px) scale(var(--jitter, 1))
      rotate(var(--rot, 0deg));
  }
  75% {
    transform: translate(-8px, -6px) scale(var(--jitter, 1))
      rotate(var(--rot, 0deg));
  }
  100% {
    transform: translate(0, 0) scale(var(--jitter, 1)) rotate(var(--rot, 0deg));
  }
}

/* 主内容容器 */
.te-container {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 920px;
  text-align: center;
}

.te-head {
  margin-bottom: 28px;
}
.te-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  border-radius: 999px;
  background: var(--brand-dim);
  color: var(--brand-light);
  border: 1px solid var(--border-active);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.8px;
  margin-bottom: 22px;
  backdrop-filter: blur(10px);
}
.te-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-light);
  box-shadow: 0 0 8px var(--brand-light);
  animation: pulse 1.6s infinite;
}
.te-title {
  font-size: 44px;
  font-weight: 800;
  line-height: 1.25;
  letter-spacing: -1px;
  margin: 0 0 18px;
  color: var(--text-primary);
}
.te-title-grad {
  background: var(--gradient-brand);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.te-sub {
  color: var(--text-secondary);
  font-size: 15px;
  max-width: 620px;
  margin: 0 auto;
  line-height: 1.9;
}
.te-sub em {
  color: var(--brand-light);
  font-style: normal;
  font-weight: 600;
}
.te-sub-2 {
  margin-top: 12px;
  color: var(--text-muted);
  font-size: 14px;
  font-style: italic;
}

/* 输入框 */
.te-input-wrap {
  margin: 32px auto 36px;
  max-width: 640px;
  display: flex;
  align-items: center;
  gap: 14px;
  background: var(--bg-card);
  border: 1.5px solid var(--border);
  border-radius: 18px;
  padding: 16px 20px;
  transition: var(--transition);
  backdrop-filter: blur(14px);
  box-shadow: 0 10px 40px rgba(0, 0, 0, 0.2);
}
.te-input-wrap.focused,
.te-input-wrap.filled {
  border-color: var(--border-active);
  box-shadow:
    0 0 0 5px rgba(99, 102, 241, 0.12),
    0 12px 40px rgba(99, 102, 241, 0.15);
}
.te-input-ico {
  color: var(--brand-light);
  display: flex;
}
.te-input {
  flex: 1;
  background: transparent;
  border: 0;
  outline: 0;
  color: var(--text-primary);
  font-size: 17px;
  font-family: inherit;
  font-weight: 500;
}
.te-input::placeholder {
  color: var(--text-dim);
  font-weight: 400;
  font-style: italic;
}
.te-input-hint {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  color: var(--text-muted);
  padding: 5px 12px;
  border-radius: 999px;
  background: var(--bg-hover);
  white-space: nowrap;
}
.te-input-hint.ok {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
}

/* 两个模式卡片 */
.te-modes {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
  text-align: left;
}
.te-mode {
  all: unset;
  cursor: pointer;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 30px;
  background: var(--bg-card);
  border: 1.5px solid var(--border);
  border-radius: 22px;
  transition: var(--transition);
  overflow: hidden;
  backdrop-filter: blur(14px);
}
.te-mode::before {
  content: "";
  position: absolute;
  inset: 0;
  background: radial-gradient(
    circle at top right,
    var(--brand-dim),
    transparent 60%
  );
  opacity: 0;
  transition: opacity 0.3s;
  pointer-events: none;
}
.te-mode:not(:disabled):hover {
  border-color: var(--border-active);
  transform: translateY(-6px);
  box-shadow: 0 24px 70px rgba(99, 102, 241, 0.2);
}
.te-mode:not(:disabled):hover::before {
  opacity: 1;
}
.te-mode:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.te-mode.ready {
  border-color: var(--border-hover);
}
.te-mode-b::before {
  background: radial-gradient(
    circle at top right,
    rgba(168, 85, 247, 0.22),
    transparent 60%
  );
}
.te-mode-icon {
  width: 54px;
  height: 54px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  background: var(--brand-dim);
  border: 1px solid var(--border-active);
}
.te-mode-b .te-mode-icon {
  background: rgba(168, 85, 247, 0.14);
  border-color: rgba(168, 85, 247, 0.45);
}
.te-mode-title {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  display: flex;
  align-items: center;
  gap: 10px;
  letter-spacing: -0.3px;
}
.te-mode-tag {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 9px;
  border-radius: 999px;
  background: var(--bg-hover);
  color: var(--text-secondary);
  letter-spacing: 0.5px;
}
.te-mode-tag.hot {
  background: linear-gradient(135deg, #f59e0b, #ef4444);
  color: #fff;
}
.te-mode-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
}
.te-mode-feats {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
}
.te-mode-feats li {
  font-size: 12.5px;
  color: var(--text-muted);
  line-height: 1.6;
}
.te-mode-cta {
  margin-top: auto;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 11px 18px;
  border-radius: 12px;
  background: var(--bg-hover);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 600;
  align-self: flex-start;
  transition: var(--transition);
}
.te-mode.ready .te-mode-cta {
  background: var(--gradient-brand);
  color: #fff;
  box-shadow: 0 6px 24px rgba(99, 102, 241, 0.4);
}
.te-mode.ready .te-mode-cta.alt {
  background: linear-gradient(135deg, #8b5cf6, #a855f7);
  box-shadow: 0 6px 24px rgba(168, 85, 247, 0.4);
}

.te-foot {
  margin-top: 36px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
  letter-spacing: 0.5px;
  font-style: italic;
}

/* 响应式 */
@media (max-width: 960px) {
  .te-clouds {
    opacity: 0.55;
  }
  .te-cloud-xs,
  .te-cloud-sm {
    display: none;
  }
}
@media (max-width: 760px) {
  .te-modes {
    grid-template-columns: 1fr;
  }
  .te-title {
    font-size: 30px;
  }
  .te-clouds {
    display: none;
  }
  .te-sub br {
    display: none;
  }
}

/* ══════ 学习状态包裹 ══════ */
.learn-wrap {
  display: flex;
  width: 100%;
  height: 100%;
}

/* ══════ 左侧展示区 ══════ */
.slide-panel {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.slide-toolbar {
  height: 52px;
  background: var(--bg-panel);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  flex-shrink: 0;
  gap: 12px;
}
.st-left {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}
.st-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.back-btn {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
  flex-shrink: 0;
}
.back-btn:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}

.st-topic-badge {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}
.st-topic-icon {
  font-size: 15px;
  flex-shrink: 0;
}
.st-topic-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.st-nav {
  display: flex;
  align-items: center;
  gap: 6px;
}
.nav-btn {
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
.nav-btn:hover:not(:disabled) {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}
.nav-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.slide-counter {
  font-size: 12px;
  color: var(--text-muted);
  min-width: 36px;
  text-align: center;
}

.export-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  transition: var(--transition);
}
.export-btn:hover:not(:disabled) {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}
.export-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}
.spin-icon {
  animation: spin 0.8s linear infinite;
}

/* 卡片舞台 */
.slide-stage {
  flex: 1;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 32px;
  position: relative;
}

/* 连接中骨架 */
.outline-generating {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  max-width: 560px;
}
.og-header {
  display: flex;
  align-items: center;
  gap: 14px;
}
.og-spinner {
  position: relative;
  width: 44px;
  height: 44px;
  flex-shrink: 0;
}
.og-ring {
  position: absolute;
  inset: -5px;
  border-radius: 50%;
  border: 2px solid transparent;
  border-top-color: var(--brand);
  border-right-color: var(--brand-light);
  animation: spin 1.5s linear infinite;
}
.og-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 3px;
}
.og-sub {
  font-size: 12px;
  color: var(--text-muted);
}

.gen-progress-bar {
  height: 3px;
  background: var(--bg-hover);
  border-radius: var(--radius-full);
  overflow: hidden;
}
.gen-progress-fill {
  height: 100%;
  background: var(--gradient-brand);
  border-radius: var(--radius-full);
  transition: width 0.3s ease;
}

/* 无卡片空状态 */
.no-card-hint {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  text-align: center;
  padding: 40px;
}
.nch-icon {
  font-size: 48px;
  opacity: 0.4;
}
.nch-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text-muted);
}
.nch-desc {
  font-size: 13px;
  color: var(--text-dim);
  line-height: 1.8;
  max-width: 320px;
}

/* PDF 主展示区 */
.pdf-main-view {
  width: 100%;
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  position: relative;
  gap: 10px;
}
.pdf-main-canvas {
  max-width: 100%;
  max-height: calc(100% - 40px);
  border-radius: var(--radius-lg);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.3);
  background: #fff;
  display: block;
}
.pdf-page-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-full);
  padding: 4px 10px;
}
.ppn-btn {
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
}
.ppn-btn:hover:not(:disabled) {
  background: var(--brand-dim);
  color: var(--brand-light);
}
.ppn-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.ppn-label {
  font-size: 11px;
  color: var(--text-muted);
  min-width: 36px;
  text-align: center;
}

/* 缩略图行 */
.thumb-strip {
  height: 100px;
  background: var(--bg-panel);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  overflow: hidden;
}
.ts-scroll {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  height: 100%;
  overflow-x: auto;
}
.ts-scroll::-webkit-scrollbar {
  height: 3px;
}
.ts-scroll::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 2px;
}
.ts-thumb {
  flex-shrink: 0;
  cursor: pointer;
  border-radius: 6px;
  border: 2px solid transparent;
  overflow: hidden;
  transition: var(--transition);
  position: relative;
  background: var(--bg-hover);
}
.ts-thumb:hover {
  border-color: var(--border-active);
}
.ts-thumb.active {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
}
.ts-canvas {
  display: block;
  height: 72px;
  width: auto;
}
.ts-page {
  position: absolute;
  bottom: 2px;
  right: 4px;
  font-size: 9px;
  color: rgba(255, 255, 255, 0.8);
  background: rgba(0, 0, 0, 0.45);
  padding: 1px 4px;
  border-radius: 3px;
}
.ts-loading {
  width: 120px;
  height: 80px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: default;
}
.ts-spinner {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 2px solid var(--border);
  border-top-color: var(--brand);
  animation: spin 0.8s linear infinite;
}

/* 底部选卡栏 */
.card-selector {
  height: 44px;
  background: var(--bg-base);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  overflow: hidden;
}
.cs-scroll {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 5px 10px;
  height: 100%;
  overflow-x: auto;
}
.cs-scroll::-webkit-scrollbar {
  height: 2px;
}
.cs-item {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition);
  white-space: nowrap;
  flex-shrink: 0;
  border: 1px solid transparent;
  font-size: 12px;
  color: var(--text-muted);
}
.cs-item:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}
.cs-item.active {
  background: var(--brand-dim);
  border-color: var(--border-active);
  color: var(--brand-light);
}
.cs-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--text-dim);
  flex-shrink: 0;
}
.cs-item.active .cs-dot {
  background: var(--brand-light);
}
.cs-label {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cs-pages {
  font-size: 10px;
  color: var(--text-dim);
  background: var(--bg-hover);
  padding: 1px 5px;
  border-radius: 3px;
}

.gen-pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--brand);
  animation: pulse 1.2s ease infinite;
}

/* 时间线导航（已替换为 card-selector，保留备用） */

/* ══════ 分隔线 ══════ */
.resizer {
  width: 4px;
  flex-shrink: 0;
  background: var(--border);
  cursor: ew-resize;
  transition: background 0.15s;
}
.resizer:hover,
.resizer.dragging {
  background: var(--brand);
}

/* ══════ 右侧对话区 ══════ */
.chat-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border-left: 1px solid var(--border);
  overflow: hidden;
  flex-shrink: 0;
}

.agent-topbar {
  height: 52px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 14px;
  flex-shrink: 0;
}
.at-agent {
  display: flex;
  align-items: center;
  gap: 10px;
}
.at-avatar-wrap {
  position: relative;
  width: 34px;
  height: 34px;
}
.at-avatar-ring {
  position: absolute;
  inset: -3px;
  border-radius: 50%;
  background: var(--gradient-brand);
  opacity: 0.25;
  animation: spin 5s linear infinite;
}
.at-avatar-ring.active {
  opacity: 0.6;
  animation-duration: 1.5s;
}
.at-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.at-status {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 11px;
  color: var(--text-muted);
}
.at-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--green);
  flex-shrink: 0;
}
.at-dot.thinking {
  background: var(--yellow);
  animation: pulse 1s ease infinite;
}
.at-btn {
  width: 28px;
  height: 28px;
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
.at-btn:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}

.context-strip {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 14px;
  background: var(--bg-hover);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  font-size: 11px;
}
.cs-title {
  color: var(--text-primary);
  font-weight: 500;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.cs-hint {
  color: var(--text-dim);
  white-space: nowrap;
}

.messages-flow {
  flex: 1;
  overflow-y: auto;
  padding: 14px 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.welcome-flow {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  padding: 16px;
}
.wf-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.8;
}
.wf-text strong {
  color: var(--brand-light);
}
.quick-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  width: 100%;
}
.quick-item {
  padding: 7px 11px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  text-align: left;
  transition: var(--transition);
}
.quick-item:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}

.msg-row {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  margin-bottom: 12px;
}
.msg-row.user {
  flex-direction: row-reverse;
}
.msg-col {
  display: flex;
  flex-direction: column;
  gap: 3px;
  max-width: 85%;
}
.msg-row.user .msg-col {
  align-items: flex-end;
}
.msg-bubble {
  padding: 9px 12px;
  border-radius: 13px;
  font-size: 13px;
  line-height: 1.75;
}
.msg-bubble.assistant {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
  padding: 10px 16px;
}
.msg-bubble.user {
  background: var(--gradient-brand);
  color: white;
  border-bottom-right-radius: 4px;
}

/* 工具调用进度 */
.msg-steps {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 6px;
}
.ms-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  color: var(--text-dim);
}
.ms-item.done {
  color: var(--text-muted);
}
.ms-item.running {
  color: var(--brand-light);
}
.ms-icon {
  width: 14px;
  height: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.ms-spin {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid var(--brand-light);
  border-top-color: transparent;
  animation: spin 0.7s linear infinite;
  display: inline-block;
}

/* 业务事件标签 */
.msg-events {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}
.me-tag {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 4px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-muted);
}
.me-tag.node_created {
  background: rgba(99, 102, 241, 0.08);
  border-color: rgba(99, 102, 241, 0.2);
  color: var(--brand-light);
}
.me-tag.node_exists {
  background: rgba(107, 114, 128, 0.08);
  border-color: rgba(107, 114, 128, 0.2);
  color: var(--text-dim);
}
.me-tag.file_created {
  background: rgba(16, 185, 129, 0.08);
  border-color: rgba(16, 185, 129, 0.2);
  color: #10b981;
}
.me-tag.mastery_updated {
  background: rgba(245, 158, 11, 0.08);
  border-color: rgba(245, 158, 11, 0.2);
  color: #f59e0b;
}

.msg-meta {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-wrap: wrap;
}
.msg-card-tag {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  color: var(--brand-light);
  background: var(--brand-dim);
  padding: 1px 6px;
  border-radius: 4px;
}
.msg-time {
  font-size: 10px;
  color: var(--text-dim);
}

.typing-dots {
  display: flex;
  gap: 4px;
  padding: 3px 0;
  align-items: center;
}
.typing-dots span {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--brand-light);
  display: inline-block;
}
.typing-dots span:nth-child(1) {
  animation: typing 1.2s ease infinite 0s;
}
.typing-dots span:nth-child(2) {
  animation: typing 1.2s ease infinite 0.2s;
}
.typing-dots span:nth-child(3) {
  animation: typing 1.2s ease infinite 0.4s;
}

.quick-bar {
  display: flex;
  gap: 5px;
  padding: 8px 12px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  flex-wrap: wrap;
}
.qb-chip {
  padding: 4px 10px;
  border-radius: var(--radius-full);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
  transition: var(--transition);
}
.qb-chip:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}

.input-zone {
  padding: 10px 12px 14px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.iz-input-wrap {
  display: flex;
  align-items: flex-end;
  gap: 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 8px 8px 8px 13px;
  transition: var(--transition);
}
.iz-input-wrap.focused {
  border-color: var(--border-active);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}
.iz-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.6;
  resize: none;
  font-family: inherit;
  max-height: 100px;
}
.iz-input::placeholder {
  color: var(--text-dim);
}
.iz-input:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.iz-send {
  width: 30px;
  height: 30px;
  border-radius: 7px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
  flex-shrink: 0;
}
.iz-send.active {
  background: var(--gradient-brand);
  border-color: transparent;
  color: white;
  box-shadow: 0 2px 10px rgba(99, 102, 241, 0.4);
}

.iz-hint {
  font-size: 10px;
  color: var(--text-dim);
  text-align: center;
  margin-top: 5px;
}

/* ══════ 动画 ══════ */
.card-slide-enter-active,
.card-slide-leave-active {
  transition: all 0.24s cubic-bezier(0.4, 0, 0.2, 1);
}
.card-slide-enter-from {
  opacity: 0;
  transform: translateX(18px) scale(0.98);
}
.card-slide-leave-to {
  opacity: 0;
  transform: translateX(-14px) scale(0.98);
}

.fade-up-enter-active,
.fade-up-leave-active {
  transition: all 0.26s ease;
}
.fade-up-enter-from {
  opacity: 0;
  transform: translateY(8px);
}
.fade-up-leave-to {
  opacity: 0;
}

.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ══════ Markdown 渲染 ══════ */
.msg-bubble.assistant .msg-text {
  line-height: 1.7;
}
.msg-bubble.assistant .msg-text p {
  margin: 0 0 8px;
}
.msg-bubble.assistant .msg-text p:last-child {
  margin-bottom: 0;
}
.msg-bubble.assistant .msg-text h1,
.msg-bubble.assistant .msg-text h2,
.msg-bubble.assistant .msg-text h3 {
  font-weight: 600;
  margin: 12px 0 6px;
  line-height: 1.4;
}
.msg-bubble.assistant .msg-text h1 {
  font-size: 15px;
}
.msg-bubble.assistant .msg-text h2 {
  font-size: 14px;
}
.msg-bubble.assistant .msg-text h3 {
  font-size: 13px;
}
.msg-bubble.assistant .msg-text ul,
.msg-bubble.assistant .msg-text ol {
  padding-left: 18px;
  margin: 6px 0;
}
.msg-bubble.assistant .msg-text li {
  margin: 3px 0;
}
.msg-bubble.assistant .msg-text code {
  background: rgba(99, 102, 241, 0.15);
  color: #a5b4fc;
  padding: 1px 5px;
  border-radius: 4px;
  font-size: 12px;
  font-family: "JetBrains Mono", monospace;
}
.msg-bubble.assistant .msg-text pre {
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 12px;
  margin: 8px 0;
  overflow-x: auto;
}
.msg-bubble.assistant .msg-text pre code {
  background: none;
  color: #e2e8f0;
  padding: 0;
  font-size: 12px;
}
.msg-bubble.assistant .msg-text blockquote {
  border-left: 3px solid var(--brand-light);
  padding-left: 10px;
  margin: 8px 0;
  color: var(--text-muted);
  font-style: italic;
}
.msg-bubble.assistant .msg-text strong {
  font-weight: 600;
  color: var(--text-primary);
}
.msg-bubble.assistant .msg-text em {
  color: var(--text-muted);
}
.msg-bubble.assistant .msg-text a {
  color: var(--brand-light);
  text-decoration: underline;
}
.msg-bubble.assistant .msg-text hr {
  border: none;
  border-top: 1px solid var(--border);
  margin: 10px 0;
}
.msg-bubble.assistant .msg-text table {
  border-collapse: collapse;
  width: 100%;
  margin: 8px 0;
  font-size: 12px;
}
.msg-bubble.assistant .msg-text th,
.msg-bubble.assistant .msg-text td {
  border: 1px solid var(--border);
  padding: 5px 8px;
  text-align: left;
}
.msg-bubble.assistant .msg-text th {
  background: var(--bg-hover);
  font-weight: 600;
}

/* ═══ 智流 Agent 对话 ═══ */
.im-agent-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  margin: -14px;
}
.im-agent-messages {
  flex: 1;
  overflow-y: auto;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.im-agent-welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 30px 0;
  text-align: center;
  flex: 1;
}
.im-agent-welcome-icon {
  font-size: 36px;
}
.im-agent-welcome-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--text-primary);
}
.im-agent-welcome-desc {
  font-size: 12px;
  color: var(--text-muted);
}
.im-agent-quick-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
  width: 100%;
  margin-top: 8px;
}
.im-agent-quick {
  padding: 7px 11px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-secondary);
  font-size: 11px;
  cursor: pointer;
  text-align: left;
  transition: var(--transition);
}
.im-agent-quick:hover {
  background: var(--brand-dim);
  color: var(--brand-light);
  border-color: var(--border-active);
}

.im-agent-msg {
  display: flex;
  align-items: flex-end;
  gap: 6px;
}
.im-agent-msg.user {
  flex-direction: row-reverse;
}
.im-agent-msg-bubble {
  padding: 8px 11px;
  border-radius: 12px;
  font-size: 12px;
  line-height: 1.7;
  max-width: 88%;
}
.im-agent-msg-bubble.assistant {
  background: var(--bg-card);
  border: 1px solid var(--border);
  color: var(--text-primary);
  border-bottom-left-radius: 4px;
}
.im-agent-msg-bubble.user {
  background: var(--gradient-brand);
  color: white;
  border-bottom-right-radius: 4px;
}
.im-agent-msg-bubble .msg-text {
  font-size: 12px;
}

.im-agent-input-zone {
  padding: 8px 10px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.im-agent-input-wrap {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 6px 6px 6px 10px;
}
.im-agent-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-primary);
  font-size: 12px;
  line-height: 1.5;
  resize: none;
  font-family: inherit;
  max-height: 80px;
}
.im-agent-input::placeholder {
  color: var(--text-dim);
}
.im-agent-send {
  width: 26px;
  height: 26px;
  border-radius: 6px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  color: var(--text-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: var(--transition);
  flex-shrink: 0;
}
.im-agent-send.active {
  background: var(--gradient-brand);
  border-color: transparent;
  color: white;
}

/* ═══ 习题美化 ═══ */
.im-quiz-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.imq-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.imq-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0;
}
.imq-stats {
  display: flex;
  gap: 8px;
}
.imq-stat {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 10px;
}
.imq-stat.correct {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
}
.imq-stat.wrong {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

/* ── 进度条 ── */
.imq-progress-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
}
.imq-progress-dots {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}
.imq-dot {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--bg-hover);
  border: 2px solid var(--border);
  color: var(--text-muted);
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s;
}
.imq-dot.active {
  border-color: var(--brand);
  background: var(--brand-dim);
  color: var(--brand-light);
}
.imq-dot.answered {
  background: var(--brand);
  border-color: var(--brand);
  color: white;
}
.imq-progress-text {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

/* ── 题目卡片 ── */
.imq-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 18px;
}
.imq-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.imq-card-type {
  font-size: 10px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.imq-card-type.choice {
  background: rgba(99, 102, 241, 0.12);
  color: #6366f1;
}
.imq-card-type.fill {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
}
.imq-card-type.text {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
}
.imq-card-section {
  font-size: 11px;
  color: var(--text-muted);
  flex: 1;
  text-align: center;
}
.imq-card-num {
  font-size: 11px;
  color: var(--text-muted);
}
.imq-card-question {
  font-size: 14px;
  color: var(--text-primary);
  line-height: 1.8;
  margin-bottom: 16px;
}
.imq-card-question p {
  margin: 0;
}

/* ── 选项 ── */
.imq-card-options {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}
.imq-card-opt {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  border-radius: var(--radius-sm);
  border: 1.5px solid var(--border);
  cursor: pointer;
  transition: all 0.2s;
}
.imq-card-opt:hover {
  background: var(--bg-hover);
  border-color: var(--border-active);
  transform: translateX(2px);
}
.imq-card-opt.selected {
  border-color: var(--brand);
  background: var(--brand-dim);
  box-shadow: 0 0 0 1px var(--brand);
}
.imq-card-opt-letter {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--bg-hover);
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 700;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.2s;
}
.imq-card-opt-letter.selected {
  background: var(--brand);
  color: white;
}
.imq-card-opt-text {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  padding-top: 2px;
}
.imq-card-opt-text p {
  margin: 0;
}

/* ── 填空/简答输入 ── */
.imq-card-input textarea {
  width: 100%;
  background: var(--bg-base);
  border: 1.5px solid var(--border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
  color: var(--text-primary);
  font-size: 13px;
  font-family: inherit;
  resize: vertical;
  outline: none;
  transition: border-color 0.2s;
  margin-bottom: 16px;
}
.imq-card-input textarea:focus {
  border-color: var(--brand);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

/* ── 翻页 ── */
.imq-card-nav {
  display: flex;
  justify-content: space-between;
  gap: 10px;
}
.imq-nav-btn {
  padding: 8px 18px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.imq-nav-btn:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-active);
}
.imq-nav-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.imq-nav-btn.primary {
  background: var(--brand);
  border-color: var(--brand);
  color: white;
}
.imq-nav-btn.primary:hover:not(:disabled) {
  opacity: 0.9;
}
.imq-nav-btn.submit {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
  color: white;
  padding: 10px 22px;
  font-size: 13px;
  font-weight: 600;
  border-radius: var(--radius-md);
}
.imq-nav-btn.submit:hover:not(:disabled) {
  opacity: 0.92;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(99, 102, 241, 0.3);
}
.imq-unanswered-hint {
  text-align: center;
  font-size: 11px;
  color: #f59e0b;
  margin-top: 8px;
}

/* ── 判分结果页 ── */
.imq-result {
  animation: fadein 0.3s ease;
}
@keyframes fadein {
  from {
    opacity: 0;
    transform: translateY(8px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.imq-result-summary {
  text-align: center;
  padding: 20px 0;
  margin-bottom: 16px;
}
.imq-score-circle {
  display: inline-flex;
  align-items: baseline;
  gap: 2px;
  margin-bottom: 6px;
}
.imq-score-num {
  font-size: 42px;
  font-weight: 800;
}
.imq-score-total {
  font-size: 16px;
  font-weight: 500;
  color: var(--text-muted);
}
.imq-score-circle.great .imq-score-num {
  color: #10b981;
}
.imq-score-circle.good .imq-score-num {
  color: #6366f1;
}
.imq-score-circle.low .imq-score-num {
  color: #ef4444;
}
.imq-score-label {
  font-size: 16px;
  margin-bottom: 10px;
}
.imq-score-bar {
  display: flex;
  justify-content: center;
  gap: 16px;
}

.imq-result-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 16px;
}
.imq-result-item {
  padding: 14px;
  border-radius: var(--radius-lg);
  background: var(--bg-card);
  border: 1px solid var(--border);
}
.imq-result-item.correct {
  border-left: 3px solid #10b981;
}
.imq-result-item.wrong {
  border-left: 3px solid #ef4444;
}
.imq-result-num {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.icon-correct {
  color: #10b981;
}
.icon-wrong {
  color: #ef4444;
}
.imq-result-question {
  font-size: 13px;
  color: var(--text-primary);
  line-height: 1.7;
  margin-bottom: 8px;
}
.imq-result-question p {
  margin: 0;
}
.imq-result-answer,
.imq-result-correct {
  font-size: 12px;
  margin-bottom: 4px;
}
.imq-result-answer .label,
.imq-result-correct .label {
  color: var(--text-muted);
}
.imq-result-answer .value {
  color: var(--text-primary);
  font-weight: 500;
}
.imq-result-correct .value {
  color: #10b981;
  font-weight: 600;
}
.imq-result-feedback {
  margin-top: 8px;
  padding: 8px 12px;
  border-radius: var(--radius-sm);
  background: var(--bg-hover);
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.imq-result-feedback p {
  margin: 0;
}

/* ── AI 学习建议 ── */
.imq-result-advice {
  margin-top: 14px;
  padding: 14px;
  border-radius: var(--radius-lg);
  background: linear-gradient(
    135deg,
    rgba(99, 102, 241, 0.06),
    rgba(139, 92, 246, 0.06)
  );
  border: 1px solid rgba(99, 102, 241, 0.15);
}
.imq-advice-title {
  font-size: 13px;
  font-weight: 700;
  color: #6366f1;
  margin-bottom: 8px;
}
.imq-advice-content {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.8;
}
.imq-advice-content p {
  margin: 0 0 6px 0;
}

/* ── 重做 ── */
.imq-retry-btn {
  display: block;
  margin: 16px auto 0;
  padding: 10px 28px;
  border-radius: var(--radius-md);
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.imq-retry-btn:hover {
  background: var(--bg-hover);
  border-color: var(--border-active);
}
</style>
