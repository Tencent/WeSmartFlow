# WeSmartFlow 数据模型

> 本地个人知识大脑 — 数据结构设计文档

## 核心理念

- **前端只负责渲染**，所有数据和逻辑来自后端
- **5 个核心实体**：User / Document / Node / Session / Quiz
- 知识图谱由 Agent 在学习过程中**自动构建**，用户无需手动维护

---

## 实体定义

### User（用户）

```json
{
  "id": "user_01",
  "name": "Rony",
  "created_at": "...",
  "config": {
    "llm_provider": "ollama", // ollama / openai / claude
    "llm_model": "qwen2.5:7b",
    "api_key": null,
    "api_base_url": "http://localhost:11434"
  },
  "stats": {
    "total_nodes": 12,
    "total_sessions": 23,
    "streak_days": 7,
    "total_study_minutes": 480
  }
}
```

---

### Document（文档）

文档是知识的**原始材料**，有两种来源：

```json
{
  "id": "doc_01",
  "user_id": "user_01",
  "name": "数据结构与算法.pdf",
  "type": "pdf", // pdf / markdown / url / note
  "source": "uploaded", // "uploaded"（用户上传）/ "generated"（AI生成）
  "source_session_id": null, // source=generated 时：由哪次会话生成
  "source_node_id": null, // source=generated 时：对应哪个知识节点
  "size_bytes": 2048000,
  "url": "/data/documents/doc_01.pdf",
  "status": "processed", // uploaded / processing / processed / failed
  "extracted_node_ids": ["node_01", "node_02", "node_05"],
  "uploaded_at": "...",
  "processed_at": "..."
}
```

**Document 生命周期**：

```
用户上传 → status: processing → Agent 提取知识点 → status: processed
                                                        ↓
                                          extracted_node_ids（产物节点）

会话生成 → source: generated → status: ready（直接可用）
```

---

### Node（知识节点）

知识图谱的核心单元，代表一个可独立理解的概念。

```json
{
  "id": "node_01",
  "user_id": "user_01",

  "title": "递归算法",
  "emoji": "🔄",
  "subject": "算法",
  "tags": ["递归", "分治", "算法基础"],
  "description": "将大问题分解为同类型的小问题求解的编程方法",

  "mastery": {
    "overall": 72,
    "understanding": 80,
    "retention": 65,
    "connection": 70
  },
  "last_studied_at": "2026-04-09T11:30:00Z",
  "next_review_at": "2026-04-10T11:30:00Z",

  "relations": [
    {
      "target_node_id": "node_02",
      "type": "prereq"
    }
  ],

  "source_doc_ids": ["doc_01"],
  "source_session_ids": ["sess_01"],

  "created_at": "...",
  "updated_at": "..."
}
```

**关系类型（relations.type）**：
| 类型 | 含义 |
|------|------|
| `prereq` | 前置依赖（我依赖目标节点） |
| `extends` | 延伸（我是目标节点的深化） |
| `applies` | 应用（我是目标节点的具体应用） |
| `contrasts` | 对比（我与目标节点形成对比） |
| `related` | 相关（弱关联） |

**掌握度三维模型（后端计算，前端只读）**：
| 维度 | 含义 | 更新方式 |
|------|------|---------|
| `understanding` | 理解度：能解释这个概念 | 会话质量评估 |
| `retention` | 记忆度：随时间衰减（遗忘曲线） | 时间流逝 + 复习重置 |
| `connection` | 连接度：与其他节点的关联深度 | 跨节点对话次数 |

---

### Session（学习会话）

一次完整的学习过程，包含对话、卡片和产出物。

```json
{
  "id": "sess_01",
  "user_id": "user_01",

  "title": "递归算法入门",
  "primary_node_id": "node_01",
  "mode": "chat", // "chat"（卡片对话）/ "courseware"（PDF课件）

  "status": "completed", // active / completed / abandoned
  "started_at": "2026-04-09T11:00:00Z",
  "ended_at": "2026-04-09T11:35:00Z",
  "duration_minutes": 35,

  "messages": [
    {
      "id": "msg_01",
      "role": "user",
      "content": "递归的三要素是什么？",
      "slide_id": null,
      "created_at": "..."
    },
    {
      "id": "msg_02",
      "role": "assistant",
      "content": "递归的三要素是...",
      "slide_id": "slide_02",
      "graph_update": {
        "action": "update_mastery",
        "node_id": "node_01",
        "new_mastery": 72
      },
      "created_at": "..."
    }
  ],

  "slides": [
    {
      "id": "slide_01",
      "type": "concept",
      "title": "递归三要素",
      "content": {},
      "node_id": "node_01",
      "created_at": "..."
    }
  ],

  "courseware_doc_id": null,

  "new_node_ids": ["node_07"],
  "mastery_updates": [
    { "node_id": "node_01", "before": 64, "after": 72, "delta": 8 },
    { "node_id": "node_07", "before": 0, "after": 40, "delta": 40 }
  ],

  "created_at": "..."
}
```

---

### Quiz（习题）

```json
{
  "id": "quiz_01",
  "user_id": "user_01",
  "node_id": "node_01",
  "source_session_id": "sess_01",
  "source_slide_id": "slide_05",

  "type": "single_choice",
  "question": "递归算法必须满足的条件是？",
  "options": ["A. 有终止条件", "B. 有递推关系", "C. 两者都要", "D. 都不对"],
  "answer": "C",
  "explanation": "递归必须有基础情况（终止条件）和递推步骤...",
  "difficulty": "medium",

  "attempts": [
    {
      "answer": "C",
      "is_correct": true,
      "time_spent_seconds": 18,
      "answered_at": "..."
    }
  ],

  "created_at": "..."
}
```

---

## 实体关系图

```
User
 │
 ├── Document[]
 │    ├── source: "uploaded"  ──→ Agent提取 ──→ Node[]
 │    └── source: "generated" ──→ 归属 Node（由Session产生）
 │
 ├── Node[]（知识图谱）
 │    ├── 来自 Document（提取）
 │    ├── 来自 Session（对话衍生）
 │    ├── mastery（后端维护，遗忘曲线）
 │    └── relations ──→ Node[]（图谱边）
 │
 ├── Session[]
 │    ├── → Slide[]（本次卡片，存在Session里）
 │    ├── → Document（PDF课件，courseware模式）
 │    ├── → Quiz[]（生成习题，归属Node）
 │    └── → Node[]（新节点 + mastery更新）
 │
 └── Quiz[]
      └── 归属 Node
```

---

## API 接口设计

```
# 用户
GET    /api/me
PATCH  /api/me/config

# 节点
GET    /api/nodes              所有节点（图谱数据，含relations）
GET    /api/nodes/:id          节点详情
PATCH  /api/nodes/:id          手动编辑节点信息

# 文档
GET    /api/documents          文档列表
POST   /api/documents          上传文档（multipart/form-data）
GET    /api/documents/:id      文档详情 + 提取状态
DELETE /api/documents/:id      删除文档

# 会话
GET    /api/sessions           历史会话列表
POST   /api/sessions           开始新会话 { topic, mode }
GET    /api/sessions/:id       会话详情（含slides）
POST   /api/sessions/:id/message  发送消息（SSE流式）
POST   /api/sessions/:id/finish   结束会话 → 返回summary

# 习题
GET    /api/quizzes            习题列表（?node_id=xxx 筛选）
POST   /api/quizzes/generate   生成习题 { node_id, count, difficulty }
POST   /api/quizzes/:id/answer 提交答案 { answer }
```

---

## 知识图谱构建时机

| 时机        | 触发条件       | 动作                             |
| ----------- | -------------- | -------------------------------- |
| 对话实时    | 每条消息       | 提取概念，推送 graph_update 事件 |
| 会话结束    | 点击「完成」   | 批量更新节点掌握度，归档卡片     |
| PDF生成完成 | courseware模式 | 批量提取章节 → 节点，爆炸式增长  |
| 文档上传    | 上传成功       | Agent解析提取，去重后入图谱      |
| 测验答题    | 提交答案       | 答对+掌握度，答错记录薄弱点      |

---

## 前端页面 ↔ API 对应

| 页面               | 主要读取                       | 写入操作             |
| ------------------ | ------------------------------ | -------------------- |
| Graph 知识图谱     | GET /api/nodes                 | —                    |
| Knowledge 节点库   | GET /api/nodes/:id             | —                    |
| Documents 文档管理 | GET/POST/DELETE /api/documents | 上传文档             |
| Chat AI辅导        | POST /api/sessions + SSE       | 发消息、结束会话     |
| Sessions 历史会话  | GET /api/sessions              | —                    |
| Quiz 练习          | GET/POST /api/quizzes          | 提交答案             |
| Dashboard 主页     | 汇总数据                       | —                    |
| Profile 档案       | GET /api/me                    | —                    |
| Settings 设置      | GET /api/me                    | PATCH /api/me/config |
