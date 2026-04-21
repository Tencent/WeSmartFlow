"""
new_core - 新一代 Agent 框架

基于原生 Function Calling 的 Agent 框架。
"""

__version__ = "0.1.0"

from .context import BaseContextBuilder
from .skills import SkillsLoader

__all__ = ["BaseContextBuilder", "SkillsLoader"]
