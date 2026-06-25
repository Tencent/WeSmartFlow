<template>
  <div class="chat-layout">
    <!-- 状态1：输入主题 -->
    <transition name="fade">
      <div v-if="phase === 'idle'" class="topic-entry">
        <div class="te-bg-grid" />
        <div class="te-bg-glow te-bg-glow-1" />
        <div class="te-bg-glow te-bg-glow-2" />

        <div class="te-container">
          <header class="te-head">
            <div class="te-tag">
              <span class="te-dot" />
              AI-Driven Learning · Immersive Mode
            </div>
            <h1 class="te-title">
              交给我吧，<br />
              <span class="te-title-grad">从第一页讲义到最后一道习题。</span>
            </h1>
            <p class="te-sub">
              让我为你铺好整条路。完整大纲、PDF讲义、语音讲解、习题练习，<br />
              我把一切准备到最好，<em>只等你来</em>。
            </p>
          </header>

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
              placeholder="输入你想学习的主题..."
              autofocus
              @keydown.enter="startImmersive"
              @focus="topicFocused = true"
              @blur="topicFocused = false"
            />
            <div v-if="topicInput.trim()" class="te-input-hint ok">
              <span>💫</span> 按 Enter 开始生成课件
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
            class="start-btn"
            :disabled="!topicInput.trim()"
            @click="startImmersive"
          >
            🤖 开始生成课件
          </button>
        </div>
      </div>
    </transition>

    <!-- 状态2：学习中（左右分栏） -->
    <transition name="fade">
      <div v-if="phase !== 'idle'" class="learn-wrap">
        <!-- 左侧展示区 -->
        <div class="slide-panel">
          <div class="slide-toolbar">
            <div class="st-left">
              <button class="back-btn" title="返回" @click="handleBack">
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
                <span class="st-topic-icon">🤖</span>
                <span class="st-topic-name">{{ currentTopic }}</span>
              </div>
            </div>
          </div>

          <!-- 续传提示横幅：恢复历史会话且未完成时由用户决定是否继续 -->
          <div v-if="imResumePrompt && !imGenerating" class="im-resume-banner">
            <div class="im-resume-info">
              <div class="im-resume-title">📚 这门课程还没生成完</div>
              <div class="im-resume-desc">
                <template v-if="imOutline?.chapters?.length">
                  已完成
                  <strong>{{ imChapters.length }}</strong>
                  /
                  <strong>{{ imOutline.chapters.length }}</strong>
                  章，剩余
                  <strong>
                    {{
                      Math.max(imOutline.chapters.length - imChapters.length, 0)
                    }}
                  </strong>
                  章未生成。
                </template>
                <template v-else> 本课程仍有内容未完成生成。 </template>
                你可以现在继续生成，也可以先浏览已有内容。
              </div>
            </div>
            <div class="im-resume-actions">
              <button
                class="im-resume-btn-ghost"
                @click="imResumePrompt = false"
              >
                稍后再说
              </button>
              <button class="im-resume-btn-primary" @click="imResumeGenerate">
                ▶ 继续生成
              </button>
            </div>
          </div>

          <!-- 阶段进度条 -->
          <div v-if="imGenerating" class="im-progress-wrap">
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

          <!-- LearningCanvas：主内容区，分页展示 -->
          <div class="slide-stage learning-stage">
            <div
              v-if="canvasPages.length > 0"
              class="learning-canvas"
              :class="{ 'is-card-page': currentCanvasPage?.isCard }"
            >
              <section
                v-for="block in currentCanvasPage?.blocks || []"
                :key="block.id"
                class="canvas-block"
                :class="[
                  `cb-${block.type}`,
                  `is-${block.status}`,
                  { 'cb-fullpage-card': currentCanvasPage?.isCard },
                ]"
              >
                <div class="cb-head">
                  <div>
                    <div class="cb-kicker">{{ blockTypeLabel(block) }}</div>
                    <h3 class="cb-title">{{ block.title || block.id }}</h3>
                  </div>
                  <span class="cb-status" :class="block.status">{{
                    blockStatusLabel(block.status)
                  }}</span>
                </div>

                <div
                  v-if="block.type === 'outline'"
                  class="plan-outline-card md-render-askable"
                  @mouseup="onMdMouseUp($event)"
                >
                  <p class="plan-overview">
                    {{
                      block.data?.outline?.overview ||
                      "学习大纲已生成，系统正在继续准备后续内容。"
                    }}
                  </p>
                  <div class="plan-chapter-grid">
                    <div
                      v-for="ch in block.data?.outline?.chapters || []"
                      :key="ch.chapter_id"
                      class="plan-chapter-card"
                    >
                      <div class="pcc-index">{{ ch.chapter_id }}</div>
                      <div class="pcc-main">
                        <div class="pcc-title">{{ ch.title }}</div>
                        <div class="pcc-desc">{{ ch.description }}</div>
                        <div class="pcc-kps">
                          <span
                            v-for="kp in (ch.knowledge_points || []).slice(
                              0,
                              4,
                            )"
                            :key="kp"
                            >{{ kp }}</span
                          >
                        </div>
                      </div>
                    </div>
                  </div>
                </div>

                <div v-else-if="block.type === 'md'" class="canvas-md">
                  <div
                    v-if="
                      block.data?.subtype === 'learning_plan' ||
                      block.data?.subtype === 'personalized_plan'
                    "
                    class="learning-plan-summary"
                  >
                    <div class="lps-pill">
                      📋 预计 {{ block.data?.estimated_chapters || 0 }} 个章节
                    </div>
                    <div class="lps-text">
                      个性化学习建议已就绪，结合了你的学习画像。PDF
                      和后续章节会继续在后台生成。
                    </div>
                  </div>
                  <div
                    v-else-if="block.data?.subtype === 'chapter_content'"
                    class="chapter-content-summary"
                  >
                    <div class="ccs-pill">📖 核心要点</div>
                    <div class="ccs-text">
                      此内容在 PDF 生成前已可阅读，帮你更快理解本章核心。
                    </div>
                  </div>
                  <div
                    class="md-render md-render-askable"
                    @mouseup="onMdMouseUp($event)"
                    v-html="renderMd(block.data?.markdown || '')"
                  />
                </div>

                <div
                  v-else-if="block.type === 'quiz_batch'"
                  class="canvas-quiz md-render-askable"
                  @mouseup="onMdMouseUp($event)"
                >
                  <div class="quiz-batch-note">
                    🎯 闯关式小测：先完成
                    <strong>3 道简单</strong>题，再决定是否挑战
                    <strong>中等</strong> 与 <strong>困难</strong>。
                  </div>

                  <!-- 阶段进度条：可视化已通关情况 -->
                  <div class="quiz-stage-rail">
                    <div
                      v-for="(lv, idx) in ['easy', 'medium', 'hard']"
                      :key="lv"
                      class="quiz-rail-node"
                      :class="{
                        active: currentStage(block.id) === lv,
                        done: isStageCleared(block, lv),
                      }"
                    >
                      <span class="rail-dot">{{ idx + 1 }}</span>
                      <span class="rail-label">
                        {{
                          lv === "easy"
                            ? "🟢 简单"
                            : lv === "medium"
                              ? "🟡 中等"
                              : "🔴 困难"
                        }}
                      </span>
                      <span class="rail-score">
                        {{ stageProgress(block, lv).correct }} /
                        {{ stageProgress(block, lv).total }}
                      </span>
                    </div>
                  </div>

                  <!-- 当前阶段题组 -->
                  <div
                    v-if="
                      currentStage(block.id) !== 'done' &&
                      groupedBlockQuestions(block)[currentStage(block.id)]
                        ?.length
                    "
                    class="quiz-stage"
                    :class="'quiz-stage-' + currentStage(block.id)"
                  >
                    <div class="quiz-stage-head">
                      <span
                        class="quiz-stage-tag"
                        :class="'tag-' + currentStage(block.id)"
                      >
                        {{
                          currentStage(block.id) === "easy"
                            ? "🟢 简单"
                            : currentStage(block.id) === "medium"
                              ? "🟡 中等"
                              : "🔴 困难挑战"
                        }}
                      </span>
                      <span class="quiz-stage-progress">
                        已答
                        {{ stageProgress(block, currentStage(block.id)).done }}
                        /
                        {{ stageProgress(block, currentStage(block.id)).total }}
                      </span>
                    </div>

                    <div class="quiz-stage-body">
                      <div
                        v-for="(q, qi) in groupedBlockQuestions(block)[
                          currentStage(block.id)
                        ]"
                        :key="q.id || qi"
                        class="canvas-question"
                        :class="{
                          'q-correct': q.completed && q.judgeResult === true,
                          'q-wrong': q.completed && q.judgeResult === false,
                          'q-done': q.completed,
                        }"
                      >
                        <div class="cq-head">
                          <span>第 {{ qi + 1 }} 题</span>
                          <span
                            class="cq-tag"
                            :class="'tag-' + currentStage(block.id)"
                          >
                            {{
                              currentStage(block.id) === "easy"
                                ? "简单"
                                : currentStage(block.id) === "medium"
                                  ? "中等"
                                  : "困难"
                            }}
                          </span>
                        </div>
                        <div
                          class="cq-stem"
                          v-html="renderMd(q.question || q.stem || '')"
                        />
                        <div v-if="q.options?.length" class="cq-options">
                          <button
                            v-for="(opt, oi) in q.options"
                            :key="oi"
                            class="cq-option"
                            :class="{
                              selected: q.userAnswer === oi,
                              'opt-correct':
                                q.completed && q.correctIndex === oi,
                              'opt-wrong':
                                q.completed &&
                                q.userAnswer === oi &&
                                q.correctIndex !== oi,
                              disabled: q.completed,
                            }"
                            :disabled="q.completed"
                            @click="selectOption(q, oi)"
                          >
                            <span>{{
                              q.optionLabels?.[oi] ||
                              String.fromCharCode(65 + oi)
                            }}</span>
                            <span
                              v-html="
                                renderMd(
                                  typeof opt === 'string'
                                    ? opt
                                    : opt.text || '',
                                )
                              "
                            />
                          </button>
                        </div>

                        <div
                          v-if="q.feedback"
                          class="cq-feedback"
                          :class="{
                            'fb-correct': q.judgeResult === true,
                            'fb-wrong': q.judgeResult === false,
                            'fb-info': q.judgeResult === null,
                          }"
                        >
                          {{ q.feedback }}
                        </div>

                        <div class="cq-actions">
                          <button
                            class="cq-action"
                            @click="toggleQuestionExplanation(q)"
                          >
                            {{ q.showExplanation ? "收起解析" : "查看解析" }}
                          </button>
                          <button
                            class="cq-action primary"
                            :disabled="q.completed"
                            @click="markQuestionDone(q)"
                          >
                            {{ q.completed ? "✓ 已完成" : "提交答案" }}
                          </button>
                        </div>

                        <div
                          v-if="q.showExplanation"
                          class="cq-explanation"
                          v-html="
                            renderMd(
                              q.explanation || '暂无解析，后续会按需生成。',
                            )
                          "
                        />
                      </div>
                    </div>

                    <!-- 阶段全部完成后的引导卡片 -->
                    <div
                      v-if="isStageAllAnswered(block, currentStage(block.id))"
                      class="quiz-stage-next"
                    >
                      <div class="qsn-summary">
                        本阶段成绩：
                        <strong>{{
                          stageProgress(block, currentStage(block.id)).correct
                        }}</strong>
                        /
                        {{ stageProgress(block, currentStage(block.id)).total }}
                        正确
                      </div>
                      <div class="qsn-actions">
                        <button
                          v-if="hasNextStage(block, currentStage(block.id))"
                          class="qsn-btn primary"
                          @click="goNextStage(block)"
                        >
                          {{
                            nextStageOf(currentStage(block.id)) === "medium"
                              ? "⚡ 进入中等挑战"
                              : "🔥 接受困难挑战"
                          }}
                        </button>
                        <button
                          v-if="hasNextStage(block, currentStage(block.id))"
                          class="qsn-btn ghost"
                          @click="finishStage(block)"
                        >
                          就到这里，结束本测
                        </button>
                        <button
                          v-else
                          class="qsn-btn primary"
                          @click="finishStage(block)"
                        >
                          🏆 完成全部挑战
                        </button>
                      </div>
                    </div>
                  </div>

                  <!-- 全部阶段完成后的总结 -->
                  <div
                    v-else-if="currentStage(block.id) === 'done'"
                    class="quiz-final"
                  >
                    <div class="qf-trophy">🏆</div>
                    <div class="qf-title">小测完成！</div>
                    <div class="qf-stats">
                      <div
                        v-for="lv in ['easy', 'medium', 'hard']"
                        :key="lv"
                        class="qf-stat"
                      >
                        <span class="qf-stat-label">
                          {{
                            lv === "easy"
                              ? "简单"
                              : lv === "medium"
                                ? "中等"
                                : "困难"
                          }}
                        </span>
                        <span class="qf-stat-value">
                          {{ stageProgress(block, lv).correct }} /
                          {{ stageProgress(block, lv).total }}
                        </span>
                      </div>
                    </div>
                    <button class="qsn-btn ghost" @click="resetQuiz(block)">
                      ↻ 重新挑战
                    </button>
                  </div>
                </div>

                <div v-else-if="block.type === 'pdf'" class="canvas-pdf-embed">
                  <div class="pdf-embed-header">
                    <span class="pdf-embed-icon">📄</span>
                    <span class="pdf-embed-title">{{
                      block.title || "PDF 讲义"
                    }}</span>
                    <button
                      class="pdf-embed-fullscreen"
                      title="新窗口打开"
                      @click="openPdfBlock(block)"
                    >
                      <svg
                        width="14"
                        height="14"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                      >
                        <polyline points="15 3 21 3 21 9" />
                        <polyline points="9 21 3 21 3 15" />
                        <line x1="21" y1="3" x2="14" y2="10" />
                        <line x1="3" y1="21" x2="10" y2="14" />
                      </svg>
                    </button>
                  </div>
                  <div
                    :ref="
                      (el) => {
                        if (el) initPdfBlock(block.id);
                      }
                    "
                    class="pdf-embed-body"
                  >
                    <!-- 缩略图侧栏 -->
                    <div
                      v-if="(pdfBlockStates[block.id]?.totalPages || 0) > 1"
                      class="pdf-thumbs"
                    >
                      <div
                        v-for="n in pdfBlockStates[block.id]?.totalPages || 0"
                        :key="n"
                        class="pdf-thumb-item"
                        :class="{
                          active:
                            (pdfBlockStates[block.id]?.currentPage || 1) === n,
                        }"
                        @click="pdfBlockGotoPage(block.id, n)"
                      >
                        <canvas
                          :ref="(el) => setPdfThumbRef(block.id, n, el)"
                          class="pdf-thumb-canvas"
                        ></canvas>
                        <div class="pdf-thumb-label">{{ n }}</div>
                      </div>
                    </div>
                    <!-- 主视图区 -->
                    <div class="pdf-main-area">
                      <div class="pdf-main-canvas-wrap">
                        <canvas
                          :ref="(el) => setPdfMainCanvasRef(block.id, el)"
                          class="pdf-main-canvas"
                        ></canvas>
                        <div
                          v-if="pdfBlockStates[block.id]?.error"
                          class="pdf-embed-loading pdf-embed-error"
                        >
                          {{ pdfBlockStates[block.id].error }}
                        </div>
                        <div
                          v-else-if="!pdfBlockStates[block.id]?.totalPages"
                          class="pdf-embed-loading"
                        >
                          正在加载 PDF...
                        </div>
                      </div>
                      <div
                        v-if="(pdfBlockStates[block.id]?.totalPages || 0) > 0"
                        class="pdf-main-toolbar"
                      >
                        <button
                          class="pdf-nav-btn"
                          :disabled="
                            (pdfBlockStates[block.id]?.currentPage || 1) <= 1
                          "
                          @click="
                            pdfBlockGotoPage(
                              block.id,
                              (pdfBlockStates[block.id]?.currentPage || 1) - 1,
                            )
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
                            <polyline points="15 18 9 12 15 6" />
                          </svg>
                          上一页
                        </button>
                        <span class="pdf-nav-info">
                          {{ pdfBlockStates[block.id]?.currentPage || 1 }} /
                          {{ pdfBlockStates[block.id]?.totalPages || 0 }}
                        </span>
                        <button
                          class="pdf-nav-btn"
                          :disabled="
                            (pdfBlockStates[block.id]?.currentPage || 1) >=
                            (pdfBlockStates[block.id]?.totalPages || 0)
                          "
                          @click="
                            pdfBlockGotoPage(
                              block.id,
                              (pdfBlockStates[block.id]?.currentPage || 1) + 1,
                            )
                          "
                        >
                          下一页
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
                        </button>
                        <button
                          v-if="pdfBlockAudioUrl(block)"
                          class="pdf-nav-btn im-audio-btn"
                          :class="{ playing: imIsPlaying }"
                          @click="imPlayAudio(pdfBlockAudioUrl(block))"
                        >
                          {{ imIsPlaying ? "⏸ 暂停语音" : "🔊 播放本页" }}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>

                <div
                  v-else-if="block.type === 'chapter_status'"
                  class="chapter-status-card"
                >
                  <div class="chapter-status-line">
                    <span
                      v-if="block.status === 'generating'"
                      class="gen-pulse"
                    />
                    <span>{{
                      block.status === "generating"
                        ? "正在生成本章内容"
                        : "本章内容已就绪"
                    }}</span>
                  </div>
                  <div class="chapter-status-sub">
                    {{ block.data?.stage || "" }}
                  </div>
                </div>

                <div
                  v-else-if="block.type === 'knowledge_card'"
                  class="canvas-html-card"
                >
                  <HtmlCard
                    v-if="block.data?.fileId"
                    :file-id="block.data.fileId"
                    :session-id="currentSessionId || ''"
                  />
                  <div v-else class="html-card-loading">
                    <span class="gen-pulse" />
                    <span>正在生成知识卡片...</span>
                  </div>
                </div>

                <div
                  v-else-if="block.type === 'viz_card'"
                  class="canvas-viz-card"
                >
                  <VizCard
                    v-if="block.data?.vizId"
                    :viz-id="block.data.vizId"
                    :title="block.title || ''"
                  />
                  <div v-else class="html-card-loading">
                    <span class="gen-pulse" />
                    <span>正在生成交互可视化...</span>
                  </div>
                </div>

                <div
                  v-else-if="block.type === 'quiz_card'"
                  class="canvas-quiz-card"
                >
                  <QuizCard
                    v-if="block.data?.quizId"
                    :quiz-id="block.data.quizId"
                    @answered="onImQuizAnswered"
                  />
                  <div v-else class="html-card-loading">
                    <span class="gen-pulse" />
                    <span>正在生成练习题...</span>
                  </div>
                </div>

                <div v-else class="canvas-fallback">
                  <pre>{{ block }}</pre>
                </div>
              </section>

              <!-- 选中文本"问AI"气泡 -->
              <Transition name="im-bubble">
                <div
                  v-if="imAskBubble.visible"
                  class="im-ask-ai-bubble"
                  :style="{
                    left: imAskBubble.x + 'px',
                    top: imAskBubble.y + 'px',
                  }"
                  @mousedown.prevent
                  @click="openImAskPanel"
                >
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    stroke-width="2.5"
                  >
                    <path
                      d="M12 2a10 10 0 0 1 10 10c0 5.52-4.48 10-10 10S2 17.52 2 12 6.48 2 12 2z"
                    />
                    <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                  问AI
                </div>
              </Transition>

              <!-- AI 解释浮窗 -->
              <Transition name="im-panel">
                <div
                  v-if="imAskPanel.visible"
                  class="im-ask-ai-panel"
                  :style="imAskPanelStyle"
                  @mousedown.stop
                >
                  <div class="im-aap-header">
                    <div class="im-aap-title">
                      <svg
                        width="13"
                        height="13"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2"
                      >
                        <circle cx="12" cy="12" r="10" />
                        <path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3" />
                        <line x1="12" y1="17" x2="12.01" y2="17" />
                      </svg>
                      AI 解释
                    </div>
                    <button class="im-aap-close" @click="closeImAskPanel">
                      <svg
                        width="13"
                        height="13"
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
                  <div class="im-aap-selected-text">
                    <span class="im-aap-selected-label">选中内容</span>
                    <span class="im-aap-selected-content">{{
                      imAskPanel.selectedText
                    }}</span>
                  </div>
                  <div ref="imAskBodyRef" class="im-aap-body">
                    <div
                      v-if="imAskPanel.loading && !imAskPanel.reply"
                      class="im-aap-thinking"
                    >
                      <div class="im-aap-dots"><span /><span /><span /></div>
                      <span>正在思考...</span>
                    </div>
                    <div
                      v-else-if="imAskPanel.reply"
                      class="im-aap-reply"
                      v-html="renderMd(imAskPanel.reply)"
                    ></div>
                    <div v-else-if="imAskPanel.error" class="im-aap-error">
                      {{ imAskPanel.error }}
                    </div>
                  </div>
                  <div class="im-aap-footer">
                    <button
                      v-if="!imAskPanel.loading"
                      class="im-aap-btn-retry"
                      @click="doImAsk"
                    >
                      <svg
                        width="11"
                        height="11"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        stroke-width="2.5"
                      >
                        <polyline points="1 4 1 10 7 10" />
                        <path d="M3.51 15a9 9 0 1 0 .49-3.5" />
                      </svg>
                      重新解释
                    </button>
                    <span v-else class="im-aap-loading-hint">生成中...</span>
                  </div>
                </div>
              </Transition>
            </div>

            <div v-else-if="imGenerating" class="im-generating">
              <div class="im-gen-icon">{{ imStageIcon }}</div>
              <div class="im-gen-title">正在生成课件</div>
              <div class="im-gen-topic">{{ currentTopic }}</div>
              <div class="im-gen-msg">{{ imStatusMessage }}</div>
            </div>
            <div v-else-if="!imGenerating" class="no-card-hint">
              <div class="nch-icon">📚</div>
              <div class="nch-title">等待课件生成...</div>
            </div>
          </div>

          <!-- 分页导航条 -->
          <div v-if="canvasPages.length > 1" class="canvas-page-nav">
            <button
              class="cpn-arrow"
              :disabled="currentCanvasPageIndex <= 0"
              @click="prevCanvasPage"
            >
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="2.5"
              >
                <polyline points="15 18 9 12 15 6" />
              </svg>
            </button>
            <div class="cpn-pages">
              <div
                v-for="(page, i) in canvasPages"
                :key="page.id"
                class="cpn-item"
                :class="{
                  active: i === currentCanvasPageIndex,
                  'is-card': page.isCard,
                }"
                :title="page.label"
                @click="goToCanvasPage(i)"
              >
                <span class="cpn-icon">{{ page.icon }}</span>
                <span class="cpn-label">{{ page.label }}</span>
              </div>
            </div>
            <button
              class="cpn-arrow"
              :disabled="currentCanvasPageIndex >= canvasPages.length - 1"
              @click="nextCanvasPage"
            >
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
            </button>
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
          <div class="im-sidebar-inner">
            <!-- 单一 Agent 视图头部 -->
            <div class="im-agent-header">
              <div class="im-agent-header-left">
                <div class="agent-avatar" style="width: 28px; height: 28px">
                  <svg
                    width="12"
                    height="12"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="white"
                    stroke-width="2.5"
                  >
                    <path d="M9.09 9a3 3 0 015.83 1c0 2-3 3-3 3" />
                    <line x1="12" y1="17" x2="12.01" y2="17" />
                  </svg>
                </div>
                <div>
                  <div class="im-agent-header-title">智流 Agent</div>
                  <div class="im-agent-header-status">
                    {{ imGenerating ? "正在思考..." : "随时为你解答" }}
                  </div>
                </div>
              </div>
              <button
                class="im-agent-toggle-reasoning"
                :class="{ active: showReasoning }"
                title="显示/隐藏推理过程"
                @click="showReasoning = !showReasoning"
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
                <span v-if="imLogs.length" class="reasoning-count">{{
                  imLogs.length
                }}</span>
              </button>
            </div>
            <div class="im-tab-content">
              <!-- 统一 Agent 视图 -->
              <div class="im-agent-chat">
                <div ref="imAgentMsgRef" class="im-agent-messages">
                  <!-- 推理过程（可折叠）：仅展示思考流，不再叠加课程大纲 -->
                  <transition name="slide-down">
                    <div v-if="showReasoning" class="im-reasoning-panel">
                      <div class="im-reasoning-header">
                        <svg
                          width="12"
                          height="12"
                          viewBox="0 0 24 24"
                          fill="none"
                          stroke="currentColor"
                          stroke-width="2"
                        >
                          <path d="M12 2L2 7l10 5 10-5-10-5z" />
                          <path d="M2 17l10 5 10-5" />
                          <path d="M2 12l10 5 10-5" />
                        </svg>
                        <span>推理过程</span>
                        <span class="im-reasoning-count"
                          >{{ imLogs.length }} 步</span
                        >
                      </div>
                      <div ref="imLogRef" class="im-reasoning-list">
                        <div
                          v-if="imLogs.length === 0"
                          class="im-reasoning-empty"
                        >
                          暂无推理记录，开始生成或对话后这里会实时显示 Agent
                          的思考过程
                        </div>
                        <div
                          v-for="(log, i) in imLogs"
                          :key="i"
                          class="im-reasoning-item"
                          :class="log.level"
                        >
                          <span class="im-reasoning-time">{{ log.time }}</span>
                          <span class="im-reasoning-msg">{{
                            log.message
                          }}</span>
                        </div>
                      </div>
                    </div>
                  </transition>

                  <!-- Agent 对话消息 -->
                  <div
                    v-for="(m, mi) in imAgentMessages"
                    :key="mi"
                    class="im-agent-msg"
                    :class="m.role"
                  >
                    <div v-if="m.role === 'assistant'" class="im-agent-msg-av">
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
            </div>
          </div>
        </div>
      </div>
    </transition>

    <!-- 离开确认弹窗 -->
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
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from "vue";
import { useRoute, onBeforeRouteLeave } from "vue-router";
import { sessionApi, BASE_URL, llmApi } from "@/api";
import {
  authHeaders,
  fetchAsBlobUrl,
  docRawUrl,
  docAssetUrl,
} from "@/api/base.js";
import { api } from "@/api/base.js";
import { renderMd } from "@/composables/useMarkdown.js";
import HtmlCard from "@/components/HtmlCard/HtmlCard.vue";
import VizCard from "@/components/VizCard/VizCard.vue";
import QuizCard from "@/components/QuizCard/QuizCard.vue";
import * as pdfjsLib from "pdfjs-dist/webpack.mjs";

// 使用 npm 包内嵌的 Worker 方案，webpack.mjs 会自动配置 Worker
// 配置 PDF.js 字体支持（与 ChatView 保持一致，已验证可用）
pdfjsLib.GlobalWorkerOptions.fontFamily =
  "'PingFang SC', 'Noto Sans CJK SC', 'Source Han Sans SC', 'FandolSong-Regular', 'Droid Sans Fallback', 'SimSun', 'Microsoft YaHei', sans-serif";
pdfjsLib.GlobalWorkerOptions.useSystemFonts = true;
pdfjsLib.GlobalWorkerOptions.cMapUrl =
  "https://unpkg.com/pdfjs-dist@5.6.205/cmaps/";
pdfjsLib.GlobalWorkerOptions.cMapPacked = true;

const route = useRoute();

// ── 阶段状态 ────────────────────────────────────────────────────
const phase = ref("idle");
const currentTopic = ref("");
const topicInput = ref("");
const topicFocused = ref(false);
const topicInputEl = ref(null);
const enableAudio = ref(false);
const enableExercises = ref(true);

// ── 沉浸式状态 ──────────────────────────────────────────────────
const currentSessionId = ref(null);
let sessionStartTime = null;

// ── AI 主导学习状态 ──────────────────────────────
const imGenerating = ref(false);
const imCompleted = ref(false);
const imProgress = ref(0);
const imCurrentStage = ref("");
const imStatusMessage = ref("");
const imOutline = ref(null);
const imChapters = ref([]);
// 返回未完成会话时，是否展示“继续生成”提示（交给用户决定）
const imResumePrompt = ref(false);
const imCurrentChapterIndex = ref(0);
const imCurrentPage = ref(1);
const imTotalPages = ref(0);
const imTab = ref("agent");
const showReasoning = ref(true);
const imLogs = ref([]);
const imPdfCanvas = ref(null);
const imLogRef = ref(null);
const imIsPlaying = ref(false);
const imExercisesHtml = ref("");
const imGeneratingChapterId = ref(0);
const imGeneratingChapterTitle = ref("");
const imPdfDocMap = new Map();
// PDF 渲染任务锁：每个 canvas 同一时间只允许一个 render task。
// 解决：连续切页/容器尺寸变化触发的并发 render 导致内容旋转错位/重影。
const imPdfRenderTasks = new WeakMap(); // canvas -> RenderTask
let imCurrentAudio = null;

// ── LearningCanvas 工作区 ───────────────────────────────────────
const canvasBlocks = ref([]);
const currentCanvasPageIndex = ref(0);
const workspaceStage = ref("");
const workspaceNextActions = ref([]);
const currentBlockId = ref(null);

// ── 分页逻辑：将 canvasBlocks 按规则分组为 pages ─────────────────
// 规则：
//   第一页：outline + md(learning_plan/personalized_plan)
//   每章一页：该章的 md(chapter_content) + pdf + quiz_batch
//   知识卡片每张一页
const canvasPages = computed(() => {
  const blocks = canvasBlocks.value;
  if (blocks.length === 0) return [];
  const pages = [];

  // 第一页：概览（大纲 + 个性化学习建议）
  const overviewBlocks = blocks.filter(
    (b) =>
      b.type === "outline" ||
      (b.type === "md" &&
        (b.data?.subtype === "learning_plan" ||
          b.data?.subtype === "personalized_plan")),
  );
  if (overviewBlocks.length > 0) {
    pages.push({
      id: "overview",
      label: "学习概览",
      icon: "📋",
      blocks: overviewBlocks,
    });
  }

  // 章节页：按 chapter_id 分组
  const chapterIds = [
    ...new Set(
      blocks
        .filter(
          (b) =>
            b.chapter_id &&
            (b.type === "md" || b.type === "pdf" || b.type === "quiz_batch"),
        )
        .map((b) => b.chapter_id),
    ),
  ].sort((a, b) => a - b);
  for (const chId of chapterIds) {
    const chBlocks = blocks.filter(
      (b) =>
        b.chapter_id === chId &&
        (b.type === "md" || b.type === "pdf" || b.type === "quiz_batch"),
    );
    if (chBlocks.length > 0) {
      const ch = imChapters.value.find((c) => c.chapter_id === chId);
      const label = ch?.title || `第${chId}章`;
      pages.push({ id: `ch_${chId}`, label, icon: "📖", blocks: chBlocks });
    }
  }

  // 知识卡片页：每张独占一页
  const cardBlocks = blocks.filter((b) => b.type === "knowledge_card");
  for (const card of cardBlocks) {
    pages.push({
      id: `card_${card.id}`,
      label: card.title || "知识卡片",
      icon: "🧠",
      blocks: [card],
      isCard: true,
    });
  }

  // 交互可视化页：每个独占一页
  const vizBlocks = blocks.filter((b) => b.type === "viz_card");
  for (const viz of vizBlocks) {
    pages.push({
      id: `viz_${viz.id}`,
      label: viz.title || "交互可视化",
      icon: "📊",
      blocks: [viz],
      isCard: true,
    });
  }

  // 练习题页：每题独占一页
  const quizBlocks = blocks.filter((b) => b.type === "quiz_card");
  for (const quiz of quizBlocks) {
    pages.push({
      id: `quiz_${quiz.id}`,
      label: quiz.title || "练习题",
      icon: "❓",
      blocks: [quiz],
      isCard: true,
    });
  }

  return pages;
});

const currentCanvasPage = computed(
  () => canvasPages.value[currentCanvasPageIndex.value] || null,
);

function goToCanvasPage(idx) {
  if (idx >= 0 && idx < canvasPages.value.length) {
    currentCanvasPageIndex.value = idx;
    // 如果切换到章节页，同步更新 imCurrentChapterIndex
    const page = canvasPages.value[idx];
    if (page?.id?.startsWith("ch_")) {
      const chId = parseInt(page.id.replace("ch_", ""));
      const chIdx = imChapters.value.findIndex((c) => c.chapter_id === chId);
      if (chIdx >= 0 && chIdx !== imCurrentChapterIndex.value) {
        imCurrentChapterIndex.value = chIdx;
      }
    }
  }
}
function nextCanvasPage() {
  goToCanvasPage(currentCanvasPageIndex.value + 1);
}
function prevCanvasPage() {
  goToCanvasPage(currentCanvasPageIndex.value - 1);
}

// ── 智流 Agent 对话 ─────────────────────────────────────────────
const imAgentMessages = ref([]);
const imAgentInput = ref("");
const imAgentGenerating = ref(false);
const imAgentMsgRef = ref(null);

// ── 习题交互 ────────────────────────────────────────────────────
const imParsedQuizzes = ref([]);
const imQuizJudging = ref(false);
const imQuizCurrent = ref(0);
const imQuizSubmitted = ref(false);
const imQuizAdvice = ref("");

// eslint-disable-next-line @typescript-eslint/no-unused-vars
const currentQuiz = computed(
  () => imParsedQuizzes.value[imQuizCurrent.value] || null,
);
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const imQuizAnsweredCount = computed(
  () =>
    imParsedQuizzes.value.filter(
      (q) => q.userAnswer !== null || q.userText.trim(),
    ).length,
);
const imQuizStats = computed(() => {
  const qs = imParsedQuizzes.value;
  return {
    correct: qs.filter((q) => q.judgeResult === true).length,
    wrong: qs.filter((q) => q.judgeResult === false).length,
    pending: qs.filter((q) => q.judgeResult === null).length,
  };
});
// eslint-disable-next-line @typescript-eslint/no-unused-vars
const imQuizScoreLevel = computed(() => {
  const total = imParsedQuizzes.value.length;
  if (total === 0) return "low";
  const ratio = imQuizStats.value.correct / total;
  if (ratio >= 0.8) return "great";
  if (ratio >= 0.5) return "good";
  return "low";
});

// ── 分栏拖拽 ─────────────────────────────────────────────────────
const chatWidth = ref(null);
const isDragging = ref(false);
function startResize(e) {
  isDragging.value = true;
  const startX = e.clientX;
  const startW = chatWidth.value || window.innerWidth * 0.45;
  function onMove(ev) {
    chatWidth.value = Math.max(
      280,
      Math.min(window.innerWidth * 0.7, startW - (ev.clientX - startX)),
    );
  }
  function onUp() {
    isDragging.value = false;
    document.removeEventListener("mousemove", onMove);
    document.removeEventListener("mouseup", onUp);
  }
  document.addEventListener("mousemove", onMove);
  document.addEventListener("mouseup", onUp);
}

// ── 阶段指示器 ──────────────────────────────────────────────────
const imBaseStages = [
  { key: "planner", icon: "📋", name: "规划" },
  { key: "researcher", icon: "🔍", name: "检索" },
  { key: "tex", icon: "📄", name: "PDF" },
  { key: "exercises", icon: "✏️", name: "习题" },
];
const imStages = computed(() =>
  enableAudio.value
    ? [...imBaseStages, { key: "tts", icon: "🔊", name: "语音" }]
    : imBaseStages,
);
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
const imStageIcon = computed(
  () =>
    imStages.value.find((s) => s.key === imCurrentStage.value)?.icon || "⚙️",
);
function isImStageComplete(key) {
  return (imStageOrder[imCurrentStage.value] || 0) > (imStageOrder[key] || 0);
}
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function isImChapterDone(chId) {
  return imChapters.value.some((c) => c.chapter_id === chId);
}
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function isImChapterCurrent(chId) {
  return imGeneratingChapterId.value === chId;
}

const imCurrentChapter = computed(
  () => imChapters.value[imCurrentChapterIndex.value] || null,
);
const imCurrentAudioUrl = computed(() => {
  const ch = imCurrentChapter.value;
  if (!ch?.audio_files?.length) return "";
  const pageIdx = imCurrentPage.value - 1;
  return getAudioUrl(ch.audio_files, pageIdx, ch.audio_doc_id || "");
});

function getAudioUrl(audioFiles = [], pageIdx = 0, audioDocId = "") {
  const af = audioFiles[pageIdx];
  if (!af || !af.success) return "";
  // 后端会在 audio_files 里返回完整 url（包括 /api/documents/{audio_doc_id}/asset/...）
  if (af.url) {
    return af.url.startsWith("http") ? af.url : `${BASE_URL}${af.url}`;
  }
  // 其次选：探底 audioDocId（例如服务重启后仅能从 chapter 属性拿到 audio_doc_id）
  if (audioDocId && af.filename) {
    return docAssetUrl(audioDocId, af.filename);
  }
  return "";
}

function pdfBlockAudioUrl(block) {
  const state = pdfBlockStates.value[block.id] || {};
  const pageIdx = (state.currentPage || 1) - 1;
  const audioFiles = block?.data?.audio_files || [];
  const audioDocId = block?.data?.audio_doc_id || "";
  if (audioFiles.length) {
    const url = getAudioUrl(audioFiles, pageIdx, audioDocId);
    if (url) return url;
  }
  const ch = imChapters.value.find(
    (item) => item.chapter_id === block.chapter_id,
  );
  if (ch?.audio_files?.length) {
    return getAudioUrl(ch.audio_files, pageIdx, ch.audio_doc_id || "");
  }
  return "";
}

// ── 工具函数 ─────────────────────────────────────────────────────
function now() {
  return new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  });
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

function blockTypeLabel(block) {
  const map = {
    outline: "学习大纲",
    md:
      block?.data?.subtype === "learning_plan" ||
      block?.data?.subtype === "personalized_plan"
        ? "个性化学习建议"
        : "文档",
    quiz_batch: "交互小测",
    pdf: "PDF 讲义",
    chapter_status: "章节状态",
    explanation: "解析",
    knowledge_card: "知识卡片",
    viz_card: "交互可视化",
    quiz_card: "练习题",
    audio: "语音",
    summary: "总结",
  };
  return map[block?.type] || "内容块";
}

// 当新 block 加入时，自动跳转到对应页面
watch(
  canvasPages,
  (newPages, oldPages) => {
    if (newPages.length > (oldPages?.length || 0)) {
      // 新增了页面，跳转到最后一页
      currentCanvasPageIndex.value = newPages.length - 1;
    }
  },
  { deep: false },
);

function blockStatusLabel(status) {
  return (
    {
      pending: "等待中",
      generating: "生成中",
      ready: "已就绪",
      failed: "失败",
    }[status] ||
    status ||
    "已就绪"
  );
}

function upsertCanvasBlock(block) {
  if (!block || !block.id) return;
  const idx = canvasBlocks.value.findIndex((b) => b.id === block.id);
  const next = { ...block, data: block.data || {} };
  if (idx >= 0) {
    canvasBlocks.value[idx] = { ...canvasBlocks.value[idx], ...next };
  } else {
    canvasBlocks.value.push(next);
  }
  if (next.type === "outline" && next.data?.outline) {
    imOutline.value = next.data.outline;
  }
  if (next.type === "quiz_batch") hydrateQuizBlock(next.id);
  // ✅ 续传/SSE 新增 PDF block 时主动触发加载，避免 :ref 钩子未触发导致一直转圈
  if (next.type === "pdf" && !pdfDocMap.has(next.id)) {
    nextTick(() => initPdfBlock(next.id));
  }
}

async function hydrateQuizBlock(blockId) {
  const block = canvasBlocks.value.find((b) => b.id === blockId);
  if (!block || block.data?.questions?.length) return;
  const docId = block.data?.doc_id || block.data?.exercises_doc_id;
  if (!docId) return;
  try {
    const res = await api.getRaw(`/api/documents/${docId}/raw`);
    const md = await res.text();
    let questions = parseExercises(md);
    // 难度排序兜底（easy → medium → hard）
    const order = { easy: 0, medium: 1, hard: 2 };
    questions = questions
      .map((q, i) => ({ ...q, _origIdx: i }))
      .sort((a, b) => {
        const da = order[a.difficulty] ?? 1;
        const db = order[b.difficulty] ?? 1;
        return da - db || a._origIdx - b._origIdx;
      });
    // 每个难度只保留 3 题（防 LLM 多吐 / 少吐导致 UI 不平衡）
    const perLevel = { easy: [], medium: [], hard: [] };
    questions.forEach((q) => {
      const d = q.difficulty || "medium";
      const arr = perLevel[d] || perLevel.medium;
      if (arr.length < 3) arr.push(q);
    });
    questions = [...perLevel.easy, ...perLevel.medium, ...perLevel.hard];
    block.data = { ...block.data, markdown: md, questions };
  } catch (e) {
    block.status = "failed";
    block.error = e.message || "习题加载失败";
  }
}

// 按难度分组后的结果：{ easy: [], medium: [], hard: [] }
function groupedBlockQuestions(block) {
  const all = block?.data?.questions || [];
  const groups = { easy: [], medium: [], hard: [] };
  all.forEach((q) => {
    const d = q.difficulty || "medium";
    (groups[d] || groups.medium).push(q);
  });
  return groups;
}

// 挑战阶段状态：'easy' | 'medium' | 'hard' | 'done'
const quizStageMap = ref({}); // { [blockId]: 'easy' | 'medium' | 'hard' | 'done' }
function currentStage(blockId) {
  return quizStageMap.value[blockId] || "easy";
}
function nextStageOf(stage) {
  if (stage === "easy") return "medium";
  if (stage === "medium") return "hard";
  return "done";
}
function hasNextStage(block, stage) {
  const next = nextStageOf(stage);
  if (next === "done") return false;
  return (groupedBlockQuestions(block)[next] || []).length > 0;
}
function goNextStage(block) {
  const cur = currentStage(block.id);
  quizStageMap.value = { ...quizStageMap.value, [block.id]: nextStageOf(cur) };
}
function finishStage(block) {
  quizStageMap.value = { ...quizStageMap.value, [block.id]: "done" };
  // 上报答题结果到后端，用于更新用户画像
  reportQuizResult(block);
}
function resetQuiz(block) {
  // 清空所有作答状态，回到 easy 阶段
  (block.data?.questions || []).forEach((q) => {
    q.userAnswer = undefined;
    q.completed = false;
    q.judgeResult = undefined;
    q.feedback = "";
    q.showExplanation = false;
  });
  quizStageMap.value = { ...quizStageMap.value, [block.id]: "easy" };
}
function isStageAllAnswered(block, level) {
  const list = groupedBlockQuestions(block)[level] || [];
  return list.length > 0 && list.every((q) => q.completed);
}
function isStageCleared(block, level) {
  // 该阶段已完成（不要求全对）
  return isStageAllAnswered(block, level);
}

// 完成进度：每个阶段已完成 / 答对题数
function stageProgress(block, level) {
  const list = groupedBlockQuestions(block)[level] || [];
  const done = list.filter((q) => q.completed).length;
  const correct = list.filter(
    (q) => q.completed && q.judgeResult === true,
  ).length;
  return { done, total: list.length, correct };
}

function toggleQuestionExplanation(q) {
  q.showExplanation = !q.showExplanation;
}

function selectOption(q, idx) {
  // 完成后禁止修改，避免用户事后改选造成反馈失真
  if (q.completed) return;
  q.userAnswer = idx;
  // 重选时清理上一次未提交状态提示
  if (q.judgeResult === null) q.feedback = "";
}

function markQuestionDone(q) {
  if (q.completed) return; // 重复点击不重复判定
  if (q.userAnswer === undefined || q.userAnswer === null) {
    q.feedback = "请先选择一个选项再提交。";
    q.judgeResult = null;
    return;
  }
  if (q.correctIndex >= 0) {
    q.judgeResult = q.userAnswer === q.correctIndex;
    const correctLabel =
      q.optionLabels?.[q.correctIndex] ||
      String.fromCharCode(65 + q.correctIndex);
    q.feedback = q.judgeResult
      ? `✅ 回答正确！`
      : `❌ 回答不正确，正确答案是 ${correctLabel}。`;
  } else {
    q.judgeResult = null;
    q.feedback = "已记录本题作答。";
  }
  q.completed = true;
}

/**
 * 上报习题作答结果到后端，用于更新用户画像中的知识点掌握度。
 * 在 finishStage 时调用（无论是"就到这里"还是"完成全部挑战"）。
 */
async function reportQuizResult(block) {
  if (!currentSessionId.value) return;

  const questions = block.data?.questions || [];
  const completedQuestions = questions.filter((q) => q.completed);
  if (completedQuestions.length === 0) return;

  // 获取当前章节信息
  const ch = imChapters.value.find(
    (item) => item.chapter_id === block.chapter_id,
  );
  const chapterTitle = ch?.title || `第${block.chapter_id || 0}章`;

  // 构建答题结果
  const difficultyMap = { easy: "简单", medium: "中等", hard: "困难" };
  const results = completedQuestions.map((q) => ({
    question: q.question || q.stem || "",
    user_answer:
      q.optionLabels?.[q.userAnswer] ||
      String.fromCharCode(65 + (q.userAnswer || 0)),
    correct_answer:
      q.optionLabels?.[q.correctIndex] ||
      String.fromCharCode(65 + (q.correctIndex || 0)),
    correct: q.judgeResult === true,
    difficulty: difficultyMap[q.difficulty] || "中等",
  }));

  try {
    await api.postRaw(`/api/immersive/quiz-result`, {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: currentSessionId.value,
        chapter_id: block.chapter_id || 0,
        chapter_title: chapterTitle,
        results,
      }),
    });
  } catch (e) {
    // 上报失败不影响用户体验，静默处理
    console.warn("习题结果上报失败:", e);
  }
}

// ── PDF Block 内嵌渲染（canvas + 翻页栏 + 缩略图，参考 ChatView 成功实现）──
// state: { currentPage, totalPages }（不存 doc，避免响应式追踪 PDF 内部对象）
const pdfBlockStates = ref({}); // { [blockId]: { currentPage, totalPages, path } }
const pdfDocMap = new Map(); // blockId -> pdfDoc（普通 Map，不响应式）
const pdfMainCanvasRefs = {}; // blockId -> 主视图 canvas 元素
const pdfThumbCanvasRefs = {}; // blockId -> { [pageNum]: canvas }
const pdfMainRenderTasks = {}; // blockId -> 当前主视图 RenderTask（用于 cancel 旧任务）
const pdfThumbRenderTasks = {}; // blockId -> { [pageNum]: RenderTask }

function setPdfMainCanvasRef(blockId, el) {
  if (el) {
    pdfMainCanvasRefs[blockId] = el;
    // 如果 doc 已加载（组件重建场景），重新渲染当前页
    nextTick(() => {
      const state = pdfBlockStates.value[blockId];
      if (state && pdfDocMap.has(blockId)) {
        renderPdfMainPage(blockId, state.currentPage || 1);
      }
    });
  } else {
    delete pdfMainCanvasRefs[blockId];
  }
}

function setPdfThumbRef(blockId, pageNum, el) {
  if (!pdfThumbCanvasRefs[blockId]) pdfThumbCanvasRefs[blockId] = {};
  if (el) {
    pdfThumbCanvasRefs[blockId][pageNum] = el;
    nextTick(() => {
      if (pdfDocMap.has(blockId)) {
        renderPdfThumb(blockId, pageNum);
      }
    });
  } else {
    delete pdfThumbCanvasRefs[blockId][pageNum];
  }
}

async function initPdfBlock(blockId) {
  // 已加载过则跳过（doc 在普通 Map 里）
  if (pdfDocMap.has(blockId)) {
    const state = pdfBlockStates.value[blockId];
    if (state && pdfMainCanvasRefs[blockId]) {
      await nextTick();
      await renderPdfMainPage(blockId, state.currentPage || 1);
    }
    return;
  }
  const existingState = pdfBlockStates.value[blockId];
  if (existingState?.loading || existingState?.error) return;

  const block = canvasBlocks.value.find((b) => b.id === blockId);
  if (!block) return;
  const docId = block?.data?.doc_id;
  if (!docId) return;
  try {
    pdfBlockStates.value[blockId] = {
      ...(pdfBlockStates.value[blockId] || {}),
      loading: true,
      error: "",
      docId,
    };
    const pdfUrl = docRawUrl(docId);
    console.log("[PDF] 开始加载:", pdfUrl);
    const headRes = await fetch(pdfUrl, {
      method: "HEAD",
      headers: authHeaders(),
    });
    const contentType = headRes.headers.get("content-type") || "";
    if (!headRes.ok) {
      throw new Error(`PDF 文件不可用（HTTP ${headRes.status}）`);
    }
    if (!contentType.toLowerCase().includes("application/pdf")) {
      throw new Error(`响应不是 PDF 文件（${contentType || "未知类型"}）`);
    }

    const doc = await pdfjsLib.getDocument({
      url: pdfUrl,
      httpHeaders: authHeaders(),
      cMapUrl: "https://unpkg.com/pdfjs-dist@5.6.205/cmaps/",
      cMapPacked: true,
    }).promise;
    console.log("[PDF] 加载成功，页数:", doc.numPages);
    pdfDocMap.set(blockId, doc);
    pdfBlockStates.value[blockId] = {
      currentPage: 1,
      totalPages: doc.numPages,
      loading: false,
      error: "",
      docId,
    };
    await nextTick();
    await renderPdfMainPage(blockId, 1);
    // 异步渲染缩略图
    for (let i = 1; i <= doc.numPages; i++) {
      renderPdfThumb(blockId, i);
    }
  } catch (e) {
    console.warn("[PDF] 加载失败:", e);
    const message = e?.message || "未知错误";
    pdfBlockStates.value[blockId] = {
      ...(pdfBlockStates.value[blockId] || {}),
      loading: false,
      totalPages: 0,
      error: `PDF 加载失败：${message}`,
      docId,
    };
    imAddLog(`PDF 加载失败: ${message}`, "error");
  }
}

async function renderPdfMainPage(blockId, pageNum) {
  const doc = pdfDocMap.get(blockId);
  let canvas = pdfMainCanvasRefs[blockId];
  if (!canvas) {
    await nextTick();
    canvas = pdfMainCanvasRefs[blockId];
  }
  if (!canvas || !doc) {
    console.warn("[PDF] renderMain 跳过 canvas=", canvas, "doc=", doc);
    return;
  }
  try {
    const page = await doc.getPage(pageNum);
    const container = canvas.parentElement;
    const containerW = (container?.clientWidth || 800) - 16;
    const containerH = (container?.clientHeight || 560) - 16;
    const dpr = window.devicePixelRatio || 1;
    // 使用页面自带的 rotation（page.rotate），让 pdfjs 自动平衡 PDF 元数据中的 /Rotate，
    // 避免强制 0 导致已被旋转过的页面出现倒置/镜像。
    const rotation = page.rotate || 0;
    const baseVp = page.getViewport({ scale: 1, rotation });
    const scaleW = containerW / baseVp.width;
    const scaleH = containerH / baseVp.height;
    const scale = Math.max(0.5, Math.min(scaleW, scaleH));
    // dpr 直接并入 viewport scale，不在 ctx 上额外 ctx.scale(dpr,dpr)，
    // 避免 transform 叠加导致部分 PDF 渲染错位/空白。
    const scaledVp = page.getViewport({ scale: scale * dpr, rotation });

    canvas.width = Math.round(scaledVp.width);
    canvas.height = Math.round(scaledVp.height);
    canvas.style.width = `${scaledVp.width / dpr}px`;
    canvas.style.height = `${scaledVp.height / dpr}px`;

    const ctx = canvas.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 取消上一个尚未完成的 render，避免并发渲染同一个 canvas 造成旋转/错位。
    const prevTask = pdfMainRenderTasks[blockId];
    if (prevTask) {
      try {
        prevTask.cancel();
      } catch {
        /* ignore cancel error */
      }
    }
    const renderTask = page.render({
      canvasContext: ctx,
      viewport: scaledVp,
    });
    pdfMainRenderTasks[blockId] = renderTask;
    try {
      await renderTask.promise;
    } catch (err) {
      // 被 cancel() 时会抛 RenderingCancelledException，忽略即可。
      if (err && err.name !== "RenderingCancelledException") throw err;
      return;
    } finally {
      if (pdfMainRenderTasks[blockId] === renderTask) {
        delete pdfMainRenderTasks[blockId];
      }
    }

    const state = pdfBlockStates.value[blockId];
    if (state) state.currentPage = pageNum;
    console.log(
      "[PDF] 主视图渲染完成 block=",
      blockId,
      "page=",
      pageNum,
      "rotation=",
      rotation,
      "size=",
      canvas.width,
      "x",
      canvas.height,
    );
  } catch (e) {
    console.error("[PDF] 主视图渲染失败:", e);
  }
}

async function renderPdfThumb(blockId, pageNum) {
  const doc = pdfDocMap.get(blockId);
  const canvas = pdfThumbCanvasRefs[blockId]?.[pageNum];
  if (!canvas || !doc) return;
  try {
    const page = await doc.getPage(pageNum);
    const dpr = window.devicePixelRatio || 1;
    const rotation = page.rotate || 0;
    const baseVp = page.getViewport({ scale: 1, rotation });
    const targetW = 110;
    const scale = targetW / baseVp.width;
    // dpr 并入 scale，不在 ctx 上额外 scale(dpr,dpr)，避免部分缩略图表现为空白。
    const scaledVp = page.getViewport({ scale: scale * dpr, rotation });

    canvas.width = Math.round(scaledVp.width);
    canvas.height = Math.round(scaledVp.height);
    canvas.style.width = `${scaledVp.width / dpr}px`;
    canvas.style.height = `${scaledVp.height / dpr}px`;

    const ctx = canvas.getContext("2d");
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    // 缩略图也加 cancel 锁，避免列表项 v-for 重挂导致并发 render。
    if (!pdfThumbRenderTasks[blockId]) pdfThumbRenderTasks[blockId] = {};
    const prevTask = pdfThumbRenderTasks[blockId][pageNum];
    if (prevTask) {
      try {
        prevTask.cancel();
      } catch {
        /* ignore cancel error */
      }
    }
    const renderTask = page.render({
      canvasContext: ctx,
      viewport: scaledVp,
    });
    pdfThumbRenderTasks[blockId][pageNum] = renderTask;
    try {
      await renderTask.promise;
    } catch (err) {
      if (err && err.name !== "RenderingCancelledException") throw err;
      return;
    } finally {
      if (pdfThumbRenderTasks[blockId][pageNum] === renderTask) {
        delete pdfThumbRenderTasks[blockId][pageNum];
      }
    }
  } catch (e) {
    console.warn("[PDF] 缩略图渲染失败:", pageNum, e);
  }
}

async function pdfBlockGotoPage(blockId, pageNum) {
  const state = pdfBlockStates.value[blockId];
  if (!state || pageNum < 1 || pageNum > state.totalPages) return;
  await renderPdfMainPage(blockId, pageNum);
}

async function openPdfBlock(block) {
  const docId = block?.data?.doc_id;
  if (!docId) return;
  try {
    const blobUrl = await fetchAsBlobUrl(`/api/documents/${docId}/raw`);
    window.open(blobUrl, "_blank", "noopener,noreferrer");
  } catch (e) {
    imAddLog(`PDF 打开失败: ${e.message}`, "error");
  }
}

function applyWorkspacePayload(payload = {}) {
  const workspacePayload = payload.workspace ? payload : { workspace: payload };
  workspaceStage.value = workspacePayload.stage || workspaceStage.value;
  workspaceNextActions.value =
    workspacePayload.next_actions || workspaceNextActions.value;
  currentBlockId.value =
    workspacePayload.current_block_id || currentBlockId.value;
  if (Array.isArray(payload.canvas_blocks)) {
    // 不直接清空再重建（会导致 canvas 元素卸载/重挂，PDF 渲染需要重做）。
    // 改为：按 id 增量更新 + 移除多余项，保留已加载的 pdf doc 与 canvas 引用。
    const incomingIds = new Set(
      payload.canvas_blocks.map((b) => b && b.id).filter(Boolean),
    );
    canvasBlocks.value = canvasBlocks.value.filter((b) =>
      incomingIds.has(b.id),
    );
    payload.canvas_blocks.forEach(upsertCanvasBlock);
    // ✅ 兜底：只对"当前选中章节对应的 PDF block"立即加载——
    // 全量并发加载会一下子拉 6 个 2-3MB PDF，pdf.js 同时处理多份会非常卡。
    // 其他章节的 PDF 等用户切到那一章时由 :ref 钩子按需触发。
    nextTick(() => {
      const curCh = imChapters.value[imCurrentChapterIndex.value];
      const curPdfId = curCh ? `pdf_ch${curCh.chapter_id}` : null;
      canvasBlocks.value.forEach((b) => {
        if (
          b.type === "pdf" &&
          !pdfDocMap.has(b.id) &&
          (!curPdfId || b.id === curPdfId)
        ) {
          initPdfBlock(b.id);
        }
      });
    });
  }
  const workspace = workspacePayload.workspace || {};
  if (workspace.topic) currentTopic.value = workspace.topic;
  if (typeof workspace.enable_audio === "boolean") {
    enableAudio.value = workspace.enable_audio;
  }
  if (typeof workspace.enable_exercises === "boolean") {
    enableExercises.value = workspace.enable_exercises;
  }
  if (Array.isArray(workspace.chapters) && workspace.chapters.length > 0) {
    imChapters.value = workspace.chapters
      .filter((ch) => {
        // 严格验证产物完整性：根据课程配置判断该章节是否真正完成
        // 1. 后端标记为 ready 的章节，信任后端的判断
        if (ch.status === "ready") return true;
        // 2. 兼容：没有 status 但产物齐全的也算完成
        const hasPdf = (ch.files || []).some((f) => /\.pdf$/i.test(f));
        if (!hasPdf) return false;
        // 如果开启了习题，必须有习题文件
        if (enableExercises.value) {
          const hasExercises = (ch.files || []).some((f) =>
            /exercises\.md$/i.test(f),
          );
          if (!hasExercises) return false;
        }
        // 如果开启了语音，必须有音频文件
        if (enableAudio.value) {
          const hasAudio =
            Array.isArray(ch.audio_files) && ch.audio_files.length > 0;
          if (!hasAudio) return false;
        }
        return true;
      })
      .map((ch) => {
        const pdfPath = (ch.files || []).find((f) => /\.pdf$/i.test(f)) || "";
        const exPath =
          (ch.files || []).find((f) => /exercises\.md$/i.test(f)) || "";
        return {
          chapter_id: ch.chapter_id,
          title: ch.title,
          pdf_exists: !!pdfPath || !!ch.pdf_doc_id,
          pdf_path: pdfPath,
          pdf_doc_id: ch.pdf_doc_id || "",
          exercises_exists: !!exPath || !!ch.exercises_doc_id,
          exercises_path: exPath,
          exercises_doc_id: ch.exercises_doc_id || "",
          audio_enabled: !!ch.audio_enabled,
          audio_files: Array.isArray(ch.audio_files) ? ch.audio_files : [],
          audio_doc_id: ch.audio_doc_id || "",
          notes_doc_id: ch.notes_doc_id || "",
          speaker_notes_count: ch.speaker_notes_count || 0,
        };
      });
  }
}

function handleWorkspaceUpdate(data) {
  if (data.session_id) {
    currentSessionId.value = data.session_id;
    if (!sessionStartTime) sessionStartTime = Date.now();
  }
  if (data.workspace) applyWorkspacePayload(data.workspace);
  if (data.next_actions) workspaceNextActions.value = data.next_actions;
  if (data.block) upsertCanvasBlock(data.block);
  const title = data.block?.title || data.event || "workspace";
  imAddLog(`📌 工作区更新：${title}`, "success");
}

// ── 启动生成 ─────────────────────────────────────────────────────
function startImmersive() {
  if (!topicInput.value.trim()) return;
  currentTopic.value = topicInput.value.trim();
  phase.value = "immersive";
  imStartGenerate();
}

async function imStartGenerate() {
  imGenerating.value = true;
  imCompleted.value = false;
  imProgress.value = 0;
  imCurrentStage.value = "init";
  imStatusMessage.value = "正在初始化...";
  imAddLog(`🚀 开始生成课件：${currentTopic.value}`);
  try {
    const res = await api.postRaw(`/api/immersive/generate`, {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        topic: currentTopic.value,
        enable_audio: enableAudio.value,
        enable_exercises: enableExercises.value,
      }),
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
        } catch (e) {
          console.error("SSE 解析失败：", e);
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

// ── 断点续传：从未完成的章节继续生成 ─────────────────────────
async function imResumeGenerate() {
  if (!currentSessionId.value) {
    imAddLog("❌ 无 session_id，无法续传", "error");
    return;
  }
  imResumePrompt.value = false;
  imGenerating.value = true;
  imCompleted.value = false;
  imProgress.value = 5;
  imCurrentStage.value = "init";
  imStatusMessage.value = "正在恢复生成...";
  imAddLog(`🔄 断点续传：从未完成的章节继续生成`, "success");
  try {
    const res = await api.postRaw(`/api/immersive/resume`, {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: currentSessionId.value }),
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
        } catch (e) {
          console.error("SSE 解析失败：", e);
        }
      }
    }
  } catch (e) {
    imAddLog(`❌ 续传失败: ${e.message}`, "error");
  } finally {
    imGenerating.value = false;
    imGeneratingChapterTitle.value = "";
    imGeneratingChapterId.value = 0;
  }
}

function imHandleSSE(data) {
  const agentType = data.agent_type || "unknown";
  const eventType = data.event_type || "unknown";
  const step = data.step || 0;
  let content =
    data.content && data.content.length
      ? data.content.length > 15
        ? data.content.substring(0, 15) + "..."
        : data.content
      : "";
  switch (data.type) {
    case "progress":
      imProgress.value = data.pct || 0;
      imStatusMessage.value = data.message || "";
      if (data.stage) imCurrentStage.value = data.stage;
      imAddLog(data.message);
      break;
    case "outline":
      imOutline.value = data.data;
      imTab.value = "agent";
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
      if (!imChapters.value.some((c) => c.chapter_id === ch.chapter_id))
        imChapters.value.push(ch);
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
      if (data.session_id) {
        currentSessionId.value = data.session_id;
        sessionStartTime = Date.now();
      }
      imAddLog(`🎉 全部完成！共 ${imChapters.value.length} 章`, "success");
      break;
    case "error":
      imAddLog(`❌ ${data.message}`, "error");
      break;
    case "workspace_update":
      handleWorkspaceUpdate(data);
      break;
    case "agent_event": {
      let logMessage, logLevel;
      switch (eventType) {
        case "start":
          logMessage = `🤖 ${agentType} 开始执行: ${content}`;
          logLevel = "info";
          break;
        case "think":
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
    }
    default:
      imAddLog(`🔍 收到未知事件: ${data.type}`, "info");
      break;
  }
}

// ── PDF 渲染 ─────────────────────────────────────────────────────
async function imSelectChapter(idx) {
  imCurrentChapterIndex.value = idx;
  imCurrentPage.value = 1;
  imQuizCurrent.value = 0;
  imQuizSubmitted.value = false;
  imQuizAdvice.value = "";
  const ch = imChapters.value[idx];
  if (!ch?.pdf_doc_id) return;
  if (ch.exercises_doc_id) {
    try {
      const exRes = await api.getRaw(
        `/api/documents/${ch.exercises_doc_id}/raw`,
      );
      const md = await exRes.text();
      imExercisesHtml.value = renderMd(md);
      imParsedQuizzes.value = parseExercises(md);
    } catch {
      imExercisesHtml.value = "";
      imParsedQuizzes.value = [];
    }
  } else {
    imExercisesHtml.value = "";
    imParsedQuizzes.value = [];
  }
  const pdfUrl = docRawUrl(ch.pdf_doc_id);
  if (!imPdfDocMap.has(pdfUrl)) {
    try {
      const headRes = await fetch(pdfUrl, {
        method: "HEAD",
        headers: authHeaders(),
      });
      const contentType = headRes.headers.get("content-type") || "";
      if (!headRes.ok) {
        throw new Error(`PDF 文件不可用（HTTP ${headRes.status}）`);
      }
      if (!contentType.toLowerCase().includes("application/pdf")) {
        throw new Error(`响应不是 PDF 文件（${contentType || "未知类型"}）`);
      }

      const doc = await pdfjsLib.getDocument({
        url: pdfUrl,
        httpHeaders: authHeaders(),
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
  // 使用页面自身 rotation，让 pdfjs 自动平衡 PDF 元数据中的 /Rotate，
  // 避免强制 0 导致已被旋转过的页面表现为颠倒/镜像。
  const rotation = page.rotate || 0;
  const baseVp = page.getViewport({ scale: 1, rotation });
  const containerW = (container?.clientWidth || 800) - 48;
  const containerH = (container?.clientHeight || 500) - 48;
  const fitScale = Math.min(
    containerW / baseVp.width,
    containerH / baseVp.height,
  );
  // dpr 并入 scale，不在 ctx 上额外 scale(dpr,dpr)，避免 transform 叠加
  const scaledVp = page.getViewport({ scale: fitScale * dpr, rotation });
  canvas.width = Math.round(scaledVp.width);
  canvas.height = Math.round(scaledVp.height);
  canvas.style.width = `${scaledVp.width / dpr}px`;
  canvas.style.height = `${scaledVp.height / dpr}px`;
  const ctx = canvas.getContext("2d");
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  // 章节预览 PDF：取消上一个尚未完成的 render 任务，避免并发渲染造成旋转错位。
  const prevTask = imPdfRenderTasks.get(canvas);
  if (prevTask) {
    try {
      prevTask.cancel();
    } catch {
      /* ignore cancel error */
    }
  }
  const renderTask = page.render({ canvasContext: ctx, viewport: scaledVp });
  imPdfRenderTasks.set(canvas, renderTask);
  try {
    await renderTask.promise;
  } catch (err) {
    if (err && err.name !== "RenderingCancelledException") throw err;
    return;
  } finally {
    if (imPdfRenderTasks.get(canvas) === renderTask) {
      imPdfRenderTasks.delete(canvas);
    }
  }
  imCurrentPage.value = pageNum;
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
async function imGotoPage(num) {
  const ch = imChapters.value[imCurrentChapterIndex.value];
  if (!ch?.pdf_doc_id) return;
  const pdfUrl = docRawUrl(ch.pdf_doc_id);
  let doc = imPdfDocMap.get(pdfUrl);
  if (!doc) {
    try {
      doc = await pdfjsLib.getDocument({
        url: pdfUrl,
        httpHeaders: authHeaders(),
        cMapUrl: "https://unpkg.com/pdfjs-dist@5.6.205/cmaps/",
        cMapPacked: true,
      }).promise;
      imPdfDocMap.set(pdfUrl, doc);
    } catch (e) {
      imAddLog(`PDF 加载失败: ${e.message}`, "error");
      return;
    }
  }
  await imRenderPage(doc, num);
}

// ── 音频播放 ─────────────────────────────────────────────────────
function imPlayAudio(audioUrl = "") {
  const targetUrl = audioUrl || imCurrentAudioUrl.value;
  if (!targetUrl) return;
  if (imIsPlaying.value && imCurrentAudio) {
    imCurrentAudio.pause();
    imIsPlaying.value = false;
    return;
  }
  if (imCurrentAudio) imCurrentAudio.pause();
  const audioPath = targetUrl.replace(BASE_URL, "");
  fetchAsBlobUrl(audioPath)
    .then((blobUrl) => {
      imCurrentAudio = new Audio(blobUrl);
      imCurrentAudio.play().catch((e) => {
        imAddLog(`音频播放失败: ${e.message}`, "error");
        imIsPlaying.value = false;
      });
      imIsPlaying.value = true;
      const cleanup = () => {
        imIsPlaying.value = false;
        URL.revokeObjectURL(blobUrl);
      };
      imCurrentAudio.onended = cleanup;
      imCurrentAudio.onerror = cleanup;
    })
    .catch((e) => {
      imAddLog(`音频加载失败: ${e.message}`, "error");
      imIsPlaying.value = false;
    });
}
watch(imCurrentPage, () => {
  if (imCurrentAudio) {
    imCurrentAudio.pause();
    imCurrentAudio = null;
  }
  imIsPlaying.value = false;
});

// ── 智流 Agent 对话 ─────────────────────────────────────────────
async function sendImAgentMsg(text) {
  if (!text || !text.trim() || imAgentGenerating.value) return;
  imAgentGenerating.value = true;
  imAgentMessages.value.push({ role: "user", content: text, time: now() });
  imAgentInput.value = "";
  await nextTick();
  if (imAgentMsgRef.value)
    imAgentMsgRef.value.scrollTop = imAgentMsgRef.value.scrollHeight;
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
  const ch = imCurrentChapter.value;
  const contextInfo = ch
    ? `当前正在学习「${currentTopic.value}」第${ch.chapter_id}章「${ch.title}」`
    : `当前正在学习「${currentTopic.value}」`;
  try {
    if (currentSessionId.value) {
      const agentText = `[智流Agent] ${contextInfo}\n\n用户问题：${text}`;
      const idx = imAgentMessages.value.length - 1;
      let fullContent = "";
      // 记录本轮生成的卡片占位 ID → canvasBlock ID 的映射
      const cardSlotMap = new Map();
      sessionApi.streamMessage(currentSessionId.value, agentText, {
        onToolCall: (id, tool, args) => {
          const parsedArgs =
            typeof args === "string" ? JSON.parse(args || "{}") : args || {};
          if (tool === "generate_html_card") {
            const cardTitle = parsedArgs.title || "知识卡片";
            const blockId = `card_${id}`;
            cardSlotMap.set(id, blockId);
            upsertCanvasBlock({
              id: blockId,
              type: "knowledge_card",
              title: cardTitle,
              status: "generating",
              data: { fileId: null },
            });
          }
          if (tool === "generate_interactive_viz") {
            const cardTitle = parsedArgs.title || "交互可视化";
            const blockId = `viz_${id}`;
            cardSlotMap.set(id, blockId);
            upsertCanvasBlock({
              id: blockId,
              type: "viz_card",
              title: cardTitle,
              status: "generating",
              data: { vizId: null },
            });
          }
          if (tool === "create_quiz") {
            const cardTitle = parsedArgs.question
              ? parsedArgs.question.slice(0, 20) + "…"
              : "练习题";
            const blockId = `quiz_${id}`;
            cardSlotMap.set(id, blockId);
            upsertCanvasBlock({
              id: blockId,
              type: "quiz_card",
              title: cardTitle,
              status: "generating",
              data: { quizId: null },
            });
          }
        },
        onToolResult: (id, tool, args, result) => {
          const blockId = cardSlotMap.get(id);
          if (!blockId) return;
          const cardArgs =
            typeof args === "string" ? JSON.parse(args || "{}") : args || {};
          if (tool === "generate_html_card") {
            try {
              const data =
                typeof result === "string" ? JSON.parse(result) : result;
              if (data?.file_id) {
                upsertCanvasBlock({
                  id: blockId,
                  type: "knowledge_card",
                  title: cardArgs.title || "知识卡片",
                  status: "ready",
                  data: { fileId: data.file_id },
                });
              }
            } catch {
              /* 解析失败，保持 loading */
            }
          }
          if (tool === "generate_interactive_viz") {
            try {
              const vizId = typeof result === "string" ? result.trim() : "";
              if (vizId && !vizId.startsWith("Error")) {
                upsertCanvasBlock({
                  id: blockId,
                  type: "viz_card",
                  title: cardArgs.title || "交互可视化",
                  status: "ready",
                  data: { vizId },
                });
              }
            } catch {
              /* 解析失败 */
            }
          }
          if (tool === "create_quiz") {
            try {
              const data =
                typeof result === "string" ? JSON.parse(result) : result;
              if (data?.quiz_id) {
                upsertCanvasBlock({
                  id: blockId,
                  type: "quiz_card",
                  title: cardArgs.question
                    ? cardArgs.question.slice(0, 20) + "…"
                    : "练习题",
                  status: "ready",
                  data: { quizId: data.quiz_id },
                });
                // 加入答题批次，等待用户作答后自动反馈给 Agent
                imPendingQuizBatch.value.set(data.quiz_id, {
                  question: cardArgs.question || "练习题",
                  options: cardArgs.options || [],
                  answered: false,
                  result: null,
                });
              }
            } catch {
              /* 解析失败 */
            }
          }
        },
        onTextReply: (t) => {
          fullContent += t;
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

// ── QuizCard 答题反馈机制 ─────────────────────────────────────────
// 收集 Agent 生成的 quiz 卡片，答完后自动发消息给 Agent
const imPendingQuizBatch = ref(new Map());

function onImQuizAnswered(result) {
  const { quizId } = result;

  // 标记该题已答
  if (quizId && imPendingQuizBatch.value.has(quizId)) {
    imPendingQuizBatch.value.set(quizId, {
      ...imPendingQuizBatch.value.get(quizId),
      answered: true,
      result,
    });
  }

  // 检查批次中是否还有未答的题
  const batch = [...imPendingQuizBatch.value.values()];
  const allAnswered = batch.length > 0 && batch.every((item) => item.answered);

  if (!allAnswered) return;

  // 全部答完，构造汇总消息
  const typeMap = {
    multiple_choice: "单选题",
    true_false: "判断题",
    fill_in: "填空题",
    open_ended: "简答题",
  };

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
    const item = batch[0];
    const r = item.result;
    const typeLabel = typeMap[r.quiz_type] || "题目";
    const answerText = formatAnswer(r);
    const resultText = r.is_correct
      ? "回答正确 ✓"
      : `回答错误 ✗（正确答案：${formatCorrectAnswer(r)}）`;
    const optionsText =
      r.quiz_type === "multiple_choice" && r.options?.length
        ? `\n选项：${r.options.join(" / ")}`
        : "";
    msg = `我完成了一道${typeLabel}：\n题目：${r.question}${optionsText}\n我的答案：${answerText}\n${resultText}`;
  } else {
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

  // 清空批次，发送汇总消息给 Agent
  imPendingQuizBatch.value.clear();
  sendImAgentMsg(msg);
}

// ── Markdown "问AI"功能（退化为简单 LLM 对话）─────────────────────
const imAskBubble = ref({ visible: false, x: 0, y: 0, text: "" });
const imAskPanel = ref({
  visible: false,
  selectedText: "",
  reply: "",
  loading: false,
  error: "",
});
const imAskPanelPos = ref({ x: 0, y: 0 });
const imAskPanelStyle = computed(() => ({
  left: imAskPanelPos.value.x + "px",
  top: imAskPanelPos.value.y + "px",
}));
const imAskBodyRef = ref(null);
let imAskAbortController = null;

function onMdMouseUp(event) {
  const sel = window.getSelection();
  const text = sel ? sel.toString().trim() : "";
  if (text.length < 2) {
    imAskBubble.value.visible = false;
    return;
  }
  // 计算气泡位置（相对于 .learning-canvas 容器，需要加上 scrollTop）
  const range = sel.getRangeAt(0);
  const rect = range.getBoundingClientRect();
  const canvas = event.currentTarget.closest(".learning-canvas");
  if (!canvas) return;
  const canvasRect = canvas.getBoundingClientRect();
  // 加上容器的 scrollTop，确保气泡在滚动后仍然定位在选中文本旁边
  const scrollTop = canvas.scrollTop;
  const bx = rect.left + rect.width / 2 - canvasRect.left;
  const by = rect.top - canvasRect.top + scrollTop - 36;
  imAskBubble.value = {
    visible: true,
    x: Math.max(4, Math.min(bx, canvasRect.width - 80)),
    y: Math.max(4, by),
    text,
  };
}

function openImAskPanel() {
  // 记录面板位置（基于气泡位置，面板显示在气泡下方偏右）
  imAskPanelPos.value = {
    x: Math.max(12, imAskBubble.value.x - 140),
    y: imAskBubble.value.y + 40,
  };
  imAskBubble.value.visible = false;
  imAskPanel.value = {
    visible: true,
    selectedText: imAskBubble.value.text,
    reply: "",
    loading: false,
    error: "",
  };
  nextTick(() => doImAsk());
}

function closeImAskPanel() {
  imAskPanel.value.visible = false;
  imAskAbortController?.abort();
  imAskAbortController = null;
}

async function doImAsk() {
  if (!imAskPanel.value.selectedText) return;
  imAskAbortController?.abort();
  imAskPanel.value.reply = "";
  imAskPanel.value.error = "";
  imAskPanel.value.loading = true;

  // 构造上下文信息
  const context = currentTopic.value
    ? `当前学习主题：${currentTopic.value}`
    : "";

  imAskAbortController = llmApi.quickAsk(
    {
      question: `请解释以下内容：\n\n"${imAskPanel.value.selectedText}"`,
      context,
    },
    {
      onTextChunk: (delta) => {
        imAskPanel.value.reply += delta;
        nextTick(() => {
          if (imAskBodyRef.value)
            imAskBodyRef.value.scrollTop = imAskBodyRef.value.scrollHeight;
        });
      },
      onDone: () => {
        imAskPanel.value.loading = false;
      },
      onError: (err) => {
        imAskPanel.value.loading = false;
        imAskPanel.value.error = err.message || "请求失败，请重试";
      },
    },
  );
}

// 点击空白处隐藏气泡
function onDocClickForAskBubble(e) {
  if (imAskBubble.value.visible) {
    const bubble = document.querySelector(".im-ask-ai-bubble");
    if (bubble && !bubble.contains(e.target)) {
      imAskBubble.value.visible = false;
    }
  }
}

// ── 习题解析 ─────────────────────────────────
function _detectDifficulty(text) {
  if (!text) return "";
  if (/简单|基础|入门|easy/i.test(text)) return "easy";
  if (/困难|难题|进阶|挑战|hard/i.test(text)) return "hard";
  if (/中等|中级|medium|普通/i.test(text)) return "medium";
  return "";
}

function parseExercises(mdText) {
  if (!mdText) return [];
  const quizzes = [];
  const lines = mdText.split("\n");
  let currentQ = null;
  let inOptions = false;
  let currentTitleLine = "";
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    // 匹配题目标题行：### 第1题 [简单] / ### 1. 选择题 / ### 习题1 / 1. xxx
    const titleMatch =
      line.match(/^#{1,4}\s*(?:题目|第|习题)?\s*(\d+)/i) ||
      line.match(/^(\d+)\.\s+/);
    if (titleMatch) {
      if (currentQ) {
        // 提取难度（从标题行）
        currentQ.difficulty =
          _detectDifficulty(currentTitleLine) ||
          currentQ.difficulty ||
          "medium";
        quizzes.push(currentQ);
      }
      currentTitleLine = line;
      currentQ = {
        question: "",
        type: "choice",
        options: [],
        optionLabels: [],
        correctIndex: -1,
        answer: "",
        explanation: "",
        sectionTitle: "",
        difficulty: "",
        userAnswer: null,
        userText: "",
        judgeResult: null,
        feedback: "",
        showExplanation: false,
        completed: false,
      };
      inOptions = false;
      continue;
    }
    if (!currentQ) continue;
    // 匹配选项行：A. xxx / A、xxx / A) xxx（可能前面有 - 或 *）
    const optMatch = line.match(/^\s*[-*]?\s*([A-D])[.、)）]\s*(.+)/);
    if (optMatch) {
      inOptions = true;
      const lab = optMatch[1];
      if (!currentQ.optionLabels.includes(lab)) {
        currentQ.optionLabels.push(lab);
        currentQ.options.push(optMatch[2].trim());
      }
      continue;
    }
    // 匹配答案行（兼容 **答案：** A）
    const ansMatch = line.match(
      /^\s*\*{0,2}\s*(?:答案|正确答案|参考答案)\s*\*{0,2}\s*[：:]\s*\*{0,2}\s*([A-D])/i,
    );
    if (ansMatch) {
      currentQ.answer = ansMatch[1].toUpperCase();
      const idx = currentQ.optionLabels.indexOf(currentQ.answer);
      if (idx >= 0) currentQ.correctIndex = idx;
      continue;
    }
    // 匹配解析行（兼容 **解析：**）
    const expMatch = line.match(
      /^\s*\*{0,2}\s*(?:解析|解释|说明|分析)\s*\*{0,2}\s*[：:]\s*(.+)/,
    );
    if (expMatch) {
      currentQ.explanation = expMatch[1].trim();
      continue;
    }
    // 题干行（去掉 **题干：** 前缀）
    if (!inOptions && line.trim()) {
      const cleaned = line.replace(
        /^\s*\*{0,2}\s*(?:题干|题目)\s*\*{0,2}\s*[：:]\s*/,
        "",
      );
      currentQ.question += (currentQ.question ? "\n" : "") + cleaned;
    }
  }
  if (currentQ) quizzes.push(currentQ);
  // 过滤掉没有选项的无效题目（确保全部是选择题）
  if (currentQ) {
    currentQ.difficulty =
      _detectDifficulty(currentTitleLine) || currentQ.difficulty || "medium";
  }
  return quizzes
    .filter((q) => q.options.length >= 2 && q.question.trim())
    .map((q) => ({ ...q, difficulty: q.difficulty || "medium" }));
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
function retryQuiz() {
  imQuizSubmitted.value = false;
  imQuizAdvice.value = "";
  imQuizCurrent.value = 0;
  for (const q of imParsedQuizzes.value) {
    q.userAnswer = null;
    q.userText = "";
    q.judgeResult = null;
    q.feedback = "";
  }
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
async function submitAllQuizzes() {
  if (!currentSessionId.value) return;
  imQuizJudging.value = true;
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
  const needAI = imParsedQuizzes.value.filter((q) => q.judgeResult === null);
  if (needAI.length > 0) {
    const questionsStr = needAI
      .map((q) => {
        const userAns =
          typeof q.userAnswer === "number"
            ? String.fromCharCode(65 + q.userAnswer)
            : q.userText || "未作答";
        return `【第${imParsedQuizzes.value.indexOf(q) + 1}题】\n题目：${q.question}\n参考答案：${q.answer || "（无）"}\n学生答案：${userAns}`;
      })
      .join("\n\n");
    const prompt = `请批量判断以下 ${needAI.length} 道题的答案是否正确。\n\n${questionsStr}\n\n请以 JSON 数组回复，每个元素格式：{"index": 题号, "correct": true/false, "feedback": "分析（50字内）"}\n只回复 JSON 数组。`;
    try {
      let fullContent = "";
      await new Promise((resolve) => {
        sessionApi.streamMessage(currentSessionId.value, prompt, {
          onTextReply: (t) => {
            fullContent += t;
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
      for (const q of needAI) {
        if (q.judgeResult === null) {
          q.judgeResult = false;
          q.feedback = "AI 判题失败，请重试。";
        }
      }
    }
  }
  const wrongQuizzes = imParsedQuizzes.value.filter(
    (q) => q.judgeResult === false,
  );
  if (wrongQuizzes.length > 0) {
    const wrongStr = wrongQuizzes
      .map((q) => {
        const userAns =
          typeof q.userAnswer === "number"
            ? String.fromCharCode(65 + q.userAnswer)
            : q.userText || "未作答";
        return `- 题目：${q.question.slice(0, 80)}\n  学生答案：${userAns}`;
      })
      .join("\n");
    try {
      let adviceContent = "";
      await new Promise((resolve) => {
        sessionApi.streamMessage(
          currentSessionId.value,
          `学生答错了以下题目：\n\n${wrongStr}\n\n请给出100-200字的综合学习建议。`,
          {
            onTextReply: (t) => {
              adviceContent += t;
            },
            onDone: () => resolve(),
            onError: () => resolve(),
          },
        );
      });
      imQuizAdvice.value = adviceContent;
    } catch {
      imQuizAdvice.value = "";
    }
  }
  imQuizJudging.value = false;
  imQuizSubmitted.value = true;
}

// ── 离开确认 ─────────────────────────────────────────────────────
const showLeaveConfirm = ref(false);
let pendingLeaveAction = null;
function handleBack() {
  if (imGenerating.value || imAgentGenerating.value) {
    pendingLeaveAction = "reset";
    showLeaveConfirm.value = true;
  } else {
    resetToIdle();
  }
}
function confirmLeave() {
  showLeaveConfirm.value = false;
  if (pendingLeaveAction === "reset") resetToIdle();
  else if (typeof pendingLeaveAction === "function") pendingLeaveAction();
  pendingLeaveAction = null;
}
onBeforeRouteLeave((to, from, next) => {
  if (imGenerating.value || imAgentGenerating.value) {
    pendingLeaveAction = next;
    showLeaveConfirm.value = true;
  } else {
    next();
  }
});

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
  phase.value = "idle";
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
  imTab.value = "agent";
  imLogs.value = [];
  imIsPlaying.value = false;
  imExercisesHtml.value = "";
  imGeneratingChapterId.value = 0;
  imGeneratingChapterTitle.value = "";
  canvasBlocks.value = [];
  workspaceStage.value = "";
  workspaceNextActions.value = [];
  currentBlockId.value = null;
  imPdfDocMap.clear();
  imAgentMessages.value = [];
  imAgentInput.value = "";
  topicInput.value = "";
  enableAudio.value = false;
}

// ── 恢复历史会话 ─────────────────────────────────────────────────
onMounted(async () => {
  const sessionId = route.query.session_id;
  const topic = route.query.topic;
  const shouldResume = route.query.resume === "1" || route.query.resume === 1;
  if (sessionId) {
    try {
      const detail = await sessionApi.getById(sessionId);
      currentSessionId.value = detail.id;
      sessionStartTime = Date.now();
      currentTopic.value =
        detail.topic || detail.title?.replace("[AI课程] ", "") || "历史课程";
      phase.value = "immersive";
      imCompleted.value =
        detail.status === "completed" || detail.stage === "completed";
      imGenerating.value = false;
      applyWorkspacePayload(detail);
      if (canvasBlocks.value.length > 0) {
        imAddLog(`已恢复 ${canvasBlocks.value.length} 个学习内容块`, "success");
      }
      try {
        // 从 canvas_blocks 里的 outline block 拿 doc_id 拉大纲
        const outlineBlock = canvasBlocks.value.find(
          (b) => b.type === "outline" && b?.data?.doc_id,
        );
        if (outlineBlock?.data?.doc_id) {
          const outlineRes = await api.getRaw(
            `/api/documents/${outlineBlock.data.doc_id}/raw`,
          );
          if (outlineRes.ok) {
            imOutline.value = await outlineRes.json();
            imAddLog(
              `大纲已加载，共 ${imOutline.value?.chapters?.length || 0} 章`,
            );
          }
        } else if (outlineBlock?.data?.outline) {
          // outline 原始数据已随 canvas_block 下发
          imOutline.value = outlineBlock.data.outline;
          imAddLog(
            `大纲已加载，共 ${imOutline.value?.chapters?.length || 0} 章`,
          );
        }
      } catch (ex) {
        console.error("加载大纲失败", ex);
      }
      if (detail.files && detail.files.length > 0) {
        // ── 恢复历史卡片（html_card / viz / quiz 类型文件）到 canvasBlocks ──
        for (const f of detail.files) {
          if (f.file_type === "html_card" && f.file_id) {
            upsertCanvasBlock({
              id: `card_${f.file_id}`,
              type: "knowledge_card",
              title: f.title || "知识卡片",
              status: "ready",
              data: { fileId: f.file_id },
            });
          }
          if (f.file_type === "viz" && f.file_id) {
            upsertCanvasBlock({
              id: `viz_${f.file_id}`,
              type: "viz_card",
              title: f.title || "交互可视化",
              status: "ready",
              data: { vizId: f.file_id },
            });
          }
          if (f.file_type === "quiz" && f.file_id) {
            upsertCanvasBlock({
              id: `quiz_${f.file_id}`,
              type: "quiz_card",
              title: f.title || "练习题",
              status: "ready",
              data: { quizId: f.file_id },
            });
          }
        }
        // ── 选中第一章 PDF（workspace.chapters 已装载到 imChapters）──
        if (imChapters.value.length > 0) {
          await nextTick();
          await nextTick();
          imSelectChapter(0);
        }
      }
      imAddLog(
        `已恢复课程「${currentTopic.value}」，共 ${imChapters.value.length} 章`,
      );
      imTab.value = "agent";
      if (detail.messages && detail.messages.length > 0) {
        const agentMsgs = [];
        for (let i = 0; i < detail.messages.length; i++) {
          const m = detail.messages[i];
          if (
            m.role === "user" &&
            m.content &&
            m.content.startsWith("[智流Agent]")
          ) {
            const match = m.content.match(/用户问题：(.+)$/s);
            const userText = match
              ? match[1].trim()
              : m.content.replace(/^\[智流Agent\].*?\n\n/, "");
            agentMsgs.push({
              role: "user",
              content: userText,
              time: m.created_at
                ? new Date(m.created_at).toLocaleTimeString("zh-CN", {
                    hour: "2-digit",
                    minute: "2-digit",
                  })
                : "",
            });
            if (
              i + 1 < detail.messages.length &&
              detail.messages[i + 1].role === "assistant"
            ) {
              const am = detail.messages[i + 1];
              agentMsgs.push({
                role: "assistant",
                thinking: false,
                content: am.content,
                html: renderMd(am.content),
                time: am.created_at
                  ? new Date(am.created_at).toLocaleTimeString("zh-CN", {
                      hour: "2-digit",
                      minute: "2-digit",
                    })
                  : "",
              });
              i++;
            }
          }
        }
        if (agentMsgs.length > 0) {
          imAgentMessages.value = agentMsgs;
          imAddLog(`已恢复 ${agentMsgs.length} 条智流 Agent 对话`);
        }
      }
    } catch (e) {
      console.warn("恢复会话失败:", e.message);
      if (topic) {
        topicInput.value = String(topic);
        nextTick(() => startImmersive());
      }
    }
    // 如果路由要求续传，且会话尚未完成 → 不再自动跳转，
    // 展示一个提示横幅，由用户手动点击“继续生成”。
    if (shouldResume && !imCompleted.value && currentSessionId.value) {
      imResumePrompt.value = true;
    }
  } else if (topic) {
    topicInput.value = String(topic);
    // 从 ChatView 跳转时读取语音开关参数
    const audioParam = route.query.enable_audio;
    if (audioParam === "1" || audioParam === 1) {
      enableAudio.value = true;
    }
    // 从 ChatView 跳转时读取习题开关参数
    const exercisesParam = route.query.enable_exercises;
    if (exercisesParam === "0" || exercisesParam === 0) {
      enableExercises.value = false;
    }
    nextTick(() => startImmersive());
  }
});

function onWindowResize() {
  const ch = imChapters.value[imCurrentChapterIndex.value];
  if (ch?.pdf_doc_id) {
    const pdfUrl = docRawUrl(ch.pdf_doc_id);
    const doc = imPdfDocMap.get(pdfUrl);
    if (doc) imRenderPage(doc, imCurrentPage.value);
  }
}
function handleBeforeUnload(e) {
  if (imGenerating.value || imAgentGenerating.value) {
    e.preventDefault();
    e.returnValue = "";
  }
}
onMounted(() => {
  window.addEventListener("resize", onWindowResize);
  window.addEventListener("beforeunload", handleBeforeUnload);
  document.addEventListener("mousedown", onDocClickForAskBubble);
});
onUnmounted(() => {
  window.removeEventListener("resize", onWindowResize);
  window.removeEventListener("beforeunload", handleBeforeUnload);
  document.removeEventListener("mousedown", onDocClickForAskBubble);
  imAskAbortController?.abort();
  if (currentSessionId.value && sessionStartTime) {
    const minutes = Math.max(
      1,
      Math.round((Date.now() - sessionStartTime) / 60000),
    );
    sessionApi.recordDuration(currentSessionId.value, minutes).catch(() => {});
  }
  if (imCurrentAudio) {
    imCurrentAudio.pause();
    imCurrentAudio = null;
  }
});
</script>

<style scoped>
/* ═══ 布局 ═══ */
.chat-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
  background: var(--bg-base);
  position: relative;
}
.learn-wrap {
  display: flex;
  width: 100%;
  height: 100%;
}
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
}
.st-topic-icon {
  font-size: 15px;
}
.st-topic-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.slide-stage {
  flex: 1;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px 32px;
  position: relative;
}
.learning-stage {
  flex-direction: column;
  align-items: stretch;
  justify-content: stretch;
  padding: 0;
}
.learning-canvas {
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 18px 22px 28px;
}
.canvas-block {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 18px;
  padding: 20px;
  box-shadow: var(--shadow-sm);
}
.cb-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.cb-kicker {
  font-size: 12px;
  color: var(--brand-light);
  margin-bottom: 4px;
}
.cb-title {
  margin: 0;
  font-size: 20px;
  color: var(--text-primary);
}
.cb-status {
  flex-shrink: 0;
  font-size: 12px;
  padding: 4px 9px;
  border-radius: 999px;
  color: var(--text-secondary);
  background: var(--bg-hover);
  border: 1px solid var(--border);
}
.cb-status.ready {
  color: var(--green);
  background: var(--green-dim);
  border-color: rgba(52, 211, 153, 0.22);
}
.cb-status.generating {
  color: var(--brand-light);
  background: var(--brand-dim);
  border-color: rgba(167, 139, 250, 0.26);
}
.cb-status.failed {
  color: var(--red);
  background: var(--red-dim);
  border-color: rgba(248, 113, 113, 0.26);
}
.plan-overview {
  color: var(--text-secondary);
  line-height: 1.8;
  margin: 0 0 14px;
}
.plan-chapter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 12px;
}
.plan-chapter-card {
  display: flex;
  gap: 12px;
  padding: 14px;
  border-radius: 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
}
.pcc-index {
  width: 30px;
  height: 30px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--brand-light);
  background: var(--brand-dim);
  font-weight: 700;
}
.pcc-title {
  font-size: 14px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 5px;
}
.pcc-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
}
.pcc-kps {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
  margin-top: 8px;
}
.pcc-kps span {
  font-size: 11px;
  color: var(--brand-light);
  background: var(--brand-dim);
  border-radius: 999px;
  padding: 2px 7px;
}
.learning-plan-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  margin-bottom: 14px;
  border-radius: 14px;
  background: var(--brand-dim);
  color: var(--text-secondary);
}
.lps-pill {
  flex-shrink: 0;
  font-size: 12px;
  color: var(--brand-light);
  border: 1px solid rgba(167, 139, 250, 0.3);
  border-radius: 999px;
  padding: 4px 8px;
}
.md-render {
  color: var(--text-primary);
  line-height: 1.85;
  font-size: 15px;
  word-break: break-word;
}
.md-render :deep(h1) {
  font-size: 1.6em;
  font-weight: 700;
  color: var(--text-primary);
  margin: 1.2em 0 0.6em;
  padding-bottom: 0.3em;
  border-bottom: 1px solid var(--border);
}
.md-render :deep(h2) {
  font-size: 1.35em;
  font-weight: 700;
  color: var(--text-primary);
  margin: 1em 0 0.5em;
  padding-bottom: 0.25em;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
}
.md-render :deep(h3) {
  font-size: 1.15em;
  font-weight: 600;
  color: var(--text-primary);
  margin: 0.9em 0 0.4em;
}
.md-render :deep(h4),
.md-render :deep(h5),
.md-render :deep(h6) {
  font-size: 1em;
  font-weight: 600;
  color: var(--text-secondary);
  margin: 0.8em 0 0.3em;
}
.md-render :deep(p) {
  margin: 0.6em 0;
}
.md-render :deep(ul),
.md-render :deep(ol) {
  padding-left: 1.5em;
  margin: 0.5em 0;
}
.md-render :deep(li) {
  margin: 0.3em 0;
}
.md-render :deep(li)::marker {
  color: var(--brand-light, #a78bfa);
}
.md-render :deep(blockquote) {
  margin: 0.8em 0;
  padding: 0.6em 1em;
  border-left: 3px solid var(--brand-light, #a78bfa);
  background: rgba(167, 139, 250, 0.06);
  border-radius: 0 8px 8px 0;
  color: var(--text-secondary);
}
.md-render :deep(code) {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 0.88em;
  padding: 0.15em 0.4em;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  color: #e2b3ff;
}
.md-render :deep(pre) {
  margin: 0.8em 0;
  padding: 14px 16px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.35);
  border: 1px solid var(--border);
  overflow-x: auto;
}
.md-render :deep(pre code) {
  padding: 0;
  background: none;
  color: var(--text-primary);
  font-size: 13px;
  line-height: 1.6;
}
.md-render :deep(table) {
  width: 100%;
  border-collapse: collapse;
  margin: 0.8em 0;
  font-size: 14px;
}
.md-render :deep(th) {
  background: rgba(255, 255, 255, 0.06);
  padding: 8px 12px;
  text-align: left;
  font-weight: 600;
  border-bottom: 2px solid var(--border);
  color: var(--text-primary);
}
.md-render :deep(td) {
  padding: 8px 12px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  color: var(--text-secondary);
}
.md-render :deep(tr:hover td) {
  background: rgba(255, 255, 255, 0.03);
}
.md-render :deep(a) {
  color: var(--brand-light, #a78bfa);
  text-decoration: underline;
  text-decoration-color: var(--brand-light, #a78bfa);
  text-decoration-thickness: 1px;
  text-underline-offset: 3px;
  border-bottom: none;
  transition:
    color 0.2s,
    text-decoration-color 0.2s;
}
.md-render :deep(a:hover) {
  color: #c4b5fd;
  text-decoration-color: #c4b5fd;
  text-decoration-thickness: 2px;
}
.md-render :deep(hr) {
  border: none;
  border-top: 1px solid var(--border);
  margin: 1.2em 0;
}
.md-render :deep(img) {
  max-width: 100%;
  border-radius: 8px;
  margin: 0.6em 0;
}
.md-render :deep(strong) {
  color: var(--text-primary);
  font-weight: 600;
}
.md-render :deep(em) {
  color: var(--text-secondary);
  font-style: italic;
}
.canvas-quiz {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.quiz-batch-note {
  color: var(--text-muted);
  font-size: 13px;
}
.canvas-question {
  padding: 16px;
  border-radius: 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
}
.cq-head {
  display: flex;
  justify-content: space-between;
  color: var(--text-muted);
  font-size: 12px;
  margin-bottom: 10px;
}
.cq-stem {
  color: var(--text-primary);
  line-height: 1.7;
  margin-bottom: 12px;
}
.cq-options {
  display: grid;
  gap: 8px;
}
.cq-option {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  text-align: left;
  border: 1px solid var(--border);
  background: var(--bg-card);
  color: var(--text-secondary);
  border-radius: 12px;
  padding: 10px 12px;
  cursor: pointer;
}
.cq-option.selected {
  border-color: var(--brand);
  color: var(--text-primary);
  background: var(--brand-dim);
}
.cq-option span:first-child {
  color: var(--brand-light);
  font-weight: 700;
}
.cq-actions {
  display: flex;
  gap: 8px;
  margin-top: 12px;
}
.cq-action {
  border: 1px solid var(--border);
  background: var(--bg-hover);
  color: var(--text-secondary);
  border-radius: 10px;
  padding: 8px 12px;
  cursor: pointer;
}
.cq-action.primary {
  color: white;
  background: var(--brand);
  border-color: var(--brand);
}
.cq-explanation {
  margin-top: 12px;
  padding: 12px;
  border-radius: 12px;
  background: rgba(52, 211, 153, 0.08);
  border: 1px solid rgba(52, 211, 153, 0.18);
  color: var(--text-secondary);
  line-height: 1.7;
}

/* ═══ 小测阶段化 UI ═══ */
.quiz-stage {
  margin-top: 16px;
  padding: 14px 16px 8px;
  border-radius: 14px;
  background: linear-gradient(
    180deg,
    rgba(255, 255, 255, 0.02),
    rgba(255, 255, 255, 0)
  );
  border: 1px solid var(--border);
  position: relative;
}
.quiz-stage-easy {
  border-left: 3px solid #22c55e;
}
.quiz-stage-medium {
  border-left: 3px solid #f59e0b;
}
.quiz-stage-hard {
  border-left: 3px solid #ef4444;
}

.quiz-stage-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.quiz-stage-tag {
  font-size: 13px;
  font-weight: 700;
  padding: 4px 10px;
  border-radius: 999px;
  letter-spacing: 0.3px;
}
.quiz-stage-tag.tag-easy {
  background: rgba(34, 197, 94, 0.14);
  color: #4ade80;
}
.quiz-stage-tag.tag-medium {
  background: rgba(245, 158, 11, 0.14);
  color: #fbbf24;
}
.quiz-stage-tag.tag-hard {
  background: rgba(239, 68, 68, 0.14);
  color: #f87171;
}
.quiz-stage-progress {
  font-size: 12px;
  color: var(--text-muted);
}
.quiz-challenge-btn {
  margin-left: auto;
  padding: 6px 14px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 999px;
  border: 1px solid rgba(239, 68, 68, 0.4);
  background: rgba(239, 68, 68, 0.08);
  color: #f87171;
  cursor: pointer;
  transition: all 0.2s;
}
.quiz-challenge-btn:hover {
  background: rgba(239, 68, 68, 0.16);
}
.quiz-challenge-btn.active {
  background: rgba(239, 68, 68, 0.18);
  color: #fecaca;
  border-color: #f87171;
}
.quiz-locked-mask {
  padding: 18px 14px;
  text-align: center;
  color: var(--text-muted);
  font-size: 13px;
  border-radius: 12px;
  background: rgba(0, 0, 0, 0.18);
  border: 1px dashed var(--border);
}

/* === 闯关式阶段进度条 === */
.quiz-stage-rail {
  display: flex;
  gap: 12px;
  margin: 12px 0 18px;
  padding: 12px 14px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid var(--border);
}
.quiz-rail-node {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.18);
  border: 1px solid transparent;
  transition: all 0.25s;
  opacity: 0.65;
}
.quiz-rail-node.active {
  border-color: var(--brand);
  background: rgba(124, 92, 255, 0.12);
  opacity: 1;
  box-shadow: 0 0 0 2px rgba(124, 92, 255, 0.18);
}
.quiz-rail-node.done {
  opacity: 1;
  background: rgba(34, 197, 94, 0.1);
  border-color: rgba(34, 197, 94, 0.35);
}
.rail-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  font-size: 12px;
  font-weight: 700;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.08);
  color: var(--text);
}
.quiz-rail-node.done .rail-dot {
  background: #22c55e;
  color: #022c0f;
}
.quiz-rail-node.active .rail-dot {
  background: var(--brand);
  color: #fff;
}
.rail-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
}
.rail-score {
  margin-left: auto;
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

/* === 阶段完成后的进入下一阶段卡片 === */
.quiz-stage-next {
  margin-top: 18px;
  padding: 18px 16px;
  border-radius: 12px;
  background: linear-gradient(
    135deg,
    rgba(124, 92, 255, 0.1),
    rgba(34, 197, 94, 0.06)
  );
  border: 1px solid rgba(124, 92, 255, 0.3);
  text-align: center;
}
.qsn-summary {
  font-size: 14px;
  margin-bottom: 12px;
  color: var(--text);
}
.qsn-summary strong {
  color: #4ade80;
  font-size: 17px;
}
.qsn-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
  flex-wrap: wrap;
}
.qsn-btn {
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 8px;
  border: 1px solid var(--border);
  background: rgba(0, 0, 0, 0.25);
  color: var(--text);
  cursor: pointer;
  transition: all 0.2s;
}
.qsn-btn:hover {
  background: rgba(255, 255, 255, 0.06);
}
.qsn-btn.primary {
  background: linear-gradient(135deg, #7c5cff, #5b8cff);
  border: none;
  color: #fff;
  box-shadow: 0 4px 14px rgba(124, 92, 255, 0.35);
}
.qsn-btn.primary:hover {
  transform: translateY(-1px);
}
.qsn-btn.ghost {
  background: transparent;
}

/* === 全部阶段完成后的总结 === */
.quiz-final {
  margin-top: 8px;
  padding: 28px 20px;
  border-radius: 16px;
  background: linear-gradient(
    135deg,
    rgba(255, 215, 0, 0.08),
    rgba(124, 92, 255, 0.06)
  );
  border: 1px solid rgba(255, 215, 0, 0.25);
  text-align: center;
}
.qf-trophy {
  font-size: 48px;
  margin-bottom: 8px;
}
.qf-title {
  font-size: 20px;
  font-weight: 700;
  color: var(--text);
  margin-bottom: 18px;
}
.qf-stats {
  display: flex;
  justify-content: center;
  gap: 18px;
  margin-bottom: 18px;
  flex-wrap: wrap;
}
.qf-stat {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 18px;
  border-radius: 10px;
  background: rgba(0, 0, 0, 0.22);
  min-width: 90px;
}
.qf-stat-label {
  font-size: 12px;
  color: var(--text-muted);
}
.qf-stat-value {
  font-size: 18px;
  font-weight: 700;
  color: #fbbf24;
  font-variant-numeric: tabular-nums;
}

.quiz-stage-body {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

/* 题目状态 */
.canvas-question.q-correct {
  border-color: rgba(34, 197, 94, 0.5);
  box-shadow: 0 0 0 1px rgba(34, 197, 94, 0.18) inset;
}
.canvas-question.q-wrong {
  border-color: rgba(239, 68, 68, 0.5);
  box-shadow: 0 0 0 1px rgba(239, 68, 68, 0.18) inset;
}
.cq-tag {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 999px;
}
.cq-tag.tag-easy {
  background: rgba(34, 197, 94, 0.12);
  color: #4ade80;
}
.cq-tag.tag-medium {
  background: rgba(245, 158, 11, 0.12);
  color: #fbbf24;
}
.cq-tag.tag-hard {
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
}

/* 选项状态（已提交后）*/
.cq-option.opt-correct {
  border-color: #22c55e;
  background: rgba(34, 197, 94, 0.12);
  color: var(--text-primary);
}
.cq-option.opt-correct span:first-child {
  color: #4ade80;
}
.cq-option.opt-wrong {
  border-color: #ef4444;
  background: rgba(239, 68, 68, 0.12);
  color: var(--text-primary);
}
.cq-option.opt-wrong span:first-child {
  color: #f87171;
}
.cq-option.disabled {
  cursor: not-allowed;
  opacity: 0.95;
}

/* 提交反馈条 */
.cq-feedback {
  margin-top: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  font-size: 13px;
  font-weight: 500;
  line-height: 1.6;
}
.cq-feedback.fb-correct {
  background: rgba(34, 197, 94, 0.12);
  color: #86efac;
  border: 1px solid rgba(34, 197, 94, 0.3);
}
.cq-feedback.fb-wrong {
  background: rgba(239, 68, 68, 0.1);
  color: #fca5a5;
  border: 1px solid rgba(239, 68, 68, 0.28);
}
.cq-feedback.fb-info {
  background: rgba(148, 163, 184, 0.1);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}
.cq-action.primary:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  background: rgba(148, 163, 184, 0.3);
  border-color: transparent;
}
.canvas-html-card {
  border-radius: 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  overflow: hidden;
  height: 520px;
}
.canvas-viz-card {
  border-radius: 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  overflow: hidden;
  height: 520px;
}
.canvas-quiz-card {
  border-radius: 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  overflow: hidden;
  padding: 16px;
}
.canvas-html-card .html-card-loading,
.canvas-viz-card .html-card-loading,
.canvas-quiz-card .html-card-loading {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 24px;
  color: var(--text-dim);
  font-size: 13px;
}
.canvas-pdf-embed {
  border-radius: 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  overflow: hidden;
}
.pdf-embed-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-card);
}
.pdf-embed-icon {
  font-size: 16px;
}
.pdf-embed-title {
  flex: 1;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.pdf-embed-fullscreen {
  background: none;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 6px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.15s;
}
.pdf-embed-fullscreen:hover {
  background: var(--bg-elev);
  color: var(--brand);
  border-color: var(--brand);
}
.pdf-embed-body {
  display: flex;
  background: #1a1a2e;
  width: 100%;
  height: 640px;
  box-sizing: border-box;
  position: relative;
}
.pdf-thumbs {
  flex: 0 0 140px;
  overflow-y: auto;
  padding: 12px 8px;
  background: rgba(0, 0, 0, 0.25);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pdf-thumbs::-webkit-scrollbar {
  width: 6px;
}
.pdf-thumbs::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.15);
  border-radius: 3px;
}
.pdf-thumb-item {
  cursor: pointer;
  border-radius: 6px;
  padding: 4px;
  border: 2px solid transparent;
  transition: all 0.15s;
  display: flex;
  flex-direction: column;
  align-items: center;
  background: rgba(255, 255, 255, 0.04);
}
.pdf-thumb-item:hover {
  background: rgba(255, 255, 255, 0.08);
}
.pdf-thumb-item.active {
  border-color: var(--brand);
  background: rgba(52, 211, 153, 0.1);
}
.pdf-thumb-canvas {
  display: block;
  max-width: 100%;
  height: auto;
  border-radius: 4px;
  background: #fff;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}
.pdf-thumb-label {
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-muted);
}
.pdf-main-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.pdf-main-canvas-wrap {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 8px;
  overflow: auto;
  position: relative;
}
.pdf-main-canvas {
  display: block;
  max-width: 100%;
  height: auto;
  border-radius: 6px;
  background: #fff;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
}
.pdf-main-toolbar {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 10px 14px;
  border-top: 1px solid var(--border);
  background: var(--bg-card);
}
.pdf-nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: none;
  border: 1px solid var(--border);
  color: var(--text-secondary);
  cursor: pointer;
  padding: 5px 12px;
  border-radius: 6px;
  font-size: 12px;
  transition: all 0.15s;
}
.pdf-nav-btn:hover:not(:disabled) {
  color: var(--brand);
  background: var(--bg-elev);
  border-color: var(--brand);
}
.pdf-nav-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}
.pdf-nav-btn.im-audio-btn {
  border-color: rgba(139, 92, 246, 0.45);
  color: #c4b5fd;
  background: rgba(139, 92, 246, 0.12);
}
.pdf-nav-btn.im-audio-btn.playing {
  color: #fff;
  border-color: #10b981;
  background: rgba(16, 185, 129, 0.25);
}
.pdf-nav-info {
  font-size: 13px;
  color: var(--text-primary);
  font-weight: 600;
  min-width: 60px;
  text-align: center;
}
.pdf-embed-loading {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 13px;
}
.pdf-embed-error {
  padding: 24px;
  color: #dc2626;
  text-align: center;
  line-height: 1.6;
}
.chapter-status-card {
  padding: 16px;
  border-radius: 14px;
  background: var(--bg-elev);
  border: 1px solid var(--border);
  color: var(--text-secondary);
}
.chapter-status-line {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
}
.chapter-status-sub {
  margin-top: 6px;
  font-size: 12px;
  color: var(--text-muted);
}
.canvas-fallback pre {
  white-space: pre-wrap;
  color: var(--text-muted);
}
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
.chat-panel {
  display: flex;
  flex-direction: column;
  background: var(--bg-panel);
  border-left: 1px solid var(--border);
  overflow: hidden;
  flex-shrink: 0;
}

/* ═══ 主题输入 ═══ */
.topic-entry {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px 24px;
  z-index: 10;
  background: var(--bg-base);
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
.te-container {
  position: relative;
  z-index: 2;
  width: 100%;
  max-width: 720px;
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
  font-size: 40px;
  font-weight: 800;
  line-height: 1.25;
  letter-spacing: -1px;
  margin: 0 0 18px;
  color: var(--text-primary);
}
.te-title-grad {
  background: linear-gradient(135deg, #8b5cf6, #a855f7);
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
.te-input-wrap {
  margin: 32px auto 24px;
  max-width: 560px;
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
}
.te-input-hint {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  padding: 5px 12px;
  border-radius: 999px;
  white-space: nowrap;
}
.te-input-hint.ok {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
}
.te-options {
  max-width: 560px;
  margin: -10px auto 20px;
  display: flex;
  gap: 10px;
}
.te-option-toggle {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid rgba(139, 92, 246, 0.2);
  border-radius: 12px;
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
  width: 16px;
  height: 16px;
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
.start-btn {
  all: unset;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 14px 32px;
  border-radius: 14px;
  background: linear-gradient(135deg, #8b5cf6, #a855f7);
  color: #fff;
  font-size: 16px;
  font-weight: 700;
  box-shadow: 0 8px 30px rgba(139, 92, 246, 0.4);
  transition: all 0.2s;
}
.start-btn:hover:not(:disabled) {
  transform: translateY(-2px);
  box-shadow: 0 12px 40px rgba(139, 92, 246, 0.5);
}
.start-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ═══ 续传提示横幅 ═══ */
.im-resume-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 12px 18px;
  margin: 8px 16px 0;
  background: linear-gradient(
    135deg,
    rgba(139, 92, 246, 0.18),
    rgba(59, 130, 246, 0.18)
  );
  border: 1px solid rgba(139, 92, 246, 0.45);
  border-radius: 10px;
  color: var(--text-primary, #e5e7ff);
  flex-shrink: 0;
}
.im-resume-info {
  flex: 1;
  min-width: 0;
}
.im-resume-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 4px;
}
.im-resume-desc {
  font-size: 13px;
  opacity: 0.85;
  line-height: 1.5;
}
.im-resume-desc strong {
  color: #c4b5fd;
  font-weight: 700;
}
.im-resume-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}
.im-resume-btn-ghost,
.im-resume-btn-primary {
  font-size: 13px;
  padding: 7px 14px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  border: 1px solid transparent;
}
.im-resume-btn-ghost {
  background: transparent;
  color: var(--text-secondary, #b0b0d0);
  border-color: var(--border, rgba(255, 255, 255, 0.15));
}
.im-resume-btn-ghost:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--text-primary, #e5e7ff);
}
.im-resume-btn-primary {
  background: linear-gradient(135deg, #8b5cf6, #6366f1);
  color: #fff;
  font-weight: 600;
  box-shadow: 0 4px 14px rgba(139, 92, 246, 0.35);
}
.im-resume-btn-primary:hover {
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(139, 92, 246, 0.5);
}

/* ═══ 进度条 ═══ */
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
  /* 占满整个 slide-stage 并垂直水平居中
     注：父级 .slide-stage.learning-stage 用了 align-items: stretch
     所以这里必须自撑满 + 主轴居中，而不能依赖父级 flex 居中 */
  flex: 1;
  align-self: stretch;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 40px 24px;
  text-align: center;
}
.im-gen-icon {
  font-size: 3rem;
  animation: pulse 1.5s ease infinite;
  margin-bottom: 4px;
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
.no-card-hint {
  flex: 1;
  align-self: stretch;
  width: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
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

/* ═══ PDF ═══ */
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

/* ═══ 分页导航 ═══ */
.canvas-page-nav {
  height: 52px;
  background: var(--bg-base);
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 0 12px;
}
.cpn-arrow {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: transparent;
  cursor: pointer;
  color: var(--text-secondary);
  transition: var(--transition);
  flex-shrink: 0;
}
.cpn-arrow:hover:not(:disabled) {
  background: var(--bg-hover);
  border-color: var(--border-active);
  color: var(--brand);
}
.cpn-arrow:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}
.cpn-pages {
  display: flex;
  align-items: center;
  gap: 4px;
  overflow-x: auto;
  flex: 1;
  padding: 4px 0;
}
.cpn-pages::-webkit-scrollbar {
  height: 3px;
}
.cpn-pages::-webkit-scrollbar-thumb {
  background: var(--border);
  border-radius: 2px;
}
.cpn-item {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition);
  white-space: nowrap;
  flex-shrink: 0;
  border: 1px solid transparent;
  font-size: 12px;
  color: var(--text-muted);
}
.cpn-item:hover {
  background: var(--bg-hover);
  color: var(--text-secondary);
}
.cpn-item.active {
  background: var(--brand-dim);
  border-color: var(--border-active);
  color: var(--brand-light);
  font-weight: 600;
}
.cpn-item.is-card {
  border-left: 2px solid var(--brand);
}
.cpn-icon {
  font-size: 13px;
}
.cpn-label {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* ═══ 知识卡片全屏页 ═══ */
.learning-canvas.is-card-page {
  padding: 0;
  gap: 0;
}
.learning-canvas.is-card-page .canvas-block {
  border: none;
  border-radius: 0;
  padding: 0;
  box-shadow: none;
  height: 100%;
  display: flex;
  flex-direction: column;
}
.learning-canvas.is-card-page .cb-head {
  padding: 12px 20px;
  flex-shrink: 0;
}
/* 知识卡片、quiz卡片、viz卡片在全屏页模式下隐藏头部（内容本身已有标题） */
.learning-canvas.is-card-page .cb-knowledge_card .cb-head,
.learning-canvas.is-card-page .cb-quiz_card .cb-head,
.learning-canvas.is-card-page .cb-viz_card .cb-head {
  display: none;
}
.learning-canvas.is-card-page .canvas-html-card {
  flex: 1;
  height: auto;
  min-height: 0;
  border-radius: 0;
  border: none;
  background: #f5f6fa;
}
.learning-canvas.is-card-page .canvas-viz-card {
  flex: 1;
  height: auto;
  min-height: 0;
  border-radius: 0;
  border: none;
}
.learning-canvas.is-card-page .canvas-quiz-card {
  flex: 1;
  height: auto;
  min-height: 0;
  border-radius: 0;
  border: none;
  padding: 24px;
  overflow-y: auto;
}
.gen-pulse {
  display: inline-block;
  border-radius: 50%;
  background: var(--brand);
  animation: pulse 1.2s ease infinite;
}

/* ═══ 右侧面板 ═══ */
.im-sidebar-inner {
  display: flex;
  flex-direction: column;
  height: 100%;
}
/* ═══ Agent Header ═══ */
.im-agent-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.im-agent-header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}
.im-agent-header-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}
.im-agent-header-status {
  font-size: 11px;
  color: var(--text-muted);
}
.im-agent-toggle-reasoning {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-muted);
  font-size: 11px;
  cursor: pointer;
  transition: var(--transition);
}
.im-agent-toggle-reasoning:hover,
.im-agent-toggle-reasoning.active {
  background: rgba(139, 92, 246, 0.1);
  border-color: var(--brand);
  color: var(--brand-light);
}
.reasoning-count {
  font-size: 9px;
  background: var(--brand);
  color: white;
  padding: 0 4px;
  border-radius: 8px;
  min-width: 16px;
  text-align: center;
}

/* ═══ 推理过程面板 ═══ */
.im-reasoning-panel {
  margin: 10px 0;
  border: 1px solid rgba(139, 92, 246, 0.2);
  border-radius: 10px;
  background: rgba(139, 92, 246, 0.04);
  overflow: hidden;
}
.im-reasoning-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px;
  font-size: 11px;
  font-weight: 600;
  color: var(--brand-light);
  border-bottom: 1px solid rgba(139, 92, 246, 0.15);
}
.im-reasoning-count {
  margin-left: auto;
  font-size: 10px;
  color: var(--text-muted);
  font-weight: 400;
}
.im-reasoning-list {
  max-height: 200px;
  overflow-y: auto;
  padding: 6px 12px;
}
.im-reasoning-item {
  display: flex;
  gap: 8px;
  padding: 4px 0;
  font-size: 11px;
  line-height: 1.5;
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
}
.im-reasoning-item:last-child {
  border-bottom: none;
}
.im-reasoning-time {
  color: var(--text-dim);
  font-size: 10px;
  flex-shrink: 0;
  font-family: monospace;
}
.im-reasoning-msg {
  color: var(--text-secondary);
  word-break: break-word;
}
.im-reasoning-item.success .im-reasoning-msg {
  color: var(--green);
}
.im-reasoning-item.error .im-reasoning-msg {
  color: var(--red);
}
.im-reasoning-empty {
  color: var(--text-dim);
  font-size: 11px;
  line-height: 1.6;
  text-align: center;
  padding: 14px 6px;
}

/* ═══ Agent 卡片（嵌入对话流） ═══ */
.im-agent-card {
  margin: 10px 0;
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 12px;
  background: var(--bg-card);
}
.im-agent-card-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 10px;
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
}
.im-agent-card-icon {
  font-size: 14px;
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
  display: flex;
  flex-direction: column;
}
.im-placeholder {
  color: var(--text-dim);
  font-size: 13px;
  text-align: center;
  padding: 40px 0;
}

/* slide-down transition */
.slide-down-enter-active,
.slide-down-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}
.slide-down-enter-from,
.slide-down-leave-to {
  opacity: 0;
  max-height: 0;
}
.slide-down-enter-to,
.slide-down-leave-from {
  opacity: 1;
  max-height: 300px;
}

/* ═══ 大纲 ═══ */
.im-outline-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin: 0 0 8px;
}
.im-outline-overview {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.7;
  margin-bottom: 16px;
}
.im-outline-chapter {
  padding: 10px 0;
  border-top: 1px solid var(--border);
}
.im-outline-ch-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 4px;
}
.im-outline-ch-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 6px;
}
.im-outline-kps {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.im-outline-kp {
  font-size: 10px;
  padding: 2px 7px;
  border-radius: 4px;
  background: var(--brand-dim);
  color: var(--brand-light);
  border: 1px solid rgba(99, 102, 241, 0.15);
}

/* ═══ 日志 ═══ */
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

/* ═══ 习题 ═══ */
.im-quiz-container {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.im-ex-content {
  font-size: 13px;
  line-height: 1.8;
  color: var(--text-primary);
}
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
.imq-nav-btn.submit {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  border: none;
  color: white;
  padding: 10px 22px;
  font-size: 13px;
  font-weight: 600;
  border-radius: var(--radius-md);
}
.imq-unanswered-hint {
  text-align: center;
  font-size: 11px;
  color: #f59e0b;
  margin-top: 8px;
}
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

/* ═══ Agent 对话 ═══ */
.im-agent-chat {
  display: flex;
  flex-direction: column;
  height: 100%;
  flex: 1;
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

/* ═══ 共用 ═══ */
.agent-avatar {
  border-radius: 50%;
  background: var(--gradient-brand);
  display: flex;
  align-items: center;
  justify-content: center;
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
@keyframes typing {
  0%,
  60%,
  100% {
    transform: translateY(0);
  }
  30% {
    transform: translateY(-4px);
  }
}
@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }
  50% {
    opacity: 0.5;
  }
}
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.3s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* ═══ 离开确认 ═══ */
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
  border-radius: 16px;
  padding: 32px 36px;
  max-width: 380px;
  width: 90%;
  text-align: center;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.25);
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
  color: #ef4444;
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
}
.btn-danger {
  background: #ef4444;
  color: #fff;
  border: 1px solid #ef4444;
}
.btn-danger:hover {
  background: #dc2626;
}
.btn-ghost {
  background: var(--bg-hover);
  color: var(--text-secondary);
  border: 1px solid var(--border);
}
.btn-ghost:hover {
  background: var(--bg-card);
  border-color: var(--border-active);
}
.msg-text {
  line-height: 1.7;
  font-size: 14px;
  word-break: break-word;
}
.msg-text p {
  margin: 0 0 8px;
}
.msg-text p:last-child {
  margin-bottom: 0;
}
.msg-text :deep(code) {
  font-family: "JetBrains Mono", "Fira Code", monospace;
  font-size: 0.88em;
  padding: 0.12em 0.35em;
  border-radius: 4px;
  background: rgba(255, 255, 255, 0.08);
  color: #e2b3ff;
}
.msg-text :deep(pre) {
  margin: 0.6em 0;
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(0, 0, 0, 0.3);
  border: 1px solid var(--border);
  overflow-x: auto;
}
.msg-text :deep(pre code) {
  padding: 0;
  background: none;
  color: var(--text-primary);
  font-size: 12.5px;
  line-height: 1.5;
}
.msg-text :deep(ul),
.msg-text :deep(ol) {
  padding-left: 1.4em;
  margin: 0.4em 0;
}
.msg-text :deep(li) {
  margin: 0.2em 0;
}
.msg-text :deep(blockquote) {
  margin: 0.5em 0;
  padding: 0.4em 0.8em;
  border-left: 3px solid var(--brand-light, #a78bfa);
  background: rgba(167, 139, 250, 0.06);
  border-radius: 0 6px 6px 0;
  color: var(--text-secondary);
}
.msg-text :deep(strong) {
  color: var(--text-primary);
  font-weight: 600;
}
.msg-text :deep(a) {
  color: var(--brand-light, #a78bfa);
  text-decoration: none;
}

/* ═══ Markdown "问AI" 气泡 & 浮窗 ═══ */
.md-render-askable {
  position: relative;
  cursor: text;
}

.learning-canvas {
  position: relative;
}

.im-ask-ai-bubble {
  position: absolute;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  background: var(--brand, #4f46e5);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  border-radius: 20px;
  cursor: pointer;
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.35);
  white-space: nowrap;
  user-select: none;
  transform: translateX(-50%);
  transition:
    opacity 0.15s,
    transform 0.15s;
}
.im-ask-ai-bubble:hover {
  opacity: 0.9;
  transform: translateX(-50%) scale(1.04);
}
.im-ask-ai-bubble::after {
  content: "";
  position: absolute;
  top: 100%;
  left: 50%;
  transform: translateX(-50%);
  border: 5px solid transparent;
  border-top-color: var(--brand, #4f46e5);
}
.im-bubble-enter-active,
.im-bubble-leave-active {
  transition:
    opacity 0.15s,
    transform 0.15s;
}
.im-bubble-enter-from,
.im-bubble-leave-to {
  opacity: 0;
  transform: translateX(-50%) translateY(4px);
}

.im-ask-ai-panel {
  position: absolute;
  z-index: 100;
  width: 340px;
  max-width: calc(100% - 24px);
  max-height: 380px;
  background: var(--bg-card, #fff);
  border: 1px solid var(--border, #e5e7eb);
  border-radius: var(--radius-lg, 10px);
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.12);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.im-panel-enter-active,
.im-panel-leave-active {
  transition:
    opacity 0.2s,
    transform 0.2s;
}
.im-panel-enter-from,
.im-panel-leave-to {
  opacity: 0;
  transform: translateY(8px) scale(0.97);
}

.im-aap-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px 8px;
  border-bottom: 1px solid var(--border, #e5e7eb);
}
.im-aap-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--brand, #4f46e5);
}
.im-aap-close {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border: none;
  background: transparent;
  cursor: pointer;
  color: var(--text-muted, #9ca3af);
  border-radius: 4px;
  transition:
    background 0.15s,
    color 0.15s;
}
.im-aap-close:hover {
  background: var(--bg-subtle, #f3f4f6);
  color: var(--text-primary, #111);
}
.im-aap-selected-text {
  padding: 8px 12px;
  background: var(--bg-subtle, #f8fafc);
  border-bottom: 1px solid var(--border, #e5e7eb);
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.im-aap-selected-label {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted, #9ca3af);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.im-aap-selected-content {
  font-size: 12px;
  color: var(--text-secondary, #6b7280);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.im-aap-body {
  padding: 12px;
  max-height: 280px;
  overflow-y: auto;
  flex: 1;
}
.im-aap-thinking {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--text-muted, #9ca3af);
  font-size: 12px;
}
.im-aap-dots {
  display: flex;
  gap: 3px;
}
.im-aap-dots span {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--brand, #4f46e5);
  animation: im-dot-bounce 1.2s infinite ease-in-out;
}
.im-aap-dots span:nth-child(2) {
  animation-delay: 0.2s;
}
.im-aap-dots span:nth-child(3) {
  animation-delay: 0.4s;
}
@keyframes im-dot-bounce {
  0%,
  80%,
  100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}
.im-aap-reply {
  font-size: 13px;
  line-height: 1.7;
  color: var(--text-primary, #111);
}
.im-aap-reply :deep(p) {
  margin: 0 0 8px;
}
.im-aap-reply :deep(p:last-child) {
  margin-bottom: 0;
}
.im-aap-reply :deep(code) {
  background: var(--bg-subtle, #f3f4f6);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
}
.im-aap-reply :deep(pre) {
  background: var(--bg-subtle, #f3f4f6);
  padding: 8px 10px;
  border-radius: 6px;
  overflow-x: auto;
  font-size: 12px;
}
.im-aap-reply :deep(.katex-display) {
  margin: 6px 0;
}
.im-aap-error {
  font-size: 12px;
  color: var(--red, #ef4444);
}
.im-aap-footer {
  padding: 8px 12px;
  border-top: 1px solid var(--border, #e5e7eb);
  display: flex;
  align-items: center;
}
.im-aap-btn-retry {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 4px 10px;
  border-radius: var(--radius-sm, 6px);
  border: 1px solid var(--border, #e5e7eb);
  background: transparent;
  cursor: pointer;
  font-size: 11px;
  color: var(--text-secondary, #6b7280);
  transition:
    border-color 0.15s,
    color 0.15s;
}
.im-aap-btn-retry:hover {
  border-color: var(--brand, #4f46e5);
  color: var(--brand, #4f46e5);
}
.im-aap-loading-hint {
  font-size: 11px;
  color: var(--text-muted, #9ca3af);
}
</style>
