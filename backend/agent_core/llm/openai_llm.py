# -*- coding: utf-8 -*-
"""标准 OpenAI API 实现。

使用 openai.OpenAI / openai.AsyncOpenAI 客户端调用标准 OpenAI 兼容接口，
通过 LLM_API_KEY 鉴权，支持任何 OpenAI 兼容的 API 端点（如 OpenAI 官方、
Azure OpenAI、vLLM、Ollama 等）。
"""

from __future__ import annotations

import os
import random
import time
from typing import Any, Dict, List, Optional

from openai import AsyncOpenAI, OpenAI

from .base import BaseLLM, LLMResponse, ToolCallRequest


# ---------------------------------------------------------------------------
# 内部工具函数
# ---------------------------------------------------------------------------


def _normalize_params(model_name: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """过滤并规范化传给 OpenAI API 的额外参数。

    - 移除值为 None 的键
    - 部分模型（o1/o3 系列）不支持 temperature / top_p，自动剔除
    """
    # o1/o3 系列不支持 temperature、top_p、presence_penalty、frequency_penalty
    _o_series = model_name.startswith(("o1", "o3"))
    _unsupported = (
        {"temperature", "top_p", "presence_penalty", "frequency_penalty"}
        if _o_series
        else set()
    )

    return {k: v for k, v in config.items() if v is not None and k not in _unsupported}


def _parse_tool_calls(raw_tool_calls: Any) -> List["ToolCallRequest"]:
    """将 OpenAI SDK 返回的 tool_calls 列表解析为 ToolCallRequest 列表。"""
    import json as _json

    if not raw_tool_calls:
        return []
    result = []
    for tc in raw_tool_calls:
        try:
            args_str = tc.function.arguments or "{}"
            try:
                arguments = _json.loads(args_str)
            except _json.JSONDecodeError:
                arguments = {"_raw": args_str}
            result.append(
                ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=arguments,
                )
            )
        except Exception:  # pylint: disable=broad-except
            continue
    return result


class OpenAILLM(BaseLLM):
    """标准 OpenAI API 的 LLM 实现，支持 Function Calling。

    通过 LLM_API_KEY + LLM_BASE_URL 鉴权，兼容所有 OpenAI 格式的 API。

    环境变量：
        LLM_API_KEY:   API 密钥（必需）
        LLM_BASE_URL:  API 端点（可选，默认 https://api.openai.com/v1）
        LLM_MODEL:     默认模型名（可选，默认 gpt-4o）
        LLM_TIMEOUT:   请求超时秒数（可选，默认 300）
        LLM_MAX_RETRIES:      最大重试次数（可选，默认 3）
        LLM_RETRY_BASE_DELAY: 重试基础延迟秒数（可选，默认 1.0）
        LLM_RETRY_MAX_DELAY:  重试最大延迟秒数（可选，默认 8.0）

    Example::

        llm = OpenAILLM("gpt-4o")
        resp = llm.think([{"role": "user", "content": "你好"}])
        print(resp.content)
    """

    RETRYABLE_STATUS_CODES = {408, 409, 425, 429, 500, 502, 503, 504}

    def __init__(
        self,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
        retry_base_delay: Optional[float] = None,
        retry_max_delay: Optional[float] = None,
        before_call=None,
        **kwargs: Any,
    ):
        model_name = model_name or os.getenv("LLM_MODEL", "gpt-4o")
        api_key = api_key or os.getenv("LLM_API_KEY")
        base_url = base_url or os.getenv("LLM_BASE_URL")  # None 则使用 SDK 默认值
        timeout = (
            timeout if timeout is not None else int(os.getenv("LLM_TIMEOUT", "300"))
        )

        max_retries = (
            max_retries
            if max_retries is not None
            else int(os.getenv("LLM_MAX_RETRIES", "3"))
        )

        retry_base_delay = (
            retry_base_delay
            if retry_base_delay is not None
            else float(os.getenv("LLM_RETRY_BASE_DELAY", "1.0"))
        )

        retry_max_delay = (
            retry_max_delay
            if retry_max_delay is not None
            else float(os.getenv("LLM_RETRY_MAX_DELAY", "8.0"))
        )

        if not api_key:
            raise ValueError("api_key 必须被提供或通过环境变量 LLM_API_KEY 定义。")

        super().__init__(model_name, before_call=before_call, **kwargs)

        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries))
        self.retry_base_delay = max(0.0, float(retry_base_delay))
        self.retry_max_delay = max(self.retry_base_delay, float(retry_max_delay))

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------

    def _make_client(self) -> OpenAI:
        """创建同步 OpenAI 客户端。"""
        kw: Dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kw["base_url"] = self.base_url
        return OpenAI(**kw)

    def _make_async_client(self) -> AsyncOpenAI:
        """创建异步 OpenAI 客户端。"""
        kw: Dict[str, Any] = {"api_key": self.api_key}
        if self.base_url:
            kw["base_url"] = self.base_url
        return AsyncOpenAI(**kw)

    def _compute_retry_delay(self, attempt: int) -> float:
        """指数退避 + 随机抖动。"""
        delay = min(
            self.retry_max_delay, self.retry_base_delay * (2 ** max(attempt - 1, 0))
        )
        return delay * random.uniform(0.8, 1.2)

    def _is_retryable(self, exc: Exception) -> bool:
        """判断异常是否可重试。"""
        from openai import APIConnectionError, APIStatusError, APITimeoutError

        if isinstance(exc, (APITimeoutError, APIConnectionError)):
            return True
        if isinstance(exc, APIStatusError):
            return exc.status_code in self.RETRYABLE_STATUS_CODES
        msg = str(exc).lower()
        return any(
            kw in msg for kw in ("timeout", "rate limit", "temporarily unavailable")
        )

    def _build_kwargs(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]],
        tool_choice: Optional[Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """组装传给 OpenAI SDK 的参数字典。"""
        kw: Dict[str, Any] = {
            "model": self.model_name,
            "messages": messages,
            "timeout": self.timeout,
            **_normalize_params(self.model_name, dict(config)),
        }
        if tools:
            kw["tools"] = tools
        if tool_choice is not None:
            kw["tool_choice"] = tool_choice
        return kw

    @staticmethod
    def _to_llm_response(completion: Any, model_name: str, attempt: int) -> LLMResponse:
        """将 OpenAI CompletionResponse 转为 LLMResponse。"""
        choice = completion.choices[0]
        message = choice.message
        tool_calls = _parse_tool_calls(getattr(message, "tool_calls", None))
        usage = {}
        if completion.usage:
            usage = {
                "prompt_tokens": completion.usage.prompt_tokens,
                "completion_tokens": completion.usage.completion_tokens,
                "total_tokens": completion.usage.total_tokens,
            }
        return LLMResponse(
            content=message.content or "",
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            metadata={"model": model_name, "attempts": attempt},
        )

    # ------------------------------------------------------------------
    # BaseLLM 接口实现
    # ------------------------------------------------------------------

    def think(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """同步调用标准 OpenAI API。"""
        self._fire_before_call()
        merged_config = {**self.default_config, **(config or {})}
        kw = self._build_kwargs(messages, tools, tool_choice, merged_config)
        total_attempts = self.max_retries + 1

        for attempt in range(1, total_attempts + 1):
            try:
                client = self._make_client()
                completion = client.chat.completions.create(**kw)
                return self._to_llm_response(completion, self.model_name, attempt)

            except Exception as exc:  # pylint: disable=broad-except
                retryable = self._is_retryable(exc)
                if attempt >= total_attempts or not retryable:
                    return LLMResponse(
                        content=f"Error: {exc}",
                        finish_reason="error",
                        metadata={
                            "error": True,
                            "error_message": str(exc),
                            "model": self.model_name,
                            "attempts": attempt,
                            "retryable": retryable,
                        },
                    )
                time.sleep(self._compute_retry_delay(attempt))

        # 不应到达此处
        return LLMResponse(
            content="Error: unknown", finish_reason="error", metadata={"error": True}
        )

    async def async_think(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Any] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> LLMResponse:
        """异步调用标准 OpenAI API。"""
        import asyncio

        await self._async_fire_before_call()
        merged_config = {**self.default_config, **(config or {})}
        kw = self._build_kwargs(messages, tools, tool_choice, merged_config)
        total_attempts = self.max_retries + 1

        for attempt in range(1, total_attempts + 1):
            try:
                client = self._make_async_client()
                completion = await client.chat.completions.create(**kw)
                return self._to_llm_response(completion, self.model_name, attempt)

            except Exception as exc:  # pylint: disable=broad-except
                retryable = self._is_retryable(exc)
                if attempt >= total_attempts or not retryable:
                    return LLMResponse(
                        content=f"Error: {exc}",
                        finish_reason="error",
                        metadata={
                            "error": True,
                            "error_message": str(exc),
                            "model": self.model_name,
                            "attempts": attempt,
                            "retryable": retryable,
                        },
                    )
                await asyncio.sleep(self._compute_retry_delay(attempt))

        return LLMResponse(
            content="Error: unknown", finish_reason="error", metadata={"error": True}
        )


# ---------------------------------------------------------------------------
# 手动测试入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import asyncio

    from dotenv import load_dotenv

    load_dotenv()

    # ── 测试1：同步调用（无工具）──────────────────────────────────
    def test_sync():
        print("=" * 60)
        print("测试1：同步调用 think()")
        print("=" * 60)
        llm = OpenAILLM()
        messages = [
            {"role": "system", "content": "你是一个有帮助的助手，请简洁回答。"},
            {"role": "user", "content": "请用一句话解释什么是智能体。"},
        ]
        resp = llm.think(messages, config={"temperature": 0.7, "max_tokens": 256})
        print(f"  模型回复: {resp.content}")
        print(f"  finish_reason: {resp.finish_reason}")
        print(f"  usage: {resp.usage}")
        print(f"  is_error: {resp.is_error}")

    # ── 测试2：异步调用（无工具）──────────────────────────────────
    async def test_async():
        print("\n" + "=" * 60)
        print("测试2：异步调用 async_think()")
        print("=" * 60)
        llm = OpenAILLM()
        messages = [
            {"role": "system", "content": "你是一个有帮助的助手，请简洁回答。"},
            {"role": "user", "content": "什么是大语言模型？"},
        ]
        resp = await llm.async_think(
            messages, config={"temperature": 0.7, "max_tokens": 256}
        )
        print(f"  模型回复: {resp.content}")
        print(f"  finish_reason: {resp.finish_reason}")
        print(f"  is_error: {resp.is_error}")

    # ── 测试3：同步 Function Calling ──────────────────────────────
    def test_function_calling():
        print("\n" + "=" * 60)
        print("测试3：同步 Function Calling")
        print("=" * 60)
        llm = OpenAILLM()
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "get_weather",
                    "description": "获取指定城市的天气信息",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "city": {
                                "type": "string",
                                "description": "城市名称，如：北京、上海",
                            },
                            "unit": {
                                "type": "string",
                                "enum": ["celsius", "fahrenheit"],
                                "description": "温度单位",
                            },
                        },
                        "required": ["city"],
                    },
                },
            }
        ]
        messages = [
            {
                "role": "system",
                "content": "你是一个有帮助的助手。当用户询问天气时，请调用 get_weather 函数。",
            },
            {"role": "user", "content": "北京今天天气怎么样？"},
        ]
        resp = llm.think(messages, tools=tools, tool_choice="auto")
        print(f"  finish_reason: {resp.finish_reason}")
        if resp.has_tool_calls:
            print("  ✅ 模型返回了 tool_calls!")
            for tc in resp.tool_calls:
                print(f"     id: {tc.id}")
                print(f"     函数名: {tc.name}")
                print(f"     参数:   {tc.arguments}")
        elif resp.content:
            print(f"  ⚠️  模型直接回复文本: {resp.content[:200]}")
        else:
            print("  ❌ 既无 tool_calls 也无 content")

    async def run_async_tests():
        await test_async()

    try:
        test_sync()
        test_function_calling()
        asyncio.run(run_async_tests())
    except Exception as e:  # pylint: disable=broad-except
        import traceback

        print(f"\n测试运行失败: {e}")
        traceback.print_exc()
        print("\n请先设置 LLM_API_KEY 环境变量后再运行。")
