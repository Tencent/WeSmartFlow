"""
@tool 装饰器

支持将普通函数快速转换为 BaseTool 实例，自动从函数签名推断 JSON Schema。

用法::

    @tool
    def get_weather(city: str, unit: str = "celsius") -> str:
        \"\"\"获取指定城市的天气信息

        Args:
            city: 城市名称
            unit: 温度单位，默认摄氏度
        \"\"\"
        return f"{city} 今天 25°C"

    @tool(name="weather", description="查询天气")
    def get_weather(city: str) -> str:
        return f"{city} 今天 25°C"

    # 异步函数同样支持
    @tool
    async def search(query: str) -> str:
        \"\"\"搜索信息\"\"\"
        return await do_search(query)
"""

from __future__ import annotations

import asyncio
import inspect
from typing import Any, Callable, Dict, List, Optional, get_type_hints

from .base import BaseTool


# ============================================================
# Python 类型 → JSON Schema 类型映射
# ============================================================

_TYPE_MAP: Dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    tuple: "array",
    set: "array",
    dict: "object",
}


def _python_type_to_json_schema(annotation: Any) -> str:
    """将 Python 类型注解转换为 JSON Schema 类型字符串。"""
    if annotation is inspect.Parameter.empty or annotation is None:
        return "string"  # 默认当作 string

    # 直接匹配
    if annotation in _TYPE_MAP:
        return _TYPE_MAP[annotation]

    # 处理泛型: List[X] → array, Dict[K,V] → object
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        if origin in (list, tuple, set):
            return "array"
        if origin is dict:
            return "object"

    return "string"


# ============================================================
# Docstring 参数描述解析（Google 风格）
# ============================================================


def _parse_param_docs(docstring: str) -> Dict[str, str]:
    """
    从 Google 风格 docstring 中提取参数描述。

    支持格式::

        Args:
            city: 城市名称
            unit: 温度单位，默认摄氏度
    """
    param_docs: Dict[str, str] = {}
    if not docstring:
        return param_docs

    lines = docstring.split("\n")
    in_args_section = False

    for line in lines:
        stripped = line.strip()

        # 检测 Args: 段落开始
        if stripped.lower() in ("args:", "arguments:", "parameters:", "params:"):
            in_args_section = True
            continue

        # 检测其他段落开始 → 退出 Args 段落
        if (
            in_args_section
            and stripped
            and stripped.endswith(":")
            and ":" not in stripped[:-1]
        ):
            in_args_section = False
            continue

        if in_args_section and ":" in stripped:
            parts = stripped.split(":", 1)
            if len(parts) == 2:
                name_part = parts[0].strip().lstrip("-").strip()
                desc_part = parts[1].strip()

                # 去掉可能的类型标注 "param_name (str)"
                if "(" in name_part and ")" in name_part:
                    name_part = name_part[: name_part.index("(")].strip()

                if name_part and desc_part:
                    param_docs[name_part] = desc_part

    return param_docs


def _build_parameters_schema(func: Callable) -> Dict[str, Any]:
    """
    从函数签名自动构建 OpenAI Function Calling 的 parameters JSON Schema。

    支持：
    - 从类型注解推断参数类型
    - 从 docstring 提取参数描述（Google 风格）
    - 识别必填/可选参数（有默认值 → 可选）
    """
    sig = inspect.signature(func)

    try:
        hints = get_type_hints(func)
    except Exception:  # pylint: disable=broad-except
        hints = {}

    param_docs = _parse_param_docs(func.__doc__ or "")

    properties: Dict[str, Any] = {}
    required: List[str] = []

    for param_name, param in sig.parameters.items():
        # 跳过 *args 和 **kwargs
        if param.kind in (param.VAR_POSITIONAL, param.VAR_KEYWORD):
            continue

        annotation = hints.get(param_name, param.annotation)
        json_type = _python_type_to_json_schema(annotation)

        prop: Dict[str, Any] = {"type": json_type}

        # 描述
        if param_name in param_docs:
            prop["description"] = param_docs[param_name]
        else:
            prop["description"] = f"参数 {param_name}"

        # 默认值
        if param.default is not inspect.Parameter.empty:
            prop["default"] = param.default
        else:
            required.append(param_name)

        properties[param_name] = prop

    return {
        "type": "object",
        "properties": properties,
        "required": required,
    }


# ============================================================
# FunctionTool：装饰器生成的工具实例
# ============================================================


class FunctionTool(BaseTool):
    """
    由 @tool 装饰器生成的工具实例，包装一个普通函数。

    同时支持同步和异步函数。
    """

    def __init__(
        self,
        func: Callable,
        name: Optional[str] = None,
        description: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ):
        self._func = func
        self._is_async = asyncio.iscoroutinefunction(func)

        # 自动推断
        tool_name = name or func.__name__
        tool_description = (
            description
            or (func.__doc__ or "").strip().split("\n")[0]
            or f"调用函数 {func.__name__}"
        )
        tool_parameters = parameters or _build_parameters_schema(func)

        super().__init__(
            name=tool_name,
            description=tool_description,
            parameters=tool_parameters,
        )

    def run(self, **kwargs: Any) -> Any:
        """同步执行被包装的函数。"""
        if self._is_async:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(self._func(**kwargs))
            finally:
                loop.close()
        return self._func(**kwargs)

    async def async_run(self, **kwargs: Any) -> Any:
        """异步执行被包装的函数。"""
        if self._is_async:
            return await self._func(**kwargs)
        return await asyncio.to_thread(self._func, **kwargs)


# ============================================================
# @tool 装饰器
# ============================================================


def tool(
    func: Optional[Callable] = None,
    *,
    name: Optional[str] = None,
    description: Optional[str] = None,
    parameters: Optional[Dict[str, Any]] = None,
) -> Any:
    """
    将普通函数转换为 BaseTool 实例的装饰器。

    支持两种用法：

    1. 无参数::

        @tool
        def get_weather(city: str) -> str:
            ...

    2. 带参数::

        @tool(name="weather", description="查询天气")
        def get_weather(city: str) -> str:
            ...

    Args:
        func: 被装饰的函数（无参数装饰器时自动传入）
        name: 工具名称（默认使用函数名）
        description: 工具描述（默认使用 docstring 第一行）
        parameters: 自定义参数 JSON Schema（默认从函数签名推断）

    Returns:
        FunctionTool: 工具实例
    """

    def decorator(fn: Callable) -> FunctionTool:
        return FunctionTool(
            func=fn,
            name=name,
            description=description,
            parameters=parameters,
        )

    if func is not None:
        # @tool 无参数形式
        return decorator(func)

    # @tool(...) 带参数形式
    return decorator
