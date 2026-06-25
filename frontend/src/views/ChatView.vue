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
              AI Learning Agent
            </div>
            <h1 class="te-title">
              今天，<span class="te-title-grad">想搞懂什么？</span>
            </h1>
            <p class="te-sub">
              输入任意主题，Agent 会陪你把它<em>真正学透</em>。
            </p>
          </header>

          <!-- 输入框 -->
          <div
            class="te-input-wrap"
            :class="{ focused: topicFocused, filled: topicInput.trim() }"
          >
            <div class="te-input-ico">
              <svg
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
            </div>
            <input
              ref="topicInputEl"
              v-model="topicInput"
              class="te-input"
              placeholder="例如：傅里叶变换、TCP/IP 协议、期权定价..."
              autofocus
              @focus="topicFocused = true"
              @blur="topicFocused = false"
            />
            <transition name="hint-fade">
              <button
                v-if="topicInput.trim()"
                class="te-input-clear"
                @click="topicInput = ''"
              >
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
            </transition>
          </div>

          <!-- 模式切换 -->
          <div class="te-mode-switch">
            <!-- Tab 选择器 -->
            <div class="te-tabs">
              <button
                class="te-tab"
                :class="{ active: selectedMode === 'chat' }"
                @click="selectedMode = 'chat'"
              >
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <path
                    d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
                  />
                </svg>
                自由对话
              </button>
              <button
                class="te-tab"
                :class="{ active: selectedMode === 'immersive' }"
                @click="selectedMode = 'immersive'"
              >
                <svg
                  width="15"
                  height="15"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <rect x="2" y="3" width="20" height="14" rx="2" />
                  <line x1="8" y1="21" x2="16" y2="21" />
                  <line x1="12" y1="17" x2="12" y2="21" />
                </svg>
                沉浸课程
                <span class="te-tab-hot">HOT</span>
              </button>
              <div class="te-tab-indicator" :class="`ind-${selectedMode}`" />
            </div>

            <!-- 模式详情面板 -->
            <transition name="te-panel" mode="out-in">
              <!-- 自由对话 -->
              <div
                v-if="selectedMode === 'chat'"
                key="chat"
                class="te-panel te-panel-a"
              >
                <div class="te-panel-feats">
                  <div class="te-panel-feat">
                    <div class="te-panel-feat-icon">💬</div>
                    <div class="te-panel-feat-title">自由节奏</div>
                    <div class="te-panel-feat-desc">随时发问，即时回应</div>
                  </div>
                  <div class="te-panel-feat">
                    <div class="te-panel-feat-icon">🧩</div>
                    <div class="te-panel-feat-title">知识卡片</div>
                    <div class="te-panel-feat-desc">自动凝结成卡片</div>
                  </div>
                  <div class="te-panel-feat">
                    <div class="te-panel-feat-icon">🗺️</div>
                    <div class="te-panel-feat-title">知识地图</div>
                    <div class="te-panel-feat-desc">构建专属知识体系</div>
                  </div>
                </div>
                <button
                  class="te-start-btn te-start-a"
                  :disabled="!topicInput.trim()"
                  @click="startLearning"
                >
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                  >
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                  开始对话
                </button>
              </div>

              <!-- 沉浸课程 -->
              <div v-else key="immersive" class="te-panel te-panel-b">
                <div class="te-panel-feats">
                  <div class="te-panel-feat">
                    <div class="te-panel-feat-icon">📚</div>
                    <div class="te-panel-feat-title">完整大纲</div>
                    <div class="te-panel-feat-desc">由浅入深的课程规划</div>
                  </div>
                  <div class="te-panel-feat">
                    <div class="te-panel-feat-icon">🎧</div>
                    <div class="te-panel-feat-title">语音讲解</div>
                    <div class="te-panel-feat-desc">随时随地听课</div>
                  </div>
                  <div class="te-panel-feat">
                    <div class="te-panel-feat-icon">✍️</div>
                    <div class="te-panel-feat-title">配套习题</div>
                    <div class="te-panel-feat-desc">自动出题检验掌握</div>
                  </div>
                </div>
                <div class="te-options">
                  <label class="te-option-toggle">
                    <input v-model="enableAudio" type="checkbox" />
                    <span class="te-option-label">🔊 生成语音讲解</span>
                    <span class="te-option-hint">逐页讲稿 + 音频</span>
                  </label>
                  <label class="te-option-toggle">
                    <input v-model="enableExercises" type="checkbox" />
                    <span class="te-option-label">✏️ 生成配套习题</span>
                    <span class="te-option-hint">自动出题检验掌握</span>
                  </label>
                </div>
                <button
                  class="te-start-btn te-start-b"
                  :disabled="!topicInput.trim()"
                  @click="
                    $router.push({
                      path: '/immersive',
                      query: {
                        topic: topicInput.trim(),
                        enable_audio: enableAudio ? '1' : '0',
                        enable_exercises: enableExercises ? '1' : '0',
                      },
                    })
                  "
                >
                  <svg
                    width="15"
                    height="15"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                  >
                    <polyline points="9 18 15 12 9 6" />
                  </svg>
                  开始课程
                </button>
              </div>
            </transition>
          </div>

          <!-- 推荐主题快捷选 -->
          <div class="te-suggestions">
            <span class="te-sug-label">试试看</span>
            <button
              v-for="c in clouds.slice(0, 6)"
              :key="c.text"
              class="te-sug-chip"
              :class="{ active: topicInput === c.text }"
              @click="topicInput = c.text"
            >
              {{ c.emoji }} {{ c.text }}
            </button>
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
              <button class="back-btn" title="重新选择主题" @click="handleBack">
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
                <span class="st-topic-icon">🎓</span>
                <span class="st-topic-name">{{ currentTopic }}</span>
              </div>
              <!-- 人机交互模式 badge -->
              <span v-if="phase === 'generating'" class="badge badge-brand">
                <span class="gen-pulse" /> 连接中
              </span>
              <span
                v-else-if="cards.filter((c) => !c.loading).length > 0"
                class="badge badge-green"
              >
                {{ cards.filter((c) => !c.loading).length }} 张卡片
              </span>
            </div>
            <div class="st-right">
              <!-- 卡片导航 -->
              <div
                v-if="cards.filter((c) => !c.loading).length > 1"
                class="st-nav"
              >
                <button
                  class="nav-btn"
                  :disabled="currentCardIndex === 0"
                  @click="selectCard(currentCardIndex - 1)"
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
                  >{{ currentCardIndex + 1 }} /
                  {{ cards.filter((c) => !c.loading).length }}</span
                >
                <button
                  class="nav-btn"
                  :disabled="currentCardIndex === cards.length - 1"
                  @click="selectCard(currentCardIndex + 1)"
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
            </div>
          </div>

          <!-- 卡片舞台 -->
          <div class="slide-stage">
            <!-- ═══ 人机交互模式内容 ═══ -->
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
              v-else-if="cards.length === 0 && phase === 'learning'"
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

            <!-- 所有卡片都在生成中（占位状态） -->
            <div
              v-else-if="cards.length > 0 && cards.every((c) => c.loading)"
              class="no-card-hint"
            >
              <div class="nch-icon" style="font-size: 36px; opacity: 1">
                <svg
                  width="36"
                  height="36"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="var(--brand-light)"
                  stroke-width="1.5"
                  style="animation: spin 1.5s linear infinite"
                >
                  <path d="M21 12a9 9 0 11-6.219-8.56" />
                </svg>
              </div>
              <div class="nch-title" style="color: var(--text-secondary)">
                正在生成卡片...
              </div>
              <div class="nch-desc">卡片生成完成后将自动显示</div>
            </div>

            <!-- 卡片主展示区 -->
            <!-- 所有卡片一次性渲染，用 v-show 切换，避免重复加载 -->
            <template
              v-for="(card, i) in cards"
              :key="card.slotId || card.cardId || i"
            >
              <div
                v-if="!card.loading && card.cardId"
                v-show="i === currentCardIndex"
                class="card-main-view"
                :class="{ 'card-active': i === currentCardIndex }"
              >
                <!-- HTML 知识卡片 -->
                <HtmlCard
                  v-if="card.cardType === 'html'"
                  :file-id="card.cardId"
                  :session-id="currentSessionId || ''"
                />
                <!-- 交互可视化卡片 -->
                <VizCard
                  v-else-if="card.cardType === 'viz'"
                  :viz-id="card.cardId"
                  :title="card.title"
                />
                <!-- 做题卡片 -->
                <QuizCard
                  v-else-if="card.cardType === 'quiz'"
                  :quiz-id="card.cardId"
                  @answered="onQuizAnswered"
                />
              </div>
            </template>
            <!-- 当前卡片还在加载中时显示占位 -->
            <div
              v-if="currentCard && currentCard.loading"
              class="card-main-view"
            />
          </div>

          <!-- 卡片画廊（底部，所有卡片缩略图） -->
          <div v-if="cards.length > 0" class="card-gallery">
            <div class="cg-scroll">
              <div
                v-for="(card, i) in cards"
                :key="card.slotId || card.cardId || i"
                class="cg-card"
                :class="{
                  active: !card.loading && i === currentCardIndex,
                  loading: card.loading,
                }"
                @click="!card.loading && selectCard(i)"
              >
                <!-- 加载中占位 -->
                <template v-if="card.loading">
                  <div class="cg-skeleton">
                    <div class="cg-shimmer" />
                    <div class="cg-stage-icon">
                      <svg
                        width="18"
                        height="18"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                        class="cg-spin"
                      >
                        <path d="M21 12a9 9 0 11-6.219-8.56" />
                      </svg>
                    </div>
                  </div>
                  <div class="cg-info">
                    <div class="cg-title cg-title--loading">
                      {{ card.title }}
                    </div>
                    <div class="cg-stage-label">{{ card.stageLabel }}</div>
                  </div>
                </template>
                <!-- 已完成卡片 -->
                <template v-else>
                  <div class="cg-thumb-wrap">
                    <!-- HTML 卡片缩略图：直接渲染实际卡片内容的迷你预览 -->
                    <HtmlCard
                      v-if="card.cardType === 'html' && card.cardId"
                      class="cg-html-thumb"
                      :file-id="card.cardId"
                      :show-header="false"
                    />
                    <div
                      v-else
                      class="cg-thumb-fallback"
                      :class="`type-${card.cardType}`"
                    >
                      <div class="cg-thumb-title">{{ card.title }}</div>
                      <div class="cg-thumb-lines">
                        <span />
                        <span />
                        <span />
                      </div>
                      <div class="cg-thumb-chip">
                        {{
                          {
                            viz: "互动",
                            quiz: "练习",
                          }[card.cardType] || "卡片"
                        }}
                      </div>
                    </div>
                    <div v-if="i === currentCardIndex" class="cg-active-badge">
                      <svg
                        width="10"
                        height="10"
                        viewBox="0 0 24 24"
                        fill="currentColor"
                      >
                        <path d="M5 3l14 9-14 9V3z" />
                      </svg>
                    </div>
                  </div>
                  <div class="cg-info">
                    <div class="cg-title">{{ card.title }}</div>
                    <div class="cg-type-label">
                      {{
                        {
                          html: "知识卡片",
                          viz: "交互可视化",
                          quiz: "做题",
                        }[card.cardType] || card.cardType
                      }}
                    </div>
                  </div>
                </template>
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
          <!-- 对话区 -->
          <!-- Agent 顶栏 -->
          <div class="agent-topbar">
            <div class="at-agent">
              <div class="at-logo-avatar">
                <img src="/logo.png" alt="AI" />
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
            v-if="
              cards.filter((c) => !c.loading).length > 0 && phase === 'learning'
            "
            class="context-strip"
          >
            <span>{{
              { html: "📄", viz: "🎮", quiz: "❓" }[currentCard?.cardType] ||
              "📄"
            }}</span>
            <span class="cs-title">{{ currentCard?.title }}</span>
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
                  <div class="agent-avatar msg-agent-avatar">
                    <img src="/logo.png" alt="AI" />
                  </div>
                </div>
                <div class="msg-col">
                  <div class="msg-bubble" :class="msg.role">
                    <div v-if="msg.thinking" class="typing-dots">
                      <span /><span /><span />
                    </div>
                    <template v-else>
                      <!-- ══ 执行步骤块 ══ -->
                      <div
                        v-if="msg.stepBlocks && msg.stepBlocks.length"
                        class="msg-step-blocks"
                      >
                        <div
                          v-for="blk in msg.stepBlocks"
                          :key="blk.step"
                          class="msb-block"
                        >
                          <!-- Think 块 -->
                          <ThinkBlock
                            v-if="blk.think"
                            :think="blk.think"
                            @set-ref="(el) => setThinkRef(blk.step, el)"
                          />

                          <!-- ToolCall 块列表（同一 step 可能并行多个） -->
                          <ToolCallBlock
                            v-for="tc in blk.toolCalls"
                            :key="tc.id"
                            :tc="tc"
                            @set-args-ref="(el) => setArgsRef(tc.id, el)"
                            @set-logs-ref="(el) => setLogsRef(tc.id, el)"
                          />
                        </div>
                      </div>

                      <!-- 正文 -->
                      <div
                        v-if="msg.content"
                        class="msg-text"
                        :class="{ 'msg-text--ready': msg.ready }"
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
                  <div class="user-avatar">
                    {{ userInitial }}
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
            <button class="qb-chip" @click="sendMessage('给一个可视化例子')">
              给一个可视化例子
            </button>
          </div>

          <!-- 输入区 -->
          <div class="input-zone">
            <!-- Quiz 锁定提示 -->
            <Transition name="quiz-toast">
              <div v-if="quizLockToast" class="quiz-lock-toast">
                <svg
                  width="14"
                  height="14"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="12" />
                  <line x1="12" y1="16" x2="12.01" y2="16" />
                </svg>
                还有
                {{
                  [...pendingQuizBatch.values()].filter((i) => !i.answered)
                    .length
                }}
                道练习题未完成，请先作答
              </div>
            </Transition>
            <div
              class="iz-input-wrap"
              :class="{
                focused: inputFocused,
                'quiz-locked': hasUnansweredQuiz,
              }"
            >
              <textarea
                ref="inputBox"
                v-model="inputText"
                class="iz-input"
                :placeholder="
                  isGenerating || phase === 'generating'
                    ? 'Agent 正在生成，请稍候...'
                    : hasUnansweredQuiz
                      ? '请先完成上方的练习题...'
                      : '问我任何学习问题...'
                "
                :disabled="
                  isGenerating || phase === 'generating' || hasUnansweredQuiz
                "
                rows="1"
                @keydown.enter.exact.prevent="
                  hasUnansweredQuiz
                    ? showQuizLockToast()
                    : sendMessage(inputText)
                "
                @input="autoResize"
                @focus="
                  hasUnansweredQuiz
                    ? (showQuizLockToast(), $event.target.blur())
                    : (inputFocused = true)
                "
                @blur="inputFocused = false"
              />
              <button
                class="iz-send"
                :class="{
                  active:
                    inputText.trim() &&
                    phase !== 'generating' &&
                    !hasUnansweredQuiz,
                }"
                @click="
                  hasUnansweredQuiz
                    ? showQuizLockToast()
                    : sendMessage(inputText)
                "
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
        </div>
      </div>
    </transition>

    <!-- ══ 离开确认弹窗 ══ -->
    <transition name="modal">
      <div
        v-if="showLeaveConfirm"
        class="leave-confirm-overlay"
        @click.self="showLeaveConfirm = false"
      >
        <div class="leave-confirm-card">
          <div class="lc-icon">⚠️</div>
          <div class="lc-title">确认离开？</div>
          <div class="lc-desc">
            当前正在生成内容，离开将会<strong>中断生成</strong>，已生成的部分内容可能丢失。
          </div>
          <div class="lc-actions">
            <button
              class="btn btn-ghost btn-sm"
              @click="showLeaveConfirm = false"
            >
              继续等待
            </button>
            <button class="btn btn-danger btn-sm" @click="confirmLeave">
              确认离开
            </button>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted } from "vue";
import { useRoute, onBeforeRouteLeave } from "vue-router";
import { sessionApi, api } from "@/api";
import { useAuth } from "@/composables/useAuth.js";
import ThinkBlock from "@/components/chat/ThinkBlock.vue";
import ToolCallBlock from "@/components/chat/ToolCallBlock.vue";
import HtmlCard from "@/components/HtmlCard/HtmlCard.vue";
import VizCard from "@/components/VizCard/VizCard.vue";
import { QuizCard } from "@/components/QuizCard/index.js";
import { marked } from "marked";
import DOMPurify from "dompurify";
import katex from "katex";
import "katex/dist/katex.min.css";

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
const { userName: authUserName } = useAuth();
// 用户名称首字母（大写）
const userInitial = computed(() => {
  const name = authUserName.value || "U";
  return name.charAt(0).toUpperCase();
});

// ── 阶段状态 ────────────────────────────────────────────────────
// idle → generating → learning
const phase = ref("idle");
const currentTopic = ref("");
const topicInput = ref("");
const topicFocused = ref(false);
const topicInputEl = ref(null);
const selectedMode = ref("chat"); // 'chat' | 'immersive'
const enableAudio = ref(false);
const enableExercises = ref(true);
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
        // AI 主导学习已拆分到 ImmersiveView，重定向过去
        window.location.replace(
          `/immersive?session_id=${detail.id}&topic=${encodeURIComponent(detail.topic || detail.title?.replace("[AI课程] ", "") || "")}`,
        );
        return;
      } else {
        // ── 恢复人机交互学习 ──
        phase.value = "learning";

        // 还原消息列表（assistant 消息渲染 markdown）
        messages.value = (detail.messages || []).map((m) => ({
          role: m.role,
          content: m.content,
          html: m.role === "assistant" ? renderMd(m.content) : m.content,
          ready: true, // 历史消息直接可见，不需要淡入动画
          time: m.created_at
            ? new Date(m.created_at).toLocaleTimeString("zh-CN", {
                hour: "2-digit",
                minute: "2-digit",
              })
            : "",
          steps: [], // 兼容旧数据
          stepBlocks: [],
          events: [],
        }));

        // 恢复历史卡片
        if (detail.files && detail.files.length > 0) {
          loadSessionCards(detail.files);
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
    // 如果 mode=immersive，重定向到 ImmersiveView
    if (route.query.mode === "immersive") {
      window.location.replace(`/immersive?topic=${encodeURIComponent(topic)}`);
      return;
    } else {
      nextTick(() => startLearning());
    }
  }
});

// ── 起始页：漂浮云朵主题（支持个性化推荐） ─────────────────────────────────
const defaultSuggestions = [
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

const rawSuggestions = ref(defaultSuggestions);

// 异步加载个性化推荐云朵
(async () => {
  try {
    const res = await api.get("/api/immersive/suggestions");
    if (res?.suggestions?.length > 0) {
      rawSuggestions.value = res.suggestions.map((s) => ({
        text: s.text,
        emoji: s.emoji || "💡",
        size: s.size || "md",
      }));
    }
  } catch {
    // 失败时保持默认列表
  }
})();

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
  rawSuggestions.value.map((s, i) => {
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

// ── 卡片列表（三种类型：html / viz / quiz）────────────────────────
// cards: [{ slotId, cardId, cardType, title, loading, stage, stageLabel }]
//   cardType: 'html' | 'viz' | 'quiz'
//   loading=true  → 占位卡片（生成中）
//   loading=false → 已完成卡片
const cards = ref([]);

// ── Quiz 批次管理 ─────────────────────────────────────────────────
// 每轮 SSE 生成的 quiz 卡片收集到同一批次，全部答完后统一发一条汇总消息
// Map<quizId, { question, answered, result }>
const pendingQuizBatch = ref(new Map());
const currentCardIndex = ref(0);

// 是否存在未答的 quiz 题目（输入框锁定条件）
const hasUnansweredQuiz = computed(() => {
  if (pendingQuizBatch.value.size === 0) return false;
  return [...pendingQuizBatch.value.values()].some((item) => !item.answered);
});
// quiz 锁定提示 toast
const quizLockToast = ref(false);
let quizLockToastTimer = null;
function showQuizLockToast() {
  // 跳转到第一张未答的 quiz 卡片
  const batch = pendingQuizBatch.value;
  for (let i = 0; i < cards.value.length; i++) {
    const card = cards.value[i];
    if (
      card.cardType === "quiz" &&
      !card.loading &&
      batch.has(card.cardId) &&
      !batch.get(card.cardId).answered
    ) {
      currentCardIndex.value = i;
      break;
    }
  }
  // 显示 toast
  quizLockToast.value = true;
  clearTimeout(quizLockToastTimer);
  quizLockToastTimer = setTimeout(() => {
    quizLockToast.value = false;
  }, 2500);
}

// 占位卡片映射：toolCallId → slotIndex
const pendingCardSlots = new Map();

const currentCard = computed(() => cards.value[currentCardIndex.value] || null);

/** 在 onToolCall 时插入占位卡片，返回 slotIndex */
function addCardPlaceholder(slotId, title, cardType = "html") {
  if (pendingCardSlots.has(slotId)) return pendingCardSlots.get(slotId);
  const idx = cards.value.length;
  cards.value.push({
    slotId,
    cardId: null,
    cardType,
    title: title || "知识卡片",
    loading: true,
    stage: "generating",
    stageLabel: "正在生成...",
  });
  pendingCardSlots.set(slotId, idx);
  return idx;
}

/** 更新占位卡片的阶段文字 */
function updateCardSlotStage(slotId, content) {
  const idx = pendingCardSlots.get(slotId);
  if (idx === undefined) return;
  const card = cards.value[idx];
  if (!card?.loading) return;
  let stage = card.stage;
  let stageLabel = content;
  if (content.includes("正在生成知识卡片") || content.includes("正在生成")) {
    stage = "generating";
    stageLabel = "正在生成...";
  } else if (content.includes("卡片生成完成") || content.includes("生成完成")) {
    stage = "done";
    stageLabel = "生成完成";
  }
  cards.value[idx] = { ...card, stage, stageLabel };
}

/** onToolResult 时，将占位卡片关联到真实 cardId */
function resolveCardSlot(slotId, cardId, title, cardType) {
  const idx = pendingCardSlots.get(slotId);
  if (idx === undefined) return;
  const card = cards.value[idx];
  if (!card) return;
  cards.value[idx] = {
    ...card,
    slotId,
    cardId,
    cardType: cardType || card.cardType,
    title: title || card.title,
    loading: false,
    stage: "done",
    stageLabel: "",
  };
  // 自动切换到新生成的卡片
  if (idx >= currentCardIndex.value) {
    currentCardIndex.value = idx;
  }
}

/** 恢复历史会话时加载已有卡片 */
function loadSessionCards(files) {
  // 后端 file_type 枚举 → 前端 cardType
  const cardTypeMap = {
    html_card: "html",
    pdf_card: "html", // PDF 卡片暂复用 html 渲染逻辑
    viz: "viz",
    quiz: "quiz",
  };
  for (const f of files) {
    if (!f.file_id) continue;
    const cardType = cardTypeMap[f.file_type];
    if (!cardType) continue;
    cards.value.push({
      slotId: f.file_id,
      cardId: f.file_id,
      cardType,
      title: f.title || f.file_id,
      loading: false,
      stage: "done",
      stageLabel: "",
    });
  }
  if (cards.value.length > 0) currentCardIndex.value = 0;
}

function selectCard(idx) {
  const card = cards.value[idx];
  if (!card || card.loading) return;
  currentCardIndex.value = idx;
}

// ── 幻灯片（保留兼容） ────────────────────────────────────────────
const slides = ref([]);
const currentIndex = ref(0);
const currentSlide = computed(() => slides.value[currentIndex.value] || null);

// ── 离开确认 ─────────────────────────────────────────────────────
const showLeaveConfirm = ref(false);
let pendingLeaveAction = null; // 'reset' | Function (路由守卫的 next)

// 是否有任何生成任务正在进行
const isAnythingGenerating = computed(
  () => isGenerating.value || phase.value === "generating",
);

function handleBack() {
  if (isAnythingGenerating.value) {
    pendingLeaveAction = "reset";
    showLeaveConfirm.value = true;
  } else {
    resetToIdle();
  }
}

function confirmLeave() {
  showLeaveConfirm.value = false;
  if (pendingLeaveAction === "reset") {
    resetToIdle();
  } else if (typeof pendingLeaveAction === "function") {
    pendingLeaveAction();
  }
  pendingLeaveAction = null;
}

// 路由离开守卫
onBeforeRouteLeave((to, from, next) => {
  if (isAnythingGenerating.value) {
    pendingLeaveAction = next;
    showLeaveConfirm.value = true;
    // 不调用 next()，阻止导航
  } else {
    next();
  }
});

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
  slides.value = [];
  cards.value = [];
  currentCardIndex.value = 0;
  pendingCardSlots.clear();
  messages.value = [];
  currentIndex.value = 0;
  topicInput.value = "";
  genProgress.value = 0;
  genStage.value = -1;
}

// 浏览器关闭/刷新拦截
function handleBeforeUnload(e) {
  if (isAnythingGenerating.value) {
    e.preventDefault();
    e.returnValue = "";
  }
}

onMounted(() => {
  window.addEventListener("beforeunload", handleBeforeUnload);
});
onUnmounted(() => {
  if (sseController) sseController.abort();
  window.removeEventListener("beforeunload", handleBeforeUnload);
  // 离开页面时上报本次会话学习时长
  if (currentSessionId.value && sessionStartTime) {
    const minutes = Math.max(
      1,
      Math.round((Date.now() - sessionStartTime) / 60000),
    );
    sessionApi.recordDuration(currentSessionId.value, minutes).catch(() => {});
  }
});

// ── 导出（暂不支持，保留占位）────────────────────────────────────
// const isExporting = ref(false);
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

// 答题完成后，等本批次全部答完再统一通知 Agent
function onQuizAnswered(result) {
  const { quizId } = result;

  // 标记该题已答
  if (quizId && pendingQuizBatch.value.has(quizId)) {
    pendingQuizBatch.value.set(quizId, {
      ...pendingQuizBatch.value.get(quizId),
      answered: true,
      result,
    });
  }

  // 检查批次中是否还有未答的题
  const batch = [...pendingQuizBatch.value.values()];
  const allAnswered = batch.length > 0 && batch.every((item) => item.answered);

  if (!allAnswered) return; // 还有题没答，等待

  // 全部答完，构造汇总消息
  const typeMap = {
    multiple_choice: "单选题",
    true_false: "判断题",
    fill_in: "填空题",
    open_ended: "简答题",
  };

  // 辅助：把用户答案转为完整内容（选择题填充选项文本）
  function formatAnswer(r) {
    if (
      r.quiz_type === "multiple_choice" &&
      r.options &&
      r.options.length > 0
    ) {
      const letter = (r.user_answer || "").toUpperCase();
      const matched = r.options.find((opt) => opt[0].toUpperCase() === letter);
      return matched ? matched : r.user_answer;
    }
    if (r.quiz_type === "true_false") {
      return r.user_answer === "true" ? "正确" : "错误";
    }
    return r.user_answer;
  }

  // 辅助：格式化正确答案（选择题填充选项文本）
  function formatCorrectAnswer(r) {
    if (
      r.quiz_type === "multiple_choice" &&
      r.options &&
      r.options.length > 0
    ) {
      const letter = (r.correct_answer || "").toUpperCase();
      const matched = r.options.find((opt) => opt[0].toUpperCase() === letter);
      return matched ? matched : r.correct_answer;
    }
    if (r.quiz_type === "true_false") {
      const trueVals = ["true", "正确", "对", "是", "yes", "t", "1"];
      return trueVals.includes((r.correct_answer || "").toLowerCase())
        ? "正确"
        : "错误";
    }
    return r.correct_answer;
  }

  // eslint-disable-next-line no-useless-assignment
  let msg = "";
  if (batch.length === 1) {
    // 只有一道题，简洁格式
    const item = batch[0];
    const r = item.result;
    const typeLabel = typeMap[r.quiz_type] || "题目";
    const answerText = formatAnswer(r);
    const resultText = r.is_correct
      ? "回答正确 ✓"
      : `回答错误 ✗（正确答案：${formatCorrectAnswer(r)}）`;
    // 选择题附上完整选项列表
    const optionsText =
      r.quiz_type === "multiple_choice" && r.options?.length
        ? `\n选项：${r.options.join(" / ")}`
        : "";
    msg = `我完成了一道${typeLabel}：\n题目：${r.question}${optionsText}\n我的答案：${answerText}\n${resultText}`;
  } else {
    // 多道题，列表格式
    const lines = batch.map((item, i) => {
      const r = item.result;
      const answerText = formatAnswer(r);
      const resultText = r.is_correct
        ? "正确 ✓"
        : `错误 ✗（正确答案：${formatCorrectAnswer(r)}）`;
      const optionsText =
        r.quiz_type === "multiple_choice" && r.options?.length
          ? `（选项：${r.options.join(" / ")}）`
          : "";
      return `第${i + 1}题（${typeMap[r.quiz_type] || "题目"}）：${r.question}${optionsText}\n   我的答案：${answerText}，${resultText}`;
    });
    const correctCount = batch.filter((item) => item.result.is_correct).length;
    msg = `我完成了本轮 ${batch.length} 道练习题（答对 ${correctCount} 题）：\n\n${lines.join("\n\n")}`;
  }

  // 清空批次，发送汇总消息
  pendingQuizBatch.value.clear();
  sendMessage(msg);
}

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
      ready: false, // 控制最终回复淡入
      time: now(),
      stepBlocks: [], // 按 step 分组的执行块
      events: [], // 业务事件标签
    };

    // 辅助：获取或创建某个 step 的 block
    const getOrCreateBlock = (step) => {
      const blocks = messages.value[idx].stepBlocks;
      let blk = blocks.find((b) => b.step === step);
      if (!blk) {
        blk = { step, think: null, toolCalls: [] };
        blocks.push(blk);
        // 按 step 排序
        blocks.sort((a, b) => a.step - b.step);
      }
      return blk;
    };

    // 辅助：获取某个 toolCall 条目（通过 id）
    const getToolCall = (id) => {
      for (const blk of messages.value[idx].stepBlocks) {
        const tc = blk.toolCalls.find((t) => t.id === id);
        if (tc) return tc;
      }
      return null;
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

    // 工具名称映射
    const toolLabels = {
      search_nodes: "搜索知识节点",
      get_node: "获取节点详情",
      create_node: "创建知识节点",
      update_node: "更新节点",
      update_mastery: "更新掌握度",
      create_quiz: "生成测验题",
      generate_html_card: "生成知识卡片",
      generate_interactive_viz: "生成交互可视化",
      tavily_search: "网络搜索",
      arxiv_search: "搜索论文",
      web_fetch: "获取网页",
      read_file: "读取文件",
      list_dir: "列出目录",
    };

    // 标志：是否已经有过工具调用（用于区分思考轮 vs 最终回复轮）
    let hasToolCall = false;

    sseController = sessionApi.streamMessage(currentSessionId.value, text, {
      // ── 流式分片事件 ──────────────────────────────────────────
      onThinkChunk: (delta, step) => {
        if (debugMode) console.log("[DEBUG] onThinkChunk:", { step, delta });
        const blk = getOrCreateBlock(step);
        const isReplyRound = blk.toolCalls.length === 0 && hasToolCall;
        if (!hasToolCall || isReplyRound) {
          fullContent += delta;
          // 流式输出时直接显示（不等 ready），用 msg-text--ready 让它始终可见
          updateMsg({
            content: fullContent,
            html: renderMd(fullContent),
            ready: true,
            time: now(),
          });
        }
        // 更新 think 块内容（用于折叠展示思考过程）
        if (!blk.think) {
          blk.think = { status: "running", content: "", collapsed: false };
        }
        blk.think.content += delta;
        updateMsg({ stepBlocks: [...messages.value[idx].stepBlocks] });
        scrollBottom();
      },

      onToolCallChunk: (index, id, tool, argsDelta, step) => {
        if (debugMode)
          console.log("[DEBUG] onToolCallChunk:", {
            index,
            id,
            tool,
            argsDelta,
            step,
          });
        const blk = getOrCreateBlock(step);
        let tc = blk.toolCalls.find((t) => t.id === id);
        if (!tc) {
          tc = {
            id,
            tool,
            step,
            status: "pending", // pending → calling → running → done
            title: `${toolLabels[tool] || tool} 调用请求`,
            argsBuf: "",
            runLogs: [],
            resultSummary: "",
            collapsed: false,
          };
          blk.toolCalls.push(tc);
        }
        if (argsDelta) tc.argsBuf += argsDelta;
        updateMsg({ stepBlocks: [...messages.value[idx].stepBlocks] });
        scrollBottom();
        // 自动滚动参数区到底部
        nextTick(() => scrollArgsRef(id));
      },

      onToolRun: (id, tool, content, step) => {
        if (debugMode)
          console.log("[DEBUG] onToolRun:", {
            id,
            tool,
            step,
            content: content?.slice?.(0, 80),
          });
        const tc = getToolCall(id);
        if (!tc) return;
        tc.status = "running";
        // 解析 content：可能是普通文本，也可能是嵌套 agent 事件
        const logEntry = parseRunContent(content);
        tc.runLogs.push(logEntry);
        // generate_html_card：更新占位卡片的阶段文字
        if (tool === "generate_html_card" && typeof content === "string") {
          updateCardSlotStage(id, content);
        }
        updateMsg({ stepBlocks: [...messages.value[idx].stepBlocks] });
        scrollBottom();
        nextTick(() => scrollLogsRef(id));
      },

      onTextChunk: (delta) => {
        if (debugMode) console.log("[DEBUG] onTextChunk:", { delta });
        fullContent += delta;
        updateMsg({
          content: fullContent,
          html: renderMd(fullContent),
          time: now(),
        });
        scrollBottom();
      },

      // ── 汇总事件 ─────────────────────────────────────────────
      onThinking: (content, step) => {
        if (debugMode)
          console.log("[DEBUG] onThinking:", {
            step,
            content: content.slice(0, 80),
          });
        const blk = getOrCreateBlock(step);
        if (!blk.think) {
          blk.think = { status: "done", content, collapsed: true };
        } else {
          // 用完整内容替换流式累积，并标为完成后自动折叠
          blk.think.content = content;
          blk.think.status = "done";
          blk.think.collapsed = true;
        }
        updateMsg({ stepBlocks: [...messages.value[idx].stepBlocks] });
        scrollBottom();
      },

      onToolCall: (id, tool, args, step) => {
        if (debugMode)
          console.log("[DEBUG] onToolCall:", { id, tool, step, args });
        // 有工具调用 → 当前轮是思考轮，清空 fullContent，标记已有工具调用
        hasToolCall = true;
        fullContent = "";
        updateMsg({ content: "", html: "", time: now() });
        const blk = getOrCreateBlock(step);
        let tc = blk.toolCalls.find((t) => t.id === id);
        if (!tc) {
          tc = {
            id,
            tool,
            step,
            status: "calling",
            title: `正在调用：${toolLabels[tool] || tool}`,
            argsBuf:
              typeof args === "string" ? args : JSON.stringify(args, null, 2),
            runLogs: [],
            resultSummary: "",
            collapsed: false,
          };
          blk.toolCalls.push(tc);
        } else {
          tc.status = "calling";
          tc.title = `正在调用：${toolLabels[tool] || tool}`;
          if (!tc.argsBuf) {
            tc.argsBuf =
              typeof args === "string" ? args : JSON.stringify(args, null, 2);
          }
        }
        // generate_html_card：立即插入 html 占位卡片，右侧只保留短引导
        if (tool === "generate_html_card") {
          const cardTitle =
            (typeof args === "string" ? JSON.parse(args || "{}") : args || {})
              .title || "知识卡片";
          addCardPlaceholder(id, cardTitle, "html");
        }
        // generate_interactive_viz：立即插入 viz 占位卡片，右侧只保留短引导
        if (tool === "generate_interactive_viz") {
          const cardTitle =
            (typeof args === "string" ? JSON.parse(args || "{}") : args || {})
              .title || "交互可视化";
          addCardPlaceholder(id, cardTitle, "viz");
        }
        // create_quiz：立即插入 quiz 占位卡片，右侧只保留短引导
        if (tool === "create_quiz") {
          const parsedArgs =
            typeof args === "string" ? JSON.parse(args || "{}") : args || {};
          const cardTitle = parsedArgs.question
            ? parsedArgs.question.slice(0, 20) + "…"
            : "练习题";
          addCardPlaceholder(id, cardTitle, "quiz");
        }
        updateMsg({ stepBlocks: [...messages.value[idx].stepBlocks] });
        scrollBottom();
      },

      onToolResult: (id, tool, args, result, step) => {
        if (debugMode)
          console.log("[DEBUG] onToolResult:", {
            id,
            tool,
            step,
            result: typeof result === "string" ? result.slice(0, 200) : result,
          });
        const tc =
          getToolCall(id) ||
          (() => {
            // 兜底：如果没有找到，从 step 的 block 里找同名工具
            const blk = getOrCreateBlock(step);
            return blk.toolCalls.find((t) => t.tool === tool);
          })();
        if (tc) {
          tc.status = "done";
          tc.title = `✓ ${toolLabels[tool] || tool}`;
          tc.collapsed = true; // 完成后自动折叠
          // 生成结果摘要（截取前 120 字符）
          const resultStr =
            typeof result === "string" ? result : JSON.stringify(result);
          tc.resultSummary =
            resultStr.slice(0, 120) + (resultStr.length > 120 ? "…" : "");
        }
        // 同时把同 step 的 think 块标为 done
        const blk = messages.value[idx].stepBlocks.find((b) => b.step === step);
        if (blk?.think) blk.think.status = "done";
        updateMsg({ stepBlocks: [...messages.value[idx].stepBlocks] });
        // generate_html_card：将占位卡片关联到真实 file_id
        if (tool === "generate_html_card") {
          try {
            const data =
              typeof result === "string" ? JSON.parse(result) : result;
            if (data?.file_id) {
              const cardArgs =
                typeof args === "string"
                  ? JSON.parse(args || "{}")
                  : args || {};
              resolveCardSlot(id, data.file_id, cardArgs.title || "", "html");
            }
          } catch {
            /* result 不是 JSON，占位卡片保持 loading 状态 */
          }
        }
        // generate_interactive_viz：result 直接是 viz_id 字符串
        if (tool === "generate_interactive_viz") {
          try {
            const vizId = typeof result === "string" ? result.trim() : "";
            if (vizId && !vizId.startsWith("Error")) {
              const cardArgs =
                typeof args === "string"
                  ? JSON.parse(args || "{}")
                  : args || {};
              resolveCardSlot(id, vizId, cardArgs.title || "", "viz");
            }
          } catch {
            /* 解析失败，占位卡片保持 loading 状态 */
          }
        }
        // create_quiz：result 包含 quiz_id，关联到占位卡片，并加入当前批次
        if (tool === "create_quiz") {
          try {
            const data =
              typeof result === "string" ? JSON.parse(result) : result;
            if (data?.quiz_id) {
              const cardArgs =
                typeof args === "string"
                  ? JSON.parse(args || "{}")
                  : args || {};
              const cardTitle = cardArgs.question
                ? cardArgs.question.slice(0, 20) + "…"
                : "练习题";
              resolveCardSlot(id, data.quiz_id, cardTitle, "quiz");
              // 加入当前批次，等待用户作答
              pendingQuizBatch.value.set(data.quiz_id, {
                question: cardArgs.question || "练习题",
                options: cardArgs.options || [],
                answered: false,
                result: null,
              });
            }
          } catch {
            /* 解析失败，占位卡片保持 loading 状态 */
          }
        }
        // create_node 返回 created:false 时给用户提示
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
          } catch (e) {
            console.error("create_node result 解析失败:", result, e);
          }
        }
      },

      onTextReply: (text) => {
        if (debugMode) console.log("[DEBUG] onTextReply:", { text });
        if (!fullContent) {
          // 非流式兑底：内容一次性到位，触发淡入动画
          fullContent = text;
          updateMsg({
            content: fullContent,
            html: renderMd(fullContent),
            ready: false,
            time: now(),
          });
          nextTick(() => updateMsg({ ready: true }));
        } else {
          // 流式兑底：内容已经存在，只确保 ready 状态正确
          updateMsg({ ready: true });
        }
        scrollBottom();
      },
      onFileCreated: (fileId) => {
        if (debugMode) {
          console.log("[DEBUG] onFileCreated:", { fileId });
        }
        // generate_card 的卡片填充完全由 onToolResult → resolveCardSlot 负责。
        // onFileCreated 早于 onToolResult 到达（后端先 yield FileCreatedEvent），
        // 此时占位卡片的 fileId 还是 null，不能在这里做任何卡片操作，否则会重复 push。
        // 这里只负责添加业务事件标签，供 UI 展示。
        const events = [...(messages.value[idx].events || [])];
        events.push({ type: "file_created", fileId });
        updateMsg({ events });
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
        if (debugMode) console.log("[DEBUG] onDone: 请求完成");
        // 把所有 running/calling/pending 状态标为 done，think 块自动折叠
        const stepBlocks = (messages.value[idx].stepBlocks || []).map(
          (blk) => ({
            ...blk,
            think: blk.think
              ? { ...blk.think, status: "done", collapsed: true }
              : null,
            toolCalls: blk.toolCalls.map((tc) => ({
              ...tc,
              status: tc.status === "done" ? "done" : "done",
              collapsed: true,
            })),
          }),
        );
        // 确保最终回复可见（兑底：如果 text_reply 没有触发 ready）
        updateMsg({
          stepBlocks,
          content: fullContent,
          html: renderMd(fullContent),
          ready: true,
        });
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
    ready: true,
    time: now(),
    stepBlocks: [],
    events: [],
  };
}

// ── stepBlocks 辅助 ──────────────────────────────────────────────
// 用 Map 缓存各滚动区域的 DOM 引用，key 分别是 step（think）或 id（args/logs）
const _thinkRefs = new Map();
const _argsRefs = new Map();
const _logsRefs = new Map();

function setThinkRef(step, el) {
  if (el) _thinkRefs.set(step, el);
  else _thinkRefs.delete(step);
}
function setArgsRef(id, el) {
  if (el) _argsRefs.set(id, el);
  else _argsRefs.delete(id);
}
function setLogsRef(id, el) {
  if (el) _logsRefs.set(id, el);
  else _logsRefs.delete(id);
}

function scrollArgsRef(id) {
  const el = _argsRefs.get(id);
  if (el) el.scrollTop = el.scrollHeight;
}
function scrollLogsRef(id) {
  const el = _logsRefs.get(id);
  if (el) el.scrollTop = el.scrollHeight;
}

/**
 * 解析 tool_run 的 content，识别嵌套 agent 事件
 * content 可能是普通文本，也可能是 JSON 序列化的事件对象
 */
function parseRunContent(content) {
  if (!content) return { type: "text", text: "" };
  try {
    const obj = typeof content === "string" ? JSON.parse(content) : content;
    if (obj && obj.type) {
      // 嵌套 agent think 事件
      if (obj.type === "think_chunk" || obj.type === "thinking") {
        return { type: "agent_think", text: obj.delta || obj.content || "" };
      }
      // 嵌套 agent tool 事件
      if (obj.type === "tool_call" || obj.type === "tool_result") {
        const label = obj.tool || "";
        const summary = obj.result
          ? `${label} → ${String(obj.result).slice(0, 60)}`
          : label;
        return { type: "agent_tool", text: summary };
      }
    }
  } catch {
    /* 不是 JSON，当普通文本处理 */
  }
  return {
    type: "text",
    text: typeof content === "string" ? content : JSON.stringify(content),
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

.cs-dot.done {
  background: #10b981;
}
.cs-item.generating {
  color: var(--brand-light);
}

/* 右侧面板：大纲+习题+日志 tabs */

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
  padding: 40px 24px;
  z-index: 10;
  background: var(--bg-base);
  color: var(--text-primary);
  overflow: hidden;
}
.te-bg-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.02) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.02) 1px, transparent 1px);
  background-size: 48px 48px;
  mask-image: radial-gradient(ellipse at center, #000 30%, transparent 72%);
  pointer-events: none;
}
.te-bg-glow {
  position: absolute;
  border-radius: 50%;
  filter: blur(120px);
  opacity: 0.15;
  pointer-events: none;
  animation: te-drift 20s ease-in-out infinite;
}
.te-bg-glow-1 {
  width: 600px;
  height: 600px;
  background: #6366f1;
  top: -150px;
  left: 5%;
}
.te-bg-glow-2 {
  width: 500px;
  height: 500px;
  background: #a855f7;
  bottom: -120px;
  right: 5%;
  animation-delay: -10s;
}
@keyframes te-drift {
  0%,
  100% {
    transform: translate(0, 0) scale(1);
  }
  50% {
    transform: translate(24px, -18px) scale(1.06);
  }
}

/* 飘散云朵（背景装饰，保留但降低存在感） */
.te-clouds {
  position: absolute;
  inset: 0;
  pointer-events: none;
  z-index: 1;
  opacity: 0.45;
}
.te-cloud {
  pointer-events: auto;
  position: absolute;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 14px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 999px;
  color: var(--text-muted);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  backdrop-filter: blur(8px);
  transition: opacity 0.2s;
  animation: te-float ease-in-out infinite;
  will-change: transform;
  white-space: nowrap;
  transform: scale(var(--jitter, 1)) rotate(var(--rot, 0deg));
}
.te-cloud-xs {
  font-size: 10px;
  padding: 4px 10px;
  opacity: 0.5;
}
.te-cloud-sm {
  font-size: 11px;
  padding: 5px 12px;
  opacity: 0.65;
}
.te-cloud-md {
  font-size: 12px;
  padding: 7px 14px;
  opacity: 0.8;
}
.te-cloud-lg {
  font-size: 13px;
  padding: 8px 16px;
  opacity: 0.9;
}
.te-cloud-xl {
  font-size: 14px;
  padding: 10px 20px;
  opacity: 1;
}
.te-cloud-xs .te-cloud-emoji,
.te-cloud-sm .te-cloud-emoji {
  font-size: 12px;
}
.te-cloud-md .te-cloud-emoji {
  font-size: 13px;
}
.te-cloud-lg .te-cloud-emoji,
.te-cloud-xl .te-cloud-emoji {
  font-size: 15px;
}
.te-cloud:hover {
  opacity: 1 !important;
  color: var(--text-primary);
  border-color: var(--border-active);
  animation-play-state: paused;
  z-index: 3;
}
.te-cloud.active {
  color: var(--brand-light);
  border-color: var(--border-active);
  background: var(--brand-dim);
  opacity: 1 !important;
}
@keyframes te-float {
  0% {
    transform: translate(0, 0) scale(var(--jitter, 1)) rotate(var(--rot, 0deg));
  }
  25% {
    transform: translate(5px, -8px) scale(var(--jitter, 1))
      rotate(var(--rot, 0deg));
  }
  50% {
    transform: translate(-3px, -14px) scale(var(--jitter, 1))
      rotate(var(--rot, 0deg));
  }
  75% {
    transform: translate(-6px, -5px) scale(var(--jitter, 1))
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
  max-width: 760px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0;
}

.te-head {
  margin-bottom: 32px;
}
.te-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  border-radius: 999px;
  background: var(--brand-dim);
  color: var(--brand-light);
  border: 1px solid var(--border-active);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.6px;
  margin-bottom: 20px;
}
.te-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand-light);
  box-shadow: 0 0 6px var(--brand-light);
  animation: pulse 1.6s infinite;
}
.te-title {
  font-size: 40px;
  font-weight: 800;
  line-height: 1.2;
  letter-spacing: -1.5px;
  margin: 0 0 14px;
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
  font-size: 14px;
  margin: 0 auto;
  line-height: 1.7;
}
.te-sub em {
  color: var(--brand-light);
  font-style: normal;
  font-weight: 600;
}

/* 输入框 */
.te-input-wrap {
  width: 100%;
  max-width: 600px;
  margin: 0 0 24px;
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--bg-card);
  border: 1.5px solid var(--border);
  border-radius: 14px;
  padding: 14px 18px;
  transition: var(--transition);
  backdrop-filter: blur(14px);
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.15);
}
.te-input-wrap.focused,
.te-input-wrap.filled {
  border-color: var(--border-active);
  box-shadow:
    0 0 0 4px rgba(99, 102, 241, 0.1),
    0 8px 32px rgba(99, 102, 241, 0.12);
}
.te-input-ico {
  color: var(--text-muted);
  display: flex;
  flex-shrink: 0;
}
.te-input-wrap.focused .te-input-ico,
.te-input-wrap.filled .te-input-ico {
  color: var(--brand-light);
}
.te-input {
  flex: 1;
  background: transparent;
  border: 0;
  outline: 0;
  color: var(--text-primary);
  font-size: 15px;
  font-family: inherit;
  font-weight: 500;
  min-width: 0;
}
.te-input::placeholder {
  color: var(--text-dim);
  font-weight: 400;
}
.te-input-clear {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--bg-hover);
  color: var(--text-muted);
  flex-shrink: 0;
  transition: var(--transition);
}
.te-input-clear:hover {
  background: var(--border);
  color: var(--text-primary);
}
.hint-fade-enter-active,
.hint-fade-leave-active {
  transition: opacity 0.15s;
}
.hint-fade-enter-from,
.hint-fade-leave-to {
  opacity: 0;
}

/* 模式切换区域 */
.te-mode-switch {
  width: 100%;
  max-width: 600px;
  margin-bottom: 20px;
  border: 1.5px solid var(--border);
  border-radius: 14px;
  overflow: hidden;
  background: var(--bg-card);
}

/* Tab 栏 */
.te-tabs {
  position: relative;
  display: flex;
  background: var(--bg-hover);
  border-bottom: 1.5px solid var(--border);
  padding: 0;
  gap: 0;
}
.te-tab {
  all: unset;
  cursor: pointer;
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  padding: 13px 16px;
  font-size: 13px;
  font-weight: 500;
  color: var(--text-muted);
  transition:
    color 0.2s,
    background 0.2s;
  position: relative;
  white-space: nowrap;
  border-right: 1px solid var(--border);
  opacity: 0.6;
}
.te-tab:last-of-type {
  border-right: none;
}
.te-tab:hover:not(.active) {
  color: var(--text-secondary);
  opacity: 0.85;
}
.te-tab.active {
  color: var(--text-primary);
  background: var(--bg-card);
  font-weight: 700;
  opacity: 1;
}
/* 激活 tab 顶部高亮线 */
.te-tab.active::before {
  content: "";
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 3px;
  background: var(--brand-light);
  border-radius: 0 0 3px 3px;
}
/* 激活 tab 底部遮住分隔线，与面板融合 */
.te-tab.active::after {
  content: "";
  position: absolute;
  bottom: -2px;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--bg-card);
  z-index: 1;
}
.te-tab-hot {
  font-size: 9px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 4px;
  background: linear-gradient(135deg, #f59e0b, #ef4444);
  color: #fff;
  letter-spacing: 0.5px;
}
.te-tab-indicator {
  display: none;
}

/* 内容面板 */
.te-panel {
  background: var(--bg-card);
  border: none;
  border-radius: 0;
  padding: 18px 20px 16px;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.te-panel-feats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 10px;
}
.te-panel-feat {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 6px;
  padding: 12px 8px;
  border-radius: 10px;
  background: var(--bg-hover);
  border: 1px solid var(--border);
  transition:
    border-color 0.2s,
    background 0.2s;
}
.te-panel-feat:hover {
  background: var(--bg-secondary, rgba(99, 102, 241, 0.04));
  border-color: var(--brand-light);
}
.te-panel-feat-icon {
  font-size: 22px;
  line-height: 1;
}
.te-panel-feat-title {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.2;
}
.te-panel-feat-desc {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.4;
}

/* 选项开关组 */
.te-options {
  display: flex;
  gap: 10px;
  margin-bottom: 12px;
}
.te-option-toggle {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid rgba(139, 92, 246, 0.2);
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  user-select: none;
  transition: all 0.2s;
}
.te-option-toggle:hover {
  border-color: rgba(139, 92, 246, 0.45);
  background: rgba(139, 92, 246, 0.05);
}
.te-option-toggle input {
  width: 15px;
  height: 15px;
  accent-color: #8b5cf6;
}
.te-option-label {
  color: var(--text-primary);
  font-weight: 600;
  font-size: 13px;
  white-space: nowrap;
}
.te-option-hint {
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
}

/* 启动按钮 */
.te-start-btn {
  all: unset;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  padding: 11px 0;
  border-radius: 10px;
  font-size: 14px;
  font-weight: 700;
  white-space: nowrap;
  transition: var(--transition);
}
.te-start-a {
  background: var(--gradient-brand);
  color: #fff;
  box-shadow: 0 4px 20px rgba(99, 102, 241, 0.35);
}
.te-start-a:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 28px rgba(99, 102, 241, 0.5);
}
.te-start-b {
  background: linear-gradient(135deg, #8b5cf6, #a855f7);
  color: #fff;
  box-shadow: 0 4px 20px rgba(168, 85, 247, 0.35);
}
.te-start-b:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 8px 28px rgba(168, 85, 247, 0.5);
}
.te-start-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  transform: none !important;
  box-shadow: none !important;
}

/* 面板切换动画 */
.te-panel-enter-active,
.te-panel-leave-active {
  transition:
    opacity 0.18s,
    transform 0.18s;
}
.te-panel-enter-from {
  opacity: 0;
  transform: translateY(6px);
}
.te-panel-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* 推荐主题快捷选 */
.te-suggestions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: center;
  max-width: 600px;
}
.te-sug-label {
  font-size: 11px;
  color: var(--text-dim);
  font-weight: 500;
  white-space: nowrap;
}
.te-sug-chip {
  all: unset;
  cursor: pointer;
  font-size: 12px;
  color: var(--text-muted);
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 999px;
  padding: 5px 12px;
  transition: var(--transition);
  white-space: nowrap;
}
.te-sug-chip:hover {
  color: var(--text-primary);
  border-color: var(--border-active);
  background: var(--brand-dim);
}
.te-sug-chip.active {
  color: var(--brand-light);
  border-color: var(--border-active);
  background: var(--brand-dim);
}

/* 响应式 */
@media (max-width: 760px) {
  .te-panel {
    flex-direction: column;
    align-items: stretch;
  }
  .te-start-btn {
    justify-content: center;
  }
  .te-title {
    font-size: 28px;
  }
  .te-clouds {
    display: none;
  }
  .te-suggestions {
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
  min-height: 0;
  overflow: hidden;
  padding: 16px;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

/* 连接中骨架 */
.outline-generating {
  display: flex;
  flex-direction: column;
  gap: 20px;
  width: 100%;
  max-width: 560px;
  margin: 80px auto 0;
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
  padding: 80px 40px;
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

/* 卡片主展示区 */
.card-main-view {
  width: 100%;
  height: 100%;
  min-height: 0;
  min-width: 0;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.3s ease;
}
.card-main-view.card-active {
  opacity: 1;
}

/* 卡片画廊（底部，所有卡片缩略图） */
.card-gallery {
  height: 130px;
  background: var(--bg-panel);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  overflow: hidden;
}
.cg-scroll {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  height: 100%;
  overflow-x: auto;
}
.cg-scroll::-webkit-scrollbar {
  height: 3px;
}
.cg-scroll::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 2px;
}

/* 单张卡片格子 */
.cg-card {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  cursor: pointer;
  width: 90px;
  transition: transform 0.15s ease;
}
.cg-card:hover:not(.loading) {
  transform: translateY(-2px);
}
.cg-card.loading {
  cursor: default;
}

/* 缩略图容器 */
.cg-thumb-wrap {
  width: 90px;
  height: 64px;
  border-radius: 6px;
  border: 2px solid transparent;
  overflow: hidden;
  position: relative;
  background: var(--bg-hover);
  transition:
    border-color 0.15s,
    box-shadow 0.15s;
}
.cg-card:hover:not(.loading) .cg-thumb-wrap {
  border-color: var(--border-active);
}
.cg-card.active .cg-thumb-wrap {
  border-color: var(--brand);
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.25);
}
.cg-html-thumb {
  display: block;
  width: 100%;
  height: 100%;
  pointer-events: none;
  background: #fff;
}
.cg-html-thumb :deep(.html-card-loading) {
  font-size: 0;
}
.cg-html-thumb :deep(.html-card-spinner) {
  width: 12px;
  height: 12px;
}
.cg-thumb-fallback {
  width: 100%;
  height: 100%;
  padding: 7px 8px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  background: linear-gradient(
    135deg,
    rgba(99, 102, 241, 0.18),
    rgba(168, 85, 247, 0.12)
  );
  color: var(--text-primary);
}
.cg-thumb-fallback.type-viz {
  background: linear-gradient(
    135deg,
    rgba(20, 184, 166, 0.18),
    rgba(59, 130, 246, 0.12)
  );
}
.cg-thumb-fallback.type-quiz {
  background: linear-gradient(
    135deg,
    rgba(245, 158, 11, 0.2),
    rgba(16, 185, 129, 0.12)
  );
}
.cg-thumb-title {
  font-size: 9px;
  line-height: 1.25;
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
}
.cg-thumb-lines {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.cg-thumb-lines span {
  height: 3px;
  border-radius: 99px;
  background: rgba(99, 102, 241, 0.22);
}
.cg-thumb-lines span:nth-child(2) {
  width: 74%;
}
.cg-thumb-lines span:nth-child(3) {
  width: 52%;
}
.cg-thumb-chip {
  align-self: flex-start;
  padding: 1px 5px;
  border-radius: 99px;
  background: rgba(255, 255, 255, 0.76);
  color: var(--brand);
  font-size: 8px;
  font-weight: 700;
}
.cg-type-label {
  font-size: 9px;
  color: var(--brand-light);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.cg-active-badge {
  position: absolute;
  bottom: 4px;
  right: 4px;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--brand);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
}

/* 卡片标题 */
.cg-info {
  width: 100%;
  text-align: center;
}
.cg-title {
  font-size: 10px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 90px;
}
.cg-title--loading {
  color: var(--text-dim);
}
.cg-stage-label {
  font-size: 9px;
  color: var(--brand-light);
  margin-top: 1px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 占位骨架屏 */
.cg-skeleton {
  width: 90px;
  height: 64px;
  border-radius: 6px;
  border: 2px solid var(--border-active);
  overflow: hidden;
  position: relative;
  background: var(--bg-hover);
}
.cg-shimmer {
  position: absolute;
  inset: 0;
  background: linear-gradient(
    90deg,
    transparent 0%,
    rgba(99, 102, 241, 0.12) 40%,
    rgba(99, 102, 241, 0.22) 50%,
    rgba(99, 102, 241, 0.12) 60%,
    transparent 100%
  );
  background-size: 200% 100%;
  animation: shimmer 1.6s ease infinite;
}
.cg-stage-icon {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--brand-light);
  opacity: 0.7;
}
.cg-spin {
  animation: spin 1.2s linear infinite;
}

@keyframes shimmer {
  0% {
    background-position: 200% 0;
  }
  100% {
    background-position: -200% 0;
  }
}

.gen-pulse {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--brand);
  animation: pulse 1.2s ease infinite;
}

/* 时间线导航（已替换为 card-gallery，保留备用） */

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
.at-logo-avatar {
  width: 34px;
  height: 34px;
  border-radius: 50%;
  overflow: hidden;
  flex-shrink: 0;
}
.at-logo-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
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
  gap: 10px;
  margin-bottom: 18px;
}
.msg-row.user {
  flex-direction: row-reverse;
}
.msg-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-width: 82%;
}
.msg-row.user .msg-col {
  align-items: flex-end;
}
.msg-bubble {
  padding: 10px 14px;
  border-radius: 16px;
  font-size: 13.5px;
  line-height: 1.75;
  min-width: 0;
  word-break: break-word;
}
.msg-bubble.assistant {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.09);
  color: var(--text-primary);
  border-top-left-radius: 4px;
  padding: 12px 16px;
  box-shadow:
    0 2px 12px rgba(0, 0, 0, 0.3),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}
.msg-bubble.user {
  background: var(--gradient-brand);
  color: white;
  border-top-right-radius: 4px;
  box-shadow: 0 2px 16px rgba(99, 102, 241, 0.35);
}
/* Light theme 适配 */
[data-theme="light"] .msg-bubble.assistant {
  background: #fff;
  border-color: rgba(0, 0, 0, 0.08);
  box-shadow:
    0 2px 12px rgba(0, 0, 0, 0.07),
    0 1px 3px rgba(0, 0, 0, 0.05);
}

/* ── 消息头像 ─────────────────────────────────────────────── */
.msg-av {
  flex-shrink: 0;
}
.msg-av .agent-avatar {
  width: 28px;
  height: 28px;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}
.msg-av .msg-agent-avatar {
  background: none;
  box-shadow: none;
  overflow: hidden;
}
.msg-av .msg-agent-avatar img {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  object-fit: cover;
  display: block;
}
.user-avatar {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--gradient-brand);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 11px;
  font-weight: 700;
  color: white;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.3);
}

/* ── stepBlocks：执行步骤块 ─────────────────────────────────── */
.msg-step-blocks {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 8px;
}

/* 每个 step 的容器 */
.msb-block {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

/* ── Think 块 / ToolCall 块 样式已迁移到组件 ThinkBlock.vue / ToolCallBlock.vue ── */

/* 最终回复淡入：只对 assistant 消息生效，用户消息直接可见 */
.msg-bubble.user .msg-text {
  opacity: 1;
}
.msg-bubble.assistant .msg-text {
  opacity: 0;
  animation: none;
}
.msg-bubble.assistant .msg-text--ready {
  animation: msgFadeIn 0.4s ease forwards;
}
@keyframes msgFadeIn {
  from {
    opacity: 0;
    transform: translateY(4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* ── 通用：分区标签 + 滚动区域 ── */
.msb-section {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.msb-section-label {
  font-size: 10px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}
.msb-scroll-area {
  max-height: 56px; /* 约 2-3 行 */
  overflow-y: auto;
  font-size: 11px;
  font-family: "JetBrains Mono", "Fira Code", ui-monospace, monospace;
  color: var(--text-secondary);
  line-height: 1.55;
  white-space: pre-wrap;
  word-break: break-all;
  padding: 4px 6px;
  background: rgba(0, 0, 0, 0.15);
  border-radius: 4px;
  scrollbar-width: thin;
  scrollbar-color: rgba(255, 255, 255, 0.1) transparent;
}
.msb-scroll-area::-webkit-scrollbar {
  width: 3px;
}
.msb-scroll-area::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 2px;
}

/* 参数区：蓝色调 */
.msb-args {
  color: #7dd3fc;
}
/* 日志区：绿色调 */
.msb-logs {
  color: var(--text-secondary);
}

/* 日志条目 */
.msb-log-item {
  display: flex;
  gap: 5px;
  align-items: flex-start;
  padding: 1px 0;
}
.msb-log-prefix {
  flex-shrink: 0;
}
.msb-log-text {
  flex: 1;
}
.msb-log-item.agent_think .msb-log-text {
  color: #c4b5fd;
}
.msb-log-item.agent_tool .msb-log-text {
  color: #6ee7b7;
}

/* 结果摘要 */
.msb-result-text {
  font-size: 11px;
  color: var(--text-dim);
  padding: 3px 6px;
  background: rgba(52, 211, 153, 0.06);
  border-radius: 4px;
  border-left: 2px solid rgba(52, 211, 153, 0.3);
  white-space: pre-wrap;
  word-break: break-all;
}

/* spin 动画（复用） */
.ms-spin {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  border: 1.5px solid var(--brand-light);
  border-top-color: transparent;
  animation: spin 0.7s linear infinite;
  display: inline-block;
}
.ms-spin-green {
  border-color: #34d399;
  border-top-color: transparent;
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
  padding: 0 2px;
  letter-spacing: 0.02em;
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
.iz-input-wrap.quiz-locked {
  border-color: var(--brand, #f59e0b);
  background: rgba(245, 158, 11, 0.04);
  cursor: not-allowed;
}
/* Quiz 锁定 toast */
.quiz-lock-toast {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 8px 13px;
  margin-bottom: 6px;
  background: rgba(245, 158, 11, 0.1);
  border: 1px solid rgba(245, 158, 11, 0.3);
  border-radius: var(--radius-md, 8px);
  font-size: 13px;
  color: #b45309;
  font-weight: 500;
}
.quiz-toast-enter-active,
.quiz-toast-leave-active {
  transition: all 0.25s ease;
}
.quiz-toast-enter-from,
.quiz-toast-leave-to {
  opacity: 0;
  transform: translateY(6px);
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
  padding-left: 1.5em;
  margin: 6px 0;
  list-style-position: outside;
}
.msg-bubble.assistant .msg-text ul {
  list-style-type: disc;
}
.msg-bubble.assistant .msg-text ol {
  list-style-type: decimal;
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

/* ═══ 习题美化 ═══ */

/* ── 进度条 ── */

/* ── 题目卡片 ── */

/* ── 选项 ── */

/* ── 填空/简答输入 ── */

/* ── 翻页 ── */

/* ── 判分结果页 ── */
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

.icon-correct {
  color: #10b981;
}
.icon-wrong {
  color: #ef4444;
}

/* ── AI 学习建议 ── */

/* ── 重做 ── */

/* ── 离开确认弹窗 ─────────────────────────────────────────── */
.leave-confirm-overlay {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(0, 0, 0, 0.45);
  backdrop-filter: blur(4px);
}
.leave-confirm-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--radius-xl, 16px);
  padding: 32px 36px;
  max-width: 380px;
  width: 90%;
  text-align: center;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
  animation: lc-pop 0.2s ease-out;
}
@keyframes lc-pop {
  from {
    opacity: 0;
    transform: scale(0.92);
  }
  to {
    opacity: 1;
    transform: scale(1);
  }
}
.lc-icon {
  font-size: 36px;
  margin-bottom: 12px;
}
.lc-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.lc-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  margin-bottom: 24px;
}
.lc-desc strong {
  color: var(--danger, #ef4444);
}
.lc-actions {
  display: flex;
  gap: 12px;
  justify-content: center;
}
.lc-actions .btn {
  min-width: 100px;
  padding: 8px 20px;
  border-radius: var(--radius-md);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.btn-danger {
  background: var(--danger, #ef4444);
  color: #fff;
  border: 1px solid var(--danger, #ef4444);
}
.btn-danger:hover {
  background: #dc2626;
  border-color: #dc2626;
}
</style>
