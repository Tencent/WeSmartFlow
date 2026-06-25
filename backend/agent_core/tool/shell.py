"""Shell execution tool."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from .base import BaseTool

logger = logging.getLogger(__name__)


class ExecTool(BaseTool):
    """Tool to execute shell commands."""

    name = "exec"
    description = "Execute a shell command and return its output. Use with caution."
    parameters = {
        "type": "object",
        "properties": {
            "command": {
                "type": "string",
                "description": "The shell command to execute",
            },
            "working_dir": {
                "type": "string",
                "description": "Optional working directory for the command",
            },
            "timeout": {
                "type": "integer",
                "description": (
                    "Timeout in seconds. Increase for long-running commands "
                    "like compilation or installation (default 60, max 600)."
                ),
                "minimum": 1,
                "maximum": 600,
            },
        },
        "required": ["command"],
    }

    _MAX_TIMEOUT = 600
    _MAX_OUTPUT = 10_000

    def __init__(
        self,
        timeout: int = 60,
        working_dir: str | None = None,
        deny_patterns: list[str] | None = None,
        allow_patterns: list[str] | None = None,
        restrict_to_workspace: bool = False,
        path_append: str = "",
    ):
        self.timeout = timeout
        self.working_dir = working_dir
        self.deny_patterns = deny_patterns or [
            r"\brm\s+-[rf]{1,2}\b",
            r"\bdel\s+/[fq]\b",
            r"\brmdir\s+/s\b",
            r"(?:^|[;&|]\s*)format\b",
            r"\b(mkfs|diskpart)\b",
            r"\bdd\s+if=",
            r">\s*/dev/sd",
            r"\b(shutdown|reboot|poweroff)\b",
            r":\(\)\s*\{.*\};\s*:",
        ]
        self.allow_patterns = allow_patterns or []
        self.restrict_to_workspace = restrict_to_workspace
        self.path_append = path_append
        super().__init__()

    def run(
        self,
        command: str = "",
        working_dir: str | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> str:
        """同步入口：在无运行中事件循环时包装 async_run。"""
        try:
            asyncio.get_running_loop()
            return "Error: ExecTool.run cannot be called inside an active event loop; use async_run instead."
        except RuntimeError:
            return asyncio.run(
                self.async_run(
                    command=command, working_dir=working_dir, timeout=timeout, **kwargs
                )
            )

    async def async_run(
        self,
        command: str = "",
        working_dir: str | None = None,
        timeout: int | None = None,
        **kwargs: Any,
    ) -> str:
        cwd = working_dir or self.working_dir or os.getcwd()
        guard_error = self._guard_command(command, cwd)
        if guard_error:
            return guard_error

        effective_timeout = min(timeout or self.timeout, self._MAX_TIMEOUT)

        env = os.environ.copy()
        if self.path_append:
            env["PATH"] = env.get("PATH", "") + os.pathsep + self.path_append

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=env,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                process.kill()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError as wait_err:
                    logger.warning("Process did not terminate after kill: %s", wait_err)
                finally:
                    if sys.platform != "win32":
                        try:
                            os.waitpid(process.pid, os.WNOHANG)
                        except (ProcessLookupError, ChildProcessError) as e:
                            logger.debug("Process already reaped or not found: {}", e)
                return f"Error: Command timed out after {effective_timeout} seconds"

            output_parts = []

            if stdout:
                output_parts.append(stdout.decode("utf-8", errors="replace"))

            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace")
                if stderr_text.strip():
                    output_parts.append(f"STDERR:\n{stderr_text}")

            output_parts.append(f"\nExit code: {process.returncode}")

            result = "\n".join(output_parts) if output_parts else "(no output)"

            max_len = self._MAX_OUTPUT
            if len(result) > max_len:
                half = max_len // 2
                result = (
                    result[:half]
                    + f"\n\n... ({len(result) - max_len:,} chars truncated) ...\n\n"
                    + result[-half:]
                )

            return result

        except Exception as e:  # pylint: disable=broad-except
            return f"Error executing command: {str(e)}"

    def _guard_command(self, command: str, cwd: str) -> str | None:
        """Best-effort safety guard for potentially destructive commands."""
        cmd = command.strip()
        lower = cmd.lower()

        for pattern in self.deny_patterns:
            if re.search(pattern, lower):
                return "Error: Command blocked by safety guard (dangerous pattern detected)"

        if self.allow_patterns:
            if not any(re.search(p, lower) for p in self.allow_patterns):
                return "Error: Command blocked by safety guard (not in allowlist)"

        if self._contains_internal_url(cmd):
            return (
                "Error: Command blocked by safety guard (internal/private URL detected)"
            )

        if self.restrict_to_workspace:
            if "..\\" in cmd or "../" in cmd:
                return (
                    "Error: Command blocked by safety guard (path traversal detected)"
                )

            cwd_path = Path(cwd).resolve()

            for raw in self._extract_absolute_paths(cmd):
                try:
                    expanded = os.path.expandvars(raw.strip())
                    p = Path(expanded).expanduser().resolve()
                except Exception:  # pylint: disable=broad-except
                    continue
                if p.is_absolute() and cwd_path not in p.parents and p != cwd_path:
                    return "Error: Command blocked by safety guard (path outside working dir)"

        return None

    @staticmethod
    def _extract_absolute_paths(command: str) -> list[str]:
        win_paths = re.findall(r"[A-Za-z]:\\[^\s\"'|><;]+", command)
        posix_paths = re.findall(r"(?:^|[\s|>'\"])(/[^\s\"'>;|<]+)", command)
        home_paths = re.findall(r"(?:^|[\s|>'\"])(~[^\s\"'>;|<]*)", command)
        return win_paths + posix_paths + home_paths

    @staticmethod
    def _contains_internal_url(text: str) -> bool:
        """Detect internal/private URL targets without external dependency."""
        urls = re.findall(r"https?://([^/\s:]+)", text, flags=re.IGNORECASE)
        if not urls:
            return False

        private_patterns = [
            r"^localhost$",
            r"^127\.\d+\.\d+\.\d+$",
            r"^10\.\d+\.\d+\.\d+$",
            r"^192\.168\.\d+\.\d+$",
            r"^172\.(1[6-9]|2\d|3[0-1])\.\d+\.\d+$",
            r"^0\.0\.0\.0$",
            r"^::1$",
            r"\.local$",
            r"\.internal$",
        ]

        for host in urls:
            h = host.lower().strip("[]")
            if any(re.search(p, h) for p in private_patterns):
                return True
        return False
