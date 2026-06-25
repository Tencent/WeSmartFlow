"""将已有的 .tex 文件编译为 PDF。"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import time
import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .base import BaseTool

logger = logging.getLogger(__name__)


def validate_pdf_file(pdf_path: Path, min_size: int = 1024) -> Optional[str]:
    """校验 PDF 是否是可交付的完整文件；返回 None 表示有效，否则返回失败原因。"""
    try:
        if not pdf_path.exists():
            return f"PDF 文件不存在: {pdf_path}"
        if not pdf_path.is_file():
            return f"PDF 路径不是文件: {pdf_path}"

        size = pdf_path.stat().st_size
        if size < min_size:
            return f"PDF 文件过小: {size} bytes"

        with pdf_path.open("rb") as fh:
            head = fh.read(16)
            fh.seek(max(size - 4096, 0))
            tail = fh.read()

        if not head.startswith(b"%PDF-"):
            return "PDF 文件头无效，缺少 %PDF- 标记"
        if b"startxref" not in tail:
            return "PDF 文件尾部无效，缺少 startxref"
        if b"%%EOF" not in tail:
            return "PDF 文件尾部无效，缺少 %%EOF"

        return None
    except OSError as exc:
        return f"PDF 文件读取失败: {exc}"


class LatexPdfCompileTool(BaseTool):
    """将已有的 .tex 文件编译为 PDF。"""

    name = "latex_pdf_compile"
    description = (
        "将指定的 .tex 文件编译为 PDF，输出 PDF 与 .tex 文件同目录同文件名。"
        "模板目录由系统配置自动注入，无需手动指定。"
        "成功时返回 PDF 文件的绝对路径，失败时返回 Error: 开头的错误信息。"
    )
    parameters = {
        "type": "object",
        "properties": {
            "tex_path": {
                "type": "string",
                "description": "待编译的 .tex 文件绝对路径",
            },
            "engine": {
                "type": "string",
                "description": "编译器策略：auto / latexmk / xelatex，默认 auto",
            },
            "timeout": {
                "type": "integer",
                "description": "单次编译命令超时时间（秒），默认 240",
            },
            "runs": {
                "type": "integer",
                "description": "使用 xelatex 直接编译时的轮数，默认 1（单页卡片无需多次编译）",
            },
        },
        "required": ["tex_path"],
    }

    def __init__(self, template_dir: Optional[Path] = None):
        self.default_template_dir = template_dir.resolve() if template_dir else None
        super().__init__()

    # ── 内部工具方法 ──

    def _resolve_template_dir(self) -> Optional[Path]:
        """返回模板目录，不存在则返回 None（不强制要求）。"""
        if (
            self.default_template_dir
            and self.default_template_dir.exists()
            and self.default_template_dir.is_dir()
        ):
            return self.default_template_dir
        return None

    @staticmethod
    def _inject_search_path(env: Dict[str, str], key: str, extra_path: Path) -> None:
        current = env.get(key, "")
        prefix = str(extra_path)
        env[key] = (
            f"{prefix}{os.pathsep}{current}" if current else f"{prefix}{os.pathsep}"
        )

    def _build_env(self) -> Dict[str, str]:
        env = os.environ.copy()
        template_path = self._resolve_template_dir()
        if template_path:
            self._inject_search_path(env, "TEXINPUTS", template_path)
            self._inject_search_path(env, "BIBINPUTS", template_path)
            self._inject_search_path(env, "BSTINPUTS", template_path)
        return env

    @staticmethod
    def _run_command(
        command: list[str], cwd: Path, env: Dict[str, str], timeout: int
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            command,
            cwd=str(cwd),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )

    def _compile_with_latexmk(
        self, tex_path: Path, env: Dict[str, str], timeout: int, output_dir: Path
    ) -> subprocess.CompletedProcess[str]:
        return self._run_command(
            [
                "latexmk",
                "-xelatex",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "-file-line-error",
                f"-outdir={output_dir}",
                tex_path.name,
            ],
            cwd=tex_path.parent,
            env=env,
            timeout=timeout,
        )

    def _compile_with_xelatex(
        self,
        tex_path: Path,
        env: Dict[str, str],
        timeout: int,
        runs: int,
        output_dir: Path,
    ) -> subprocess.CompletedProcess[str]:
        last_result: Optional[subprocess.CompletedProcess[str]] = None
        for _ in range(max(1, runs)):
            last_result = self._run_command(
                [
                    "xelatex",
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-file-line-error",
                    "-output-directory",
                    str(output_dir),
                    tex_path.name,
                ],
                cwd=tex_path.parent,
                env=env,
                timeout=timeout,
            )
            if last_result.returncode != 0:
                break
        assert last_result is not None
        return last_result

    @staticmethod
    def _quarantine_invalid_pdf(pdf_path: Path, reason: str) -> Optional[Path]:
        """将坏 PDF 从正式路径移走，避免前端继续加载。"""
        if not pdf_path.exists():
            return None
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        quarantine_path = pdf_path.with_name(f"{pdf_path.stem}.invalid_{timestamp}.pdf")
        try:
            pdf_path.replace(quarantine_path)
            logger.warning(
                "已隔离无效 PDF: %s -> %s，原因: %s", pdf_path, quarantine_path, reason
            )
            return quarantine_path
        except OSError as exc:
            logger.error(
                "隔离无效 PDF 失败: %s，原因: %s，错误: %s", pdf_path, reason, exc
            )
            return None

    @staticmethod
    def _copy_compile_log(tmp_log_path: Path, log_path: Path) -> None:
        """将临时编译日志复制到 tex 同目录，便于排查失败原因。"""
        if not tmp_log_path.exists():
            return
        try:
            shutil.copy2(tmp_log_path, log_path)
        except OSError as exc:
            logger.warning(
                "复制 PDF 编译日志失败: %s -> %s，错误: %s", tmp_log_path, log_path, exc
            )

    def run(
        self,
        tex_path: str = "",
        engine: str = "auto",
        timeout: int = 240,
        runs: int = 1,
        **kwargs: Any,
    ) -> str:
        tex = Path(tex_path).expanduser().resolve()
        if not tex.exists():
            return f"Error: .tex 文件不存在: {tex}"
        if tex.suffix.lower() != ".tex":
            return f"Error: 文件不是 .tex 文件: {tex}"

        pdf_path = tex.with_suffix(".pdf")
        log_path = tex.with_suffix(".log")
        env = self._build_env()

        selected_engine = (engine or "auto").lower()
        if selected_engine not in {"auto", "latexmk", "xelatex"}:
            return "Error: engine 只支持 auto / latexmk / xelatex"

        latexmk_exists = shutil.which("latexmk") is not None
        xelatex_exists = shutil.which("xelatex") is not None

        if selected_engine == "latexmk" and not latexmk_exists:
            return "Error: 系统中未找到 latexmk"
        if selected_engine == "xelatex" and not xelatex_exists:
            return "Error: 系统中未找到 xelatex"
        if selected_engine == "auto" and not (latexmk_exists or xelatex_exists):
            return "Error: 系统中既没有 latexmk，也没有 xelatex，无法编译 PDF"

        compiler_used = (
            "latexmk"
            if selected_engine in {"auto", "latexmk"} and latexmk_exists
            else "xelatex"
        )

        existing_pdf_error = validate_pdf_file(pdf_path) if pdf_path.exists() else None
        if existing_pdf_error:
            self._quarantine_invalid_pdf(pdf_path, existing_pdf_error)

        result: subprocess.CompletedProcess[str]
        tmp_pdf_path: Path
        tmp_log_path: Path
        try:
            with tempfile.TemporaryDirectory(
                prefix=f".{tex.stem}_compile_", dir=str(tex.parent)
            ) as tmp_dir_name:
                tmp_dir = Path(tmp_dir_name)
                tmp_pdf_path = tmp_dir / pdf_path.name
                tmp_log_path = tmp_dir / log_path.name

                if compiler_used == "latexmk":
                    result = self._compile_with_latexmk(
                        tex, env=env, timeout=timeout, output_dir=tmp_dir
                    )
                else:
                    result = self._compile_with_xelatex(
                        tex, env=env, timeout=timeout, runs=runs, output_dir=tmp_dir
                    )

                self._copy_compile_log(tmp_log_path, log_path)
                validation_error = validate_pdf_file(tmp_pdf_path)
                success = result.returncode == 0 and validation_error is None
                if success:
                    tmp_pdf_path.replace(pdf_path)
                    logger.info("PDF 编译并校验成功: %s", pdf_path)
                    return f"PDF 编译成功，路径：{str(pdf_path)}"
        except subprocess.TimeoutExpired:
            logger.error("PDF 编译超时: tex=%s timeout=%s", tex, timeout)
            return f"Error: PDF 编译超时（>{timeout} 秒），tex 文件: {tex}"

        # 失败时提取关键错误行
        file_log = (
            log_path.read_text(encoding="utf-8", errors="ignore")
            if log_path.exists()
            else ""
        )
        command_output = "\n".join(
            p for p in [result.stdout, result.stderr] if p
        ).strip()
        combined = "\n".join(p for p in [command_output, file_log] if p)
        error_lines = [
            line
            for line in combined.splitlines()
            if line.startswith("!") or "Error" in line or "error" in line
        ][:30]
        error_summary = "\n".join(error_lines) if error_lines else combined[:2000]
        validation_text = (
            f"\nPDF 校验失败: {validation_error}" if validation_error else ""
        )
        logger.error(
            "PDF 编译失败: compiler=%s returncode=%s tex=%s%s\n%s",
            compiler_used,
            result.returncode,
            tex,
            validation_text,
            error_summary,
        )
        return (
            f"Error: PDF 编译失败（{compiler_used} 返回码 {result.returncode}）{validation_text}\n"
            f"tex 文件: {tex}\n"
            f"编译日志: {log_path}\n"
            f"错误摘要:\n{error_summary}"
        )


latex_pdf_compile_tool = LatexPdfCompileTool()

__all__ = [
    "LatexPdfCompileTool",
    "latex_pdf_compile_tool",
    "validate_pdf_file",
]

if __name__ == "__main__":
    print(latex_pdf_compile_tool(tex_path="test_dir/chapter_01.tex"))
