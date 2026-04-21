"""Agent tool 模块 — 工具定义、注册与执行。"""

from .agent_tool import AgentTool
from .base import BaseTool
from .decorator import FunctionTool, tool
from .filesystem import EditFileTool, ListDirTool, ReadFileTool, WriteFileTool
from .registry import ToolRegistry
from .shell import ExecTool
from .openai_image_gen import OpenAIImageGenTool
from .pdf_compile import LatexPdfCompileTool, latex_pdf_compile_tool
from .web import ArxivSearch, TavilySearch, WebFetch

__all__ = [
    # 基础
    "AgentTool",
    "BaseTool",
    "FunctionTool",
    "tool",
    "ToolRegistry",
    # 文件系统
    "ReadFileTool",
    "WriteFileTool",
    "EditFileTool",
    "ListDirTool",
    # Shell
    "ExecTool",
    # 图片生成
    "OpenAIImageGenTool",
    # PDF 编译
    "LatexPdfCompileTool",
    "latex_pdf_compile_tool",
    # Web / 搜索
    "WebFetch",
    "TavilySearch",
    "ArxivSearch",
]

# try:
#     from .mcp import MCPToolWrapper, connect_mcp_servers

#     __all__.extend(
#         [
#             "MCPToolWrapper",
#             "connect_mcp_servers",
#         ]
#     )
# except ModuleNotFoundError:
#     # 可选依赖（如 httpx / mcp）缺失时，不影响基础工具导入
#     pass
