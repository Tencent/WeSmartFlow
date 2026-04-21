"""内置资源包。

存放框架自带的默认资源文件：
- ``agent.md``：默认 Agent 灵魂/身份定义文件。
- ``skills/``：内置技能（SKILL.md）。
"""

from pathlib import Path

# 内置资源根目录
BUILTINS_DIR = Path(__file__).parent

# 默认 Agent 灵魂文件
DEFAULT_AGENT_IDENTITY_FILE = BUILTINS_DIR / "agent.md"

# 内置 skills 目录
BUILTIN_SKILLS_DIR = BUILTINS_DIR / "skills"

__all__ = ["BUILTINS_DIR", "DEFAULT_AGENT_IDENTITY_FILE", "BUILTIN_SKILLS_DIR"]
