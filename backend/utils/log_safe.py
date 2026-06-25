"""日志安全工具：清洗用户输入，防止 Log Injection (CWE-117)。

任何来源于 HTTP 请求（query/body/header/JWT payload 等）的字符串，
在写入日志前都应先通过 ``safe_log`` 处理，避免攻击者通过 CR/LF
等控制字符伪造或污染日志条目。
"""

from __future__ import annotations

from typing import Any

# 默认最大长度，避免恶意超长字符串撑爆日志
_DEFAULT_MAX_LEN = 128


def safe_log(value: Any, max_len: int = _DEFAULT_MAX_LEN) -> str:
    """清洗用于日志输出的字符串。

    Args:
        value: 任意值，会被 ``str()`` 转换为字符串。
        max_len: 截断长度，默认 128。传入 ``0`` 或负数表示不截断。

    Returns:
        移除 CR/LF 等控制字符并按需截断后的字符串。``None`` 会返回空串。

    Note:
        采用显式的 ``str.replace`` 链而非正则替换，
        以便静态分析工具（CodeQL ``py/log-injection`` 等）将其识别为
        Log Injection (CWE-117) 的 sanitizer。
    """
    if value is None:
        return ""
    s = str(value)
    # 关键：显式去除换行/回车，阻断日志条目伪造
    cleaned = (
        s.replace("\r", "")
        .replace("\n", "")
        .replace("\t", " ")
        .replace("\x0b", "")
        .replace("\x0c", "")
        .replace("\x00", "")
        .replace("\x7f", "")
    )
    if max_len and max_len > 0:
        cleaned = cleaned[:max_len]
    return cleaned
