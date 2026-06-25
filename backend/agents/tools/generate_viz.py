"""
GenerateInteractiveVizTool：两阶段循环生成交互式可视化代码

阶段一 Design 循环（纯 LLM，无工具）：
  design → judge → design → ... → 满意的 VizSpec（最多 MAX_DESIGN_ROUNDS 轮）

阶段二 Code 循环（纯 LLM Reflection）：
  code → validate_viz_code → judge → code → ... → 可运行的代码（最多 MAX_CODE_ROUNDS 轮）

生成的代码保存至 documents/viz/{viz_id}/viz.js，
metadata 保存至 documents/viz/{viz_id}/meta.json，
成功时返回 viz_id，前端按 viz_id 拉取代码并用 EduVizSandbox 渲染。
"""

from __future__ import annotations

import json
import logging
import tempfile
import uuid
from pathlib import Path
from typing import Optional

from json_repair import repair_json

from agent_core.tool.base import BaseTool
from config import VIZ_DIR
from repositories.document_repo import DocumentRepository
from services.llm_factory import get_llm
from utils.log_safe import safe_log

from .validate_viz_code import ValidateVizCodeTool
from .viz_registry import list_patterns_with_meta, load_pattern


logger = logging.getLogger(__name__)

MAX_DESIGN_ROUNDS = 3  # Design 循环最大轮数
MAX_CODE_ROUNDS = 3  # Code 循环最大轮数

# --------------------------------------------------------------------------
# 文档路径
# --------------------------------------------------------------------------

_CORE_PATH = (
    Path(__file__).parent.parent / "prompts" / "skills" / "eduviz_sdk" / "CORE.md"
)


def _load_core_doc() -> str:
    try:
        return _CORE_PATH.read_text(encoding="utf-8")
    except Exception as e:  # pylint: disable=broad-except
        logger.error("加载 CORE.md 失败: %s", e)
        return "（SDK 文档加载失败）"


# --------------------------------------------------------------------------
# 阶段一：Design 循环
# --------------------------------------------------------------------------


def _build_designer_system() -> str:
    """动态构建 Designer system prompt，viz_pattern 说明从 registry frontmatter 自动派生。"""
    metas = list_patterns_with_meta()

    # 生成 pattern 选择指引：每个 pattern 一行，包含名称、适用场景、推荐控件
    if metas:
        pattern_lines = []
        for m in metas:
            name = m.get("name", "")
            label = m.get("label", name)
            when = m.get("when_to_use", "")
            controls = m.get("controls", "")
            line = f"  - **{name}**（{label}）：{when}"
            if controls:
                line += f"\n    推荐控件：{controls}"
            pattern_lines.append(line)
        pattern_guide = "\n".join(pattern_lines)
        pattern_enum = " | ".join(m.get("name", "") for m in metas) + " | other"
    else:
        pattern_guide = "  - other：其他场景"
        pattern_enum = "other"

    return f"""\
你是「交互式可视化设计师」，专门为教学场景设计 EduViz 交互用例。

你的任务是输出一份结构化的 VizSpec（JSON），描述这个可视化的完整设计方案。

## viz_pattern 选择指南

根据概念的核心交互方式选择最合适的 pattern：

{pattern_guide}
  - **other**：以上均不适合时使用

## VizSpec 格式

```json
{{
  "title": "可视化标题",
  "concept": "核心概念一句话",
  "viz_pattern": "{pattern_enum}",
  "controls": [
    {{"type": "slider|toggle|select|stepper|button", "name": "控件名", "purpose": "作用说明", "range": "范围（slider 必填）"}}
  ],
  "canvas": {{
    "type": "axis2d | raw_canvas | svg_d3 | p5 | three | plotly | none",
    "description": "画布内容描述"
  }},
  "display": [
    {{"type": "latex|text|metric|progress", "name": "名称", "purpose": "展示什么"}}
  ],
  "interaction_flow": "用一段话描述用户如何操作、画面如何响应、学生能从中理解什么",
  "key_insight": "学生操作后应该获得的核心洞察"
}}
```

## 设计原则

- 每个可视化只讲一个概念，不要贪多
- 控件数量 2-4 个，不要超过 5 个
- 交互要直接体现概念的本质，不是装饰
- canvas 类型选最合适的，不要强行用复杂库
- 代码量控制在 120 行内（设计时就要考虑实现复杂度）

**只输出 JSON，不要有任何其他文字。**
"""


_DESIGN_JUDGE_SYSTEM = """\
你是「可视化设计评审官」，负责评审 VizSpec 设计方案的质量。

## 评审维度

1. **教学有效性**：交互是否真正帮助理解概念？还是只是好看？
2. **实现可行性**：控件和画布组合能否在 120 行 JS 内实现？
3. **聚焦度**：是否只讲一个概念？有没有过度设计？
4. **交互逻辑**：interaction_flow 是否清晰、合理？

## 输出格式

```json
{
  "pass": true | false,
  "score": 1-10,
  "issues": ["问题1", "问题2"],
  "suggestions": ["改进建议1", "改进建议2"]
}
```

**只输出 JSON，不要有任何其他文字。**
"""


def _design_viz(llm, title: str, concept: str, interaction_hint: str) -> dict:
    """
    Design 循环：design → judge → design → ...
    返回最终通过评审的 VizSpec dict。
    """
    designer_system = _build_designer_system()
    user_prompt = (
        f"请为以下教学内容设计一个交互式可视化方案：\n\n标题：{title}\n概念：{concept}"
    )
    if interaction_hint:
        user_prompt += f"\n交互形式建议：{interaction_hint}"

    spec_json: Optional[str] = None
    spec: dict = {}

    for round_i in range(1, MAX_DESIGN_ROUNDS + 1):
        logger.info("[Design] 第 %d 轮设计", round_i)

        # --- Design ---
        design_messages = [
            {"role": "system", "content": designer_system},
            {"role": "user", "content": user_prompt},
        ]
        if spec_json and round_i > 1:
            # 把上一轮的 spec 和 judge 意见带入
            design_messages[-1]["content"] = user_prompt  # 保持原始需求
            # 已经在 user_prompt 里追加了 judge 反馈（见下方）

        resp = llm.think(design_messages)
        spec_json = resp.content.strip()

        # 解析 JSON（用 json_repair 容错处理 LLM 输出的不规范 JSON）
        try:
            spec = json.loads(repair_json(spec_json))
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("[Design] 第 %d 轮 JSON 解析失败: %s", round_i, e)
            spec = {"title": title, "concept": concept, "raw": spec_json}
            # 解析失败直接用原始文本继续，不走 judge
            continue

        if round_i == MAX_DESIGN_ROUNDS:
            logger.info("[Design] 达到最大轮数，使用当前方案")
            break

        # --- Judge ---
        logger.info("[Design] 第 %d 轮评审", round_i)
        judge_messages = [
            {"role": "system", "content": _DESIGN_JUDGE_SYSTEM},
            {
                "role": "user",
                "content": f"请评审以下 VizSpec：\n\n```json\n{json.dumps(spec, ensure_ascii=False, indent=2)}\n```",
            },
        ]
        judge_resp = llm.think(judge_messages)
        judge_raw = judge_resp.content.strip()

        try:
            judge = json.loads(repair_json(judge_raw))
        except Exception:  # pylint: disable=broad-except
            logger.warning("[Design] Judge JSON 解析失败，跳过本轮评审")
            break

        score = judge.get("score", 10)
        passed = judge.get("pass", True)
        logger.info("[Design] Judge 评分: %s, pass: %s", score, passed)

        if passed and score >= 7:
            logger.info("[Design] 方案通过评审，进入 Code 阶段")
            break

        # 把 judge 意见追加到下一轮的 user_prompt
        issues = judge.get("issues", [])
        suggestions = judge.get("suggestions", [])
        feedback = "\n".join(
            ["\n\n## 上一轮设计的问题（请修正后重新设计）"]
            + [f"- 问题：{i}" for i in issues]
            + [f"- 建议：{s}" for s in suggestions]
        )
        user_prompt = f"请为以下教学内容设计一个交互式可视化方案：\n\n标题：{title}\n概念：{concept}"
        if interaction_hint:
            user_prompt += f"\n交互形式建议：{interaction_hint}"
        user_prompt += feedback

    return spec


# --------------------------------------------------------------------------
# 阶段二：Code 循环
# --------------------------------------------------------------------------


def _build_coder_system(core_doc: str, pattern_examples: str) -> str:
    examples_section = (
        f"\n\n---\n\n# 示例参考\n\n{pattern_examples}" if pattern_examples else ""
    )
    return f"""你是「交互式可视化代码生成器」，专门为教学场景生成 EduViz 沙箱代码。

## 任务

根据用户提供的 VizSpec（可视化设计方案），输出一段完整可运行的 JavaScript 代码。
如果用户反馈了上一轮的校验错误或评审意见，请针对性修复后重新输出完整代码。

## 输出规范

- **只输出 JavaScript 代码，不要有任何解释文字、markdown 代码块标记**
- 不要写 `<html>` `<body>` 等 HTML 标签
- 不要写 `import` / `require`，所有库通过 `await EduViz.loadLib(...)` 加载
- 直接写顶层代码，外层已经是 async function，可以直接 `await`
- 用 `EduViz.colors()` 取主题色，保持视觉一致
- 代码控制在 120 行内

## 代码原则

- **代码必须能跑**：不要写演示性的伪代码，每一行都要能在 iframe 沙箱中执行
- **严格按 VizSpec 实现**：不要自作主张增减控件或改变交互逻辑
- **只用 SDK 文档中的 API**：不要发明没有的方法
- **修复时定向修复**：每次只改报错相关的部分，不要重写整个代码

---

# EduViz SDK 核心文档

{core_doc}{examples_section}
"""


_CODE_JUDGE_SYSTEM = """\
你是「可视化代码评审官」，负责评审生成的 EduViz JS 代码质量。

## 评审维度

1. **与 VizSpec 的一致性**：代码是否按照设计方案实现了所有控件和交互？
2. **教学有效性**：交互逻辑是否正确体现了概念？
3. **代码质量**：有没有明显的逻辑错误、死代码、冗余？

## 输出格式

```json
{
  "pass": true | false,
  "issues": ["问题1", "问题2"],
  "fix_hints": ["修复提示1", "修复提示2"]
}
```

**只输出 JSON，不要有任何其他文字。**
"""


def _extract_code(raw: str) -> str:
    """从 LLM 输出中提取纯 JS 代码（去掉 markdown 代码块标记）。"""
    text = raw.strip()
    # 去掉 ```javascript ... ``` 或 ```js ... ``` 或 ``` ... ```
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉首行（```javascript）和末行（```）
        start = 1
        end = len(lines)
        if lines[-1].strip() == "```":
            end -= 1
        text = "\n".join(lines[start:end])
    return text.strip()


def _run_code_loop(
    work_dir: Path,
    spec: dict,
    user_id,
    core_doc: str,
    pattern_examples: str,
) -> str | None:
    """
    Code Reflection 循环：code → validate_viz_code → judge → code → ...
    纯 LLM 调用，无 Agent/工具框架。
    返回最终通过的 JS 代码字符串，失败返回 None。
    """
    validator = ValidateVizCodeTool()
    llm = get_llm(user_id)
    system_prompt = _build_coder_system(core_doc, pattern_examples)
    spec_str = json.dumps(spec, ensure_ascii=False, indent=2)

    # 对话历史（system + 多轮 user/assistant）
    messages: list[dict] = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": (
                f"请根据以下 VizSpec 生成交互式可视化代码：\n\n"
                f"```json\n{spec_str}\n```\n\n"
                f"直接输出 JavaScript 代码，不要有任何解释。"
            ),
        },
    ]

    code: str = ""

    for round_i in range(1, MAX_CODE_ROUNDS + 1):
        logger.info("[Code] 第 %d 轮生成", round_i)

        # --- Code：调用 LLM 生成/修复代码 ---
        resp = llm.think(messages)
        raw_code = resp.content or ""
        code = _extract_code(raw_code)

        # 把 assistant 回复追加到历史
        messages.append({"role": "assistant", "content": raw_code})

        if not code:
            logger.warning("[Code] 第 %d 轮输出为空", round_i)
            if round_i < MAX_CODE_ROUNDS:
                messages.append(
                    {
                        "role": "user",
                        "content": "你的输出为空，请重新生成完整的 JavaScript 代码。",
                    }
                )
            continue

        # --- Validate：写入临时文件校验 ---
        viz_path = work_dir / f"viz_r{round_i}.js"
        viz_path.write_text(code, encoding="utf-8")
        validate_result = validator.run(file_path=str(viz_path))

        if validate_result != "ok":
            logger.warning(
                "[Code] 第 %d 轮校验失败: %s", round_i, validate_result[:200]
            )
            if round_i < MAX_CODE_ROUNDS:
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"代码校验未通过，请修复以下问题后重新输出完整代码：\n\n"
                            f"{validate_result[:1000]}\n\n"
                            f"直接输出修复后的完整 JavaScript 代码，不要有任何解释。"
                        ),
                    }
                )
                continue
            else:
                logger.warning("[Code] 达到最大轮数，校验仍未通过，返回当前代码")
                return code  # 折中返回，前端会显示运行错误

        # --- Judge：评审代码与 VizSpec 的一致性 ---
        if round_i < MAX_CODE_ROUNDS:
            logger.info("[Code] 第 %d 轮 Judge 评审", round_i)
            judge_messages = [
                {"role": "system", "content": _CODE_JUDGE_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"VizSpec：\n```json\n{spec_str}\n```\n\n"
                        f"生成的代码：\n```javascript\n{code}\n```\n\n"
                        f"请评审代码是否正确实现了 VizSpec。"
                    ),
                },
            ]
            judge_resp = llm.think(judge_messages)
            judge_raw = judge_resp.content.strip()

            try:
                judge = json.loads(repair_json(judge_raw))
            except Exception:  # pylint: disable=broad-except
                logger.warning("[Code] Judge JSON 解析失败，视为通过")
                judge = {"pass": True}

            if judge.get("pass", True):
                logger.info("[Code] 第 %d 轮通过 Judge 评审", round_i)
                return code

            fix_hints = judge.get("fix_hints", judge.get("issues", []))
            logger.info(
                "[Code] 第 %d 轮 Judge 不通过，修复提示: %s", round_i, fix_hints
            )
            hints_text = "\n".join(f"- {h}" for h in fix_hints)
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"代码评审未通过，请修复以下问题后重新输出完整代码：\n\n"
                        f"{hints_text}\n\n"
                        f"直接输出修复后的完整 JavaScript 代码，不要有任何解释。"
                    ),
                }
            )
        else:
            # 最后一轮，校验通过直接返回
            logger.info("[Code] 第 %d 轮校验通过，返回代码", round_i)
            return code

    return code if code else None


# --------------------------------------------------------------------------
# Tool 主类
# --------------------------------------------------------------------------


class GenerateInteractiveVizTool(BaseTool):
    """
    两阶段循环生成交互式可视化代码（基于 EduViz SDK）。

    阶段一：Design 循环 — LLM 设计 VizSpec，Judge 评审，最多 MAX_DESIGN_ROUNDS 轮
    阶段二：Code 循环  — Coder Agent 写代码，validate + Judge 评审，最多 MAX_CODE_ROUNDS 轮

    成功时返回 viz_id（前端通过 /api/viz/{viz_id} 拉取代码），
    失败时返回 'Error: ...'。
    """

    name = "generate_interactive_viz"
    description = (
        "委派专门的子 Agent 生成一个交互式可视化教学示例。"
        "适用于「需要学生通过动手操作（拖滑块、看动画、逐步执行）才能真正理解的概念」，"
        "如：函数图像变化、算法过程、概率分布演化、物理模拟等。"
        "你只需描述要展示的概念和期望的交互形式，子 Agent 负责设计方案、编写 JavaScript 代码、校验、修复。"
        "生成的可视化会自动登记到文档系统（file_type='viz'），并可通过 node_ids 关联知识节点。"
        "成功返回 viz_id 字符串（同时也是 document_id），失败返回 'Error: ...'。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "可视化标题，简洁明确，如「导数的几何意义」「冒泡排序过程」",
            },
            "concept": {
                "type": "string",
                "description": (
                    "要让学生理解的核心概念。详细说明这个概念是什么、关键点在哪里，"
                    "便于子 Agent 设计合适的可视化。"
                ),
            },
            "interaction_hint": {
                "type": "string",
                "description": (
                    "建议的交互形式。例如：「滑块控制 Δx，观察割线变切线」、"
                    "「步进器逐步展示每一轮比较和交换」、「时间轴自动播放分布演化」。"
                    "可以为空，让子 Agent 自由发挥。"
                ),
            },
            "node_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "关联的知识节点 ID 列表，用于把可视化与节点建立链接（便于后续检索/复用）",
            },
        },
        "required": ["title", "concept"],
    }

    def __init__(self, user_id=None, session_id=None, on_result_hook=None):
        super().__init__(on_result_hook=on_result_hook)
        self.user_id = user_id
        self.session_id = session_id

    def run(
        self,
        title: str = "",
        concept: str = "",
        interaction_hint: str = "",
        node_ids: list = None,
        **kwargs,
    ) -> str:
        viz_id = str(uuid.uuid4())
        llm = get_llm(self.user_id)
        core_doc = _load_core_doc()

        # ── 阶段一：Design 循环 ──────────────────────────────────────────
        logger.info("[GenerateViz] 开始 Design 循环: title=%s", safe_log(title))
        try:
            spec = _design_viz(llm, title, concept, interaction_hint)
        except Exception as e:  # pylint: disable=broad-except
            logger.exception("Design 循环异常")
            return f"Error: 设计阶段失败 — {e}"

        logger.info(
            "[GenerateViz] VizSpec 设计完成: %s",
            safe_log(json.dumps(spec, ensure_ascii=False)[:200]),
        )

        # ── 阶段二：Code 循环 ────────────────────────────────────────────
        # 只加载与 viz_pattern 匹配的单个示例，避免 token 浪费
        pattern_example = load_pattern(spec.get("viz_pattern", ""))
        logger.info(
            "[GenerateViz] 开始 Code 循环, viz_pattern=%s",
            safe_log(spec.get("viz_pattern", "unknown")),
        )
        with tempfile.TemporaryDirectory(prefix=f"viz_{viz_id}_") as _tmp:
            work_dir = Path(_tmp)
            try:
                code = _run_code_loop(
                    work_dir, spec, self.user_id or "default", core_doc, pattern_example
                )
            except Exception as e:  # pylint: disable=broad-except
                logger.exception("Code 循环异常")
                return f"Error: 代码生成阶段失败 — {e}"

            if not code:
                return "Error: 子 Agent 未生成有效代码"

            # ── 持久化 ───────────────────────────────────────────────────
            viz_dir = VIZ_DIR / viz_id
            viz_dir.mkdir(parents=True, exist_ok=True)

            viz_file = viz_dir / "viz.js"
            viz_file.write_text(code, encoding="utf-8")

            meta = {
                "viz_id": viz_id,
                "title": title,
                "concept": concept,
                "interaction_hint": interaction_hint,
                "viz_spec": spec,
                "user_id": self.user_id,
                "session_id": self.session_id,
            }
            (viz_dir / "meta.json").write_text(
                json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            self._create_document_record(
                viz_id=viz_id,
                viz_file=viz_file,
                title=title,
                concept=concept,
                interaction_hint=interaction_hint,
                spec=spec,
                node_ids=node_ids or [],
            )

            logger.info(
                "[GenerateViz] 生成成功: viz_id=%s, title=%s", viz_id, safe_log(title)
            )
            return viz_id

    def _create_document_record(
        self,
        viz_id: str,
        viz_file: Path,
        title: str,
        concept: str,
        interaction_hint: str,
        spec: dict,
        node_ids: list,
    ) -> None:
        if not self.user_id:
            logger.warning("GenerateInteractiveVizTool 缺少 user_id，跳过文档登记")
            return
        try:
            generation_prompt = concept
            if interaction_hint:
                generation_prompt += f"\n\n[交互形式]\n{interaction_hint}"

            doc = DocumentRepository().register_produced(
                doc_id=viz_id,
                user_id=self.user_id,
                title=title,
                file_path=viz_file,
                file_type="viz",
                session_id=self.session_id,
                generation_prompt=generation_prompt,
                node_ids=node_ids,
            )
            logger.info("可视化文档记录创建成功: %s", doc.id)
        except Exception as e:  # pylint: disable=broad-except
            logger.warning("创建可视化文档记录失败（不影响生成）: %s", e)
