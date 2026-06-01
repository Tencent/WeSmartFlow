"""
ValidateVizCodeTool：校验 Agent 生成的 EduViz 可视化代码

校验内容：
  1. JavaScript 语法（用 Node.js 解析）
  2. JavaScript 语义（用 ESLint 做作用域分析，抓 no-undef / no-redeclare 等）
  3. EduViz API 调用规范（白名单 API、必要参数）
  4. 危险操作（window.parent、外部 URL、import/require、document.write）
  5. p5.js 实例模式 / 必须有可视化输出

返回：
  ok: 通过
  Error: 列出所有问题，Agent 据此修复
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

from agent_core.tool.base import BaseTool

from .viz_registry import (
    API_NAMES,
    REMOVED_APIS,
    LIB_NAMES,
    FORBIDDEN_PATTERNS,
    HAS_OUTPUT_PATTERNS,
)

# 别名，保持下方代码可读性
_EDUVIZ_APIS = API_NAMES
_REMOVED_APIS = REMOVED_APIS
_VALID_LIBS = LIB_NAMES
_FORBIDDEN_PATTERNS = FORBIDDEN_PATTERNS

# eslint 资源目录（与本文件同级）
_ESLINT_DIR = Path(__file__).parent / "eslint_assets"
_ESLINT_CONFIG = _ESLINT_DIR / "eslint.config.mjs"
# frontend/node_modules/.bin/eslint
_ESLINT_BIN = (
    Path(__file__).parent.parent.parent.parent
    / "frontend"
    / "node_modules"
    / ".bin"
    / "eslint"
)


def _find_node() -> str | None:
    """定位 node 可执行文件：先 PATH，再当前 Python 解释器同目录（conda env），再常见路径。"""
    node = shutil.which("node")
    if node:
        return node
    # conda 环境中 node 通常和 python 同目录
    py_dir = Path(sys.executable).parent
    candidate = py_dir / "node"
    if candidate.exists():
        return str(candidate)
    # 常见安装位置
    for p in ("/opt/homebrew/bin/node", "/usr/local/bin/node"):
        if Path(p).exists():
            return p
    return None


class ValidateVizCodeTool(BaseTool):
    """
    校验 EduViz 可视化 JavaScript 代码。

    1. node --check 做语法解析
    2. ESLint 做作用域分析（no-undef / no-redeclare / no-const-assign 等运行时必炸的错）
    3. EduViz API / loadLib 库 / 危险模式正则检查
    4. p5 实例模式 + 必须有可视化输出

    通过返回 'ok'，否则返回以 'Error:' 开头的多条问题列表。
    """

    name = "validate_viz_code"
    description = (
        "校验 EduViz 可视化 JavaScript 代码的合法性。"
        "传入文件路径，返回 'ok' 表示通过，否则返回 'Error: ...' 列出所有问题。"
        "建议在写完代码后调用此工具校验，根据错误信息修复后重试。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "file_path": {
                "type": "string",
                "description": "要校验的 .js 文件绝对路径",
            },
        },
        "required": ["file_path"],
    }

    def run(self, file_path: str, **_) -> str:
        path = Path(file_path)
        if not path.exists():
            return f"Error: 文件不存在 {file_path}"

        try:
            code = path.read_text(encoding="utf-8")
        except Exception as e:  # pylint: disable=broad-except
            return f"Error: 读取文件失败 {e}"

        if not code.strip():
            return "Error: 代码为空"

        errors: list[str] = []

        # 1. 语法检查（用 node --check，如果有）
        syntax_err = self._check_syntax(code)
        if syntax_err:
            errors.append(f"[语法] {syntax_err}")

        # 2. 语义检查（ESLint 作用域分析），仅当语法通过时才跑，避免无意义噪声
        if not syntax_err:
            eslint_errs = self._check_eslint(code)
            errors.extend(f"[语义] {e}" for e in eslint_errs)

        # 3. 危险模式
        for pat, msg in _FORBIDDEN_PATTERNS:
            if re.search(pat, code, flags=re.MULTILINE):
                errors.append(f"[禁用] {msg}")

        # 4. EduViz API 调用合法性
        valid_api_hint = "/".join(sorted(_EDUVIZ_APIS))
        for m in re.finditer(r"\bEduViz\s*\.\s*([a-zA-Z_$][\w$]*)", code):
            api = m.group(1)
            if api in _REMOVED_APIS:
                errors.append(
                    f"[API] EduViz.{api} 已在 v2 中移除。请用：{valid_api_hint}"
                )
            elif api not in _EDUVIZ_APIS:
                errors.append(
                    f"[API] EduViz 没有 {api} 方法。可用 API：{sorted(_EDUVIZ_APIS)}"
                )

        # 5. loadLib 参数检查
        for m in re.finditer(r"EduViz\s*\.\s*loadLib\s*\(([^)]*)\)", code):
            args = m.group(1)
            for lib_match in re.finditer(r"['\"]([a-zA-Z_]+)['\"]", args):
                lib_name = lib_match.group(1)
                if lib_name not in _VALID_LIBS:
                    errors.append(
                        f"[loadLib] 未知库 '{lib_name}'。可用库：{sorted(_VALID_LIBS)}"
                    )

        # 6. p5.js 必须使用实例模式
        uses_p5 = bool(
            re.search(r"EduViz\s*\.\s*loadLib\s*\([^)]*['\"]p5['\"]", code)
            or re.search(r"\bnew\s+p5\b", code)
        )
        if uses_p5 and not re.search(r"\bnew\s+p5\s*\(", code):
            errors.append(
                "[p5] 加载了 p5.js 但未使用实例模式。"
                "由于沙箱代码被包在 async function 内，`function setup`/`function draw` "
                "不会挂到 window 上，p5 全局模式无法生效。"
                "请使用：new p5(p => { p.setup = ...; p.draw = ... }, EduViz.getContainer())"
            )

        # 7. 必须有可视化输出（从 registry 自动派生检测正则）
        has_output = any(re.search(p, code) for p in HAS_OUTPUT_PATTERNS)
        if not has_output:
            errors.append(
                "[输出] 代码没有任何可见输出，"
                "至少需要一个 EduViz 控件/容器/展示 API，或第三方库渲染器"
            )

        if errors:
            return "Error: 代码校验未通过：\n" + "\n".join(f"  - {e}" for e in errors)
        return "ok"

    # -------------------- 语法检查（node --check） --------------------
    def _check_syntax(self, code: str) -> str | None:
        """用 node --check 检查 JS 语法。如果找不到 node 则跳过。"""
        node = _find_node()
        if not node:
            return None

        # 把代码包成 async function 来匹配运行时（顶层 await 才合法）
        wrapped = f"(async function() {{\n{code}\n}})()"

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".js", delete=False, encoding="utf-8"
        ) as f:
            f.write(wrapped)
            tmp_path = f.name

        try:
            proc = subprocess.run(
                [node, "--check", tmp_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if proc.returncode == 0:
                return None
            return self._format_node_error(proc.stderr or proc.stdout, tmp_path)
        except subprocess.TimeoutExpired:
            return "语法检查超时"
        except Exception as e:  # pylint: disable=broad-except
            return f"语法检查异常: {e}"
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)
            except Exception:  # pylint: disable=broad-except
                pass

    @staticmethod
    def _format_node_error(raw: str, tmp_path: str) -> str:
        """
        把 node --check 的报错处理成用户友好的格式：
          - 隐藏临时文件绝对路径（含 macOS 上的 /private 软链接前缀）
          - 行号从 wrap 后回退到用户原文视角（第 1 行是 `(async function(){`）
          - 取最有信息量的前几行
        """
        text = (raw or "").strip()
        if not text:
            return "未知语法错误"

        # 把 "/abs/path/to/file.js:42" 整段替换成 "line 41"，行号 -1 回到用户视角。
        # 这样不论临时路径长什么样、有没有 /private 前缀都能命中。
        def shift_lineno(m: "re.Match[str]") -> str:
            return f"line {max(1, int(m.group(1)) - 1)}"

        text = re.sub(r"/[^\s:]+\.js:(\d+)", shift_lineno, text)
        # 兜底：把 node 内部栈里的 "node:internal/..." 行干掉
        text = re.sub(r"\s+at\s+\S+\s+\(node:[^)]+\)", "", text)

        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        # 丢掉 "Node.js vXX" 这种尾巴
        lines = [ln for ln in lines if not re.match(r"^Node\.js\s+v", ln)]
        return " | ".join(lines[:5])[:500]

    # -------------------- 语义检查（ESLint） --------------------
    def _check_eslint(self, code: str) -> list[str]:
        """
        用 ESLint 做作用域分析，抓出 node --check 抓不到的运行时错误，例如：
          - no-undef：引用未声明变量（典型 bug：箭头函数参数漏写却使用）
          - no-redeclare / no-const-assign / no-dupe-args / no-dupe-keys 等

        返回错误描述列表（已经把行号回退到用户原文视角）。
        失败（找不到 node/eslint、超时、解析异常）一律静默跳过，避免阻塞 Agent。
        """
        if not _ESLINT_CONFIG.exists() or not _ESLINT_BIN.exists():
            return []
        node = _find_node()
        if not node:
            return []

        # 包成 async IIFE：与运行时行为一致，且让顶层 await 合法
        wrapped = f"(async function() {{\n{code}\n}})()\n"
        # eslint flat config 的 basePath 限制要求目标文件在 config 所在目录树内，
        # 因此把临时文件写到 _ESLINT_DIR 下
        tmp_name = f".tmp_{uuid.uuid4().hex}.js"
        tmp_path = _ESLINT_DIR / tmp_name
        try:
            tmp_path.write_text(wrapped, encoding="utf-8")
            # 通过环境变量把 node 加到 PATH，eslint shebang 才能跑起来
            env = os.environ.copy()
            env["PATH"] = f"{Path(node).parent}{os.pathsep}{env.get('PATH', '')}"
            proc = subprocess.run(
                [
                    str(_ESLINT_BIN),
                    "--config",
                    str(_ESLINT_CONFIG),
                    "--no-config-lookup",
                    "--format",
                    "json",
                    str(tmp_path),
                ],
                capture_output=True,
                text=True,
                timeout=15,
                env=env,
            )
            stdout = proc.stdout.strip()
            if not stdout:
                return []
            try:
                results = json.loads(stdout)
            except json.JSONDecodeError:
                return []
            if not results:
                return []

            issues: list[str] = []
            for msg in results[0].get("messages", []):
                # 只把 error（severity=2）当成阻塞，warning 忽略
                if msg.get("severity") != 2:
                    continue
                rule = msg.get("ruleId") or "parse"
                line = msg.get("line", 0)
                col = msg.get("column", 0)
                # wrap 多了一行 "(async function() {"，所以行号 -1 还原用户视角
                user_line = max(1, line - 1) if line else 0
                text = (msg.get("message") or "").rstrip(".")
                issues.append(f"{rule} @ line {user_line}:{col} — {text}")
            return issues
        except subprocess.TimeoutExpired:
            return ["eslint 超时（>15s），跳过语义检查"]
        except Exception:  # pylint: disable=broad-except
            return []
        finally:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:  # pylint: disable=broad-except
                pass
