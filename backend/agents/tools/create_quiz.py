"""
create_quiz：Agent 已出好题目后，将题目存入数据库
"""

from __future__ import annotations

import json

from agent_core.tool.base import BaseTool
from repositories.base import new_id, utcnow_str
from database import get_db


class CreateQuizTool(BaseTool):
    """
    将 Agent 已生成好的测验题目存入数据库，等待用户作答。
    """

    name = "create_quiz"
    description = "将已生成好的测验题目保存到数据库中。当你已经构思好题目内容、选项和答案后，调用此工具完成存储。"
    parameters = {
        "type": "object",
        "properties": {
            "node_id": {"type": "string", "description": "目标知识节点 id"},
            "quiz_type": {
                "type": "string",
                "enum": ["multiple_choice", "fill_in", "true_false", "open_ended"],
                "description": "题目类型",
            },
            "question": {"type": "string", "description": "已生成的题目内容"},
            "options": {
                "type": "array",
                "items": {"type": "string"},
                "description": '选择题选项列表（如 ["A. 选项一", "B. 选项二"]），非选择题不填',
            },
            "correct_answer": {
                "type": "string",
                "description": "正确答案（选择题填选项字母，简答题填参考答案）",
            },
            "explanation": {
                "type": "string",
                "description": "答题解析，说明为什么这个答案是正确的",
            },
        },
        "required": [
            "node_id",
            "quiz_type",
            "question",
            "correct_answer",
            "explanation",
        ],
    }

    def __init__(self, user_id: str, session_id: str, on_result_hook=None):
        super().__init__(on_result_hook=on_result_hook)
        self._user_id = user_id
        self._session_id = session_id

    def run(
        self,
        node_id: str,
        quiz_type: str,
        question: str,
        correct_answer: str,
        explanation: str,
        options: list[str] = None,
    ) -> str:
        quiz_id = new_id()
        now = utcnow_str()

        with get_db() as conn:
            conn.execute(
                """
                INSERT INTO quizzes
                  (id, user_id, node_id, session_id, quiz_type, question, options,
                   correct_answer, explanation, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    quiz_id,
                    self._user_id,
                    node_id,
                    self._session_id,
                    quiz_type,
                    question,
                    json.dumps(options, ensure_ascii=False) if options else None,
                    correct_answer,
                    explanation,
                    now,
                ),
            )

        result = {
            "quiz_id": quiz_id,
            "question": question,
            "type": quiz_type,
        }
        if options:
            result["options"] = options

        return json.dumps(result, ensure_ascii=False)
