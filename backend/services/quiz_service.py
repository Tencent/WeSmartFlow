"""
QuizService：出题与评分

- 调用 LLM 为指定节点出题
- 自动/手动评分（选择题/判断题自动，主观题 LLM 评分）
- 调用 MemoryService 更新 SM-2 状态
"""

from __future__ import annotations

import json
import logging
import sqlite3

from repositories import NodeRepository
from repositories.quiz_repo import QuizRepository
from services.llm_factory import get_llm
from services.memory_service import MemoryService

logger = logging.getLogger(__name__)


class QuizService:
    def __init__(self, db: sqlite3.Connection):
        self.db = db
        self.node_repo = NodeRepository(db)
        self.quiz_repo = QuizRepository(db)
        self.memory_service = MemoryService(db)
        self.llm = get_llm()

    async def generate_quiz(
        self,
        user_id: str,
        node_id: str,
        session_id: str = None,
        quiz_type: str = "multiple_choice",
    ) -> dict:
        """为某节点生成一道题"""
        node = self.node_repo.get_by_id(node_id)
        if not node:
            raise ValueError(f"节点 {node_id} 不存在")

        prompt = self._build_prompt(node, quiz_type)
        response = await self.llm.async_think(
            messages=[
                {"role": "system", "content": "你是出题专家，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ]
        )

        raw = response.content.strip()
        if "```" in raw:
            raw = raw.split("```")[1].lstrip("json").strip()

        quiz_data = json.loads(raw)
        quiz = self.quiz_repo.create(
            user_id=user_id,
            node_id=node_id,
            session_id=session_id,
            quiz_type=quiz_type,
            question=quiz_data["question"],
            options=quiz_data.get("options"),
            correct_answer=quiz_data["correct_answer"],
            explanation=quiz_data.get("explanation", ""),
        )
        return quiz.model_dump(mode="json")

    async def submit_answer(self, quiz_id: str, user_answer: str) -> dict:
        """用户提交答案，自动评分并更新记忆状态"""
        quiz = self.quiz_repo.get_by_id(quiz_id)
        if not quiz:
            raise ValueError(f"题目 {quiz_id} 不存在")

        # 评分
        if quiz.quiz_type == "multiple_choice":
            is_correct = self._check_multiple_choice(
                user_answer, quiz.correct_answer, quiz.options
            )
            score = 1.0 if is_correct else 0.0
        elif quiz.quiz_type == "true_false":
            is_correct = self._check_true_false(user_answer, quiz.correct_answer)
            score = 1.0 if is_correct else 0.0
        else:
            # 主观题（填空题 / 简答题）：LLM 评分
            is_correct, score = await self._llm_grade(
                quiz.question, quiz.correct_answer, user_answer
            )

        self.quiz_repo.submit_answer(quiz_id, user_answer, is_correct, score)

        # SM-2 quality: score 映射到 0~5
        quality = round(score * 5)
        memory_result = self.memory_service.review_node(quiz.node_id, quality)

        return {
            "quiz_id": quiz_id,
            "is_correct": is_correct,
            "score": score,
            "correct_answer": quiz.correct_answer,
            "explanation": quiz.explanation,
            "mastery_delta": memory_result["mastery_delta"],
        }

    def _build_prompt(self, node, quiz_type: str) -> str:
        content = node.content
        node_info = f"""知识节点：{node.title}
描述：{node.description}
核心要点：{"; ".join(content.key_points[:3])}
"""
        type_hint = {
            "multiple_choice": (
                "出一道单选题，提供4个选项（A/B/C/D），其中只有1个正确。"
                'correct_answer 必须只填选项字母（如 "B"），不要包含选项内容'
            ),
            "fill_in": "出一道填空题，答案为1~3个词或短句",
            "true_false": (
                "出一道判断题。"
                'correct_answer 必须填 "正确" 或 "错误"，不要用 True/False'
            ),
            "open_ended": "出一道简答题，考察对概念的深层理解",
        }[quiz_type]

        return f"""{node_info}

请{type_hint}。以如下 JSON 格式返回：
{{
  "question": "题目内容",
  "options": ["A. ...", "B. ...", "C. ...", "D. ..."],  // 仅选择题需要
  "correct_answer": "正确答案（选择题只填字母如 B，判断题填「正确」或「错误」）",
  "explanation": "详细解析"
}}"""

    @staticmethod
    def _check_multiple_choice(
        user_answer: str, correct_answer: str, options: list[str] | None
    ) -> bool:
        """选择题判题：兼容多种 correct_answer 格式。

        LLM 生成的 correct_answer 可能是：
        - 纯字母："B"
        - 字母+内容："B. O(n log n)"
        - 纯内容："O(n log n)"

        前端发送的 user_answer 始终是纯字母："A"/"B"/"C"/"D"
        """
        ua = user_answer.strip().upper()  # 用户答案，如 "B"
        ca = correct_answer.strip()

        # 情况 1：correct_answer 以字母开头（如 "B" 或 "B. xxx"）
        if ca and ca[0].upper() in "ABCD":
            # 取第一个字符比较
            if ca[0].upper() == ua:
                return True
            # 如果 correct_answer 就是纯字母
            if len(ca) == 1:
                return False

        # 情况 2：correct_answer 是纯内容（如 "O(n log n)"），需要在 options 中查找
        if options:
            ca_lower = ca.lower()
            for i, opt in enumerate(options):
                opt_clean = opt.strip()
                # 去掉选项前缀 "A. " / "A、" / "A) " 等
                opt_content = opt_clean
                if (
                    len(opt_clean) >= 2
                    and opt_clean[0].upper() in "ABCD"
                    and opt_clean[1] in ".、) "
                ):
                    opt_content = opt_clean[2:].strip()
                elif (
                    len(opt_clean) >= 3
                    and opt_clean[0].upper() in "ABCD"
                    and opt_clean[1:3] in [". ", "、 "]
                ):
                    opt_content = opt_clean[3:].strip()

                # 如果 correct_answer 匹配某个选项的内容
                if ca_lower == opt_content.lower() or ca_lower == opt_clean.lower():
                    correct_letter = chr(65 + i)  # A=65
                    return ua == correct_letter

        # 兜底：直接比较
        return ua.lower() == ca.lower()

    @staticmethod
    def _check_true_false(user_answer: str, correct_answer: str) -> bool:
        """判断题判题：兼容多种 correct_answer 格式。

        前端发送的 user_answer 是 "true" 或 "false"（布尔值转字符串）。
        LLM 生成的 correct_answer 可能是："正确"/"错误"/"True"/"False"/"对"/"错" 等。
        """
        ua = user_answer.strip().lower()
        ca = correct_answer.strip().lower()

        # 统一映射为布尔值
        true_values = {"true", "正确", "对", "是", "yes", "t", "1"}
        false_values = {"false", "错误", "错", "否", "no", "f", "0"}

        ua_bool = ua in true_values
        ca_bool = ca in true_values

        # 如果 correct_answer 无法识别，尝试直接比较
        if ca not in true_values and ca not in false_values:
            return ua == ca

        return ua_bool == ca_bool

    async def _llm_grade(
        self, question: str, correct_answer: str, user_answer: str
    ) -> tuple[bool, float]:
        """LLM 评分主观题，返回 (is_correct, score 0~1)"""
        prompt = f"""请评估以下答题的准确性。

问题：{question}
参考答案：{correct_answer}
用户答案：{user_answer}

请返回 JSON：
{{"score": 0.8, "comment": "评语"}}

score 为 0~1 的浮点数，1.0 表示完全正确。"""

        response = await self.llm.async_think(
            messages=[{"role": "user", "content": prompt}]
        )
        try:
            raw = response.content.strip()
            if "```" in raw:
                raw = raw.split("```")[1].lstrip("json").strip()
            data = json.loads(raw)
            score = float(data.get("score", 0.5))
            return score >= 0.6, score
        except Exception:  # pylint: disable=broad-except
            return False, 0.0
