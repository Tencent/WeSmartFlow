"""沉浸式学习（AI主导学习）服务包。

对外只暴露 `immersive_generate`（SSE 异步生成器）。
其余子模块（sse / repository / agents / tts / node_extractor / utils）
均为内部实现细节，不建议外部直接 import。
"""

from services.immersive.service import immersive_generate

__all__ = ["immersive_generate"]
