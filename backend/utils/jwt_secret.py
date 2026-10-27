"""JWT 主密钥的加载、校验与持久化。

JWT 使用 HS256 对称签名，主密钥就是唯一的信任根：只要密钥可预测，
任何能访问后端端口的人都能伪造任意用户或管理员的 token。因此这里遵循
三条规则：

1. 仓库内不存在任何可用的默认密钥，历史默认值会被明确拒绝；
2. 显式配置的密钥必须足够长且不是占位符，否则启动直接失败（fail closed）；
3. 未显式配置时生成一次强随机密钥并以 0600 权限持久化，避免重启后
   所有会话失效，也避免把密钥写进源码或镜像。

密钥文件在多进程（uvicorn workers）下用文件锁串行化创建，保证所有
worker 读到同一个值。
"""

from __future__ import annotations

import logging
import os
import secrets
import stat
from pathlib import Path

try:  # POSIX（Linux/macOS）文件锁；其它平台退化为无锁创建
    import fcntl
except ImportError:  # pragma: no cover - 仅非 POSIX 平台
    fcntl = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

# HS256 的密钥应至少提供 256 bit 熵；32 个随机字符是最低要求。
MIN_SECRET_LENGTH = 32
# 拒绝 "aaaa...." / "121212...." 这类长度够但熵极低的填充串。
MIN_UNIQUE_CHARACTERS = 8
GENERATED_SECRET_BYTES = 48

# 仓库文档、示例与历史代码中出现过的公开字符串，一律禁止使用。
PUBLIC_PLACEHOLDER_SECRETS = frozenset(
    {
        "change-me-in-production",
        "changeme",
        "change-me",
        "wesmartflow-dev-secret-change-in-production",
        "your-secret-key",
        "please-change-me",
        "jwt-secret",
        "secret",
    }
)

# 随机串几乎不会包含这些片段；出现即表明仍在使用示例/占位配置。
_PLACEHOLDER_MARKERS = (
    "change-me",
    "changeme",
    "placeholder",
    "replace-me",
    "your-secret",
    "example-secret",
)

_GENERATE_HINT = 'python -c "import secrets; print(secrets.token_urlsafe(48))"'


class InsecureJWTSecretError(RuntimeError):
    """JWT 主密钥缺失、过弱或来自不可信来源。"""


def validate_jwt_secret(secret: str | None, *, source: str = "JWT_SECRET") -> str:
    """校验并返回可用的主密钥；不满足最低要求时抛出异常。"""
    value = (secret or "").strip()
    if not value:
        raise InsecureJWTSecretError(
            f"{source} 为空。请配置随机密钥，或删除该配置让程序自动生成："
            f"{_GENERATE_HINT}"
        )

    lowered = value.lower()
    if lowered in PUBLIC_PLACEHOLDER_SECRETS or any(
        marker in lowered for marker in _PLACEHOLDER_MARKERS
    ):
        raise InsecureJWTSecretError(
            f"{source} 是公开占位符，任何人都能据此伪造登录 token。"
            f"请更换为随机密钥：{_GENERATE_HINT}"
        )

    if len(value) < MIN_SECRET_LENGTH:
        raise InsecureJWTSecretError(
            f"{source} 长度不足 {MIN_SECRET_LENGTH} 个字符"
            f"（HS256 至少需要 256 bit 熵）。请生成：{_GENERATE_HINT}"
        )

    if len(set(value)) < MIN_UNIQUE_CHARACTERS:
        raise InsecureJWTSecretError(
            f"{source} 字符重复度过高，无法提供足够熵。请生成：{_GENERATE_HINT}"
        )

    return value


def load_jwt_secret(explicit: str | None, secret_file: Path) -> tuple[str, str]:
    """返回 ``(secret, source)``，source 为 ``environment`` 或 ``generated``。

    显式值优先；显式值不安全时直接失败，绝不回退到自动生成或历史默认值。
    """
    if explicit is not None and explicit.strip():
        return validate_jwt_secret(explicit), "environment"

    secret = _load_or_create_secret_file(Path(secret_file))
    return secret, "generated"


def _read_secret_file(path: Path) -> str | None:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise InsecureJWTSecretError(f"无法读取 JWT 密钥文件 {path}: {exc}") from exc

    value = raw.strip()
    if not value:
        return None

    try:
        secret = validate_jwt_secret(value, source=f"JWT 密钥文件 {path}")
    except InsecureJWTSecretError as exc:
        raise InsecureJWTSecretError(
            f"{exc} 如确认该文件已不可信，请删除后重启以重新生成。"
        ) from exc

    _ensure_private_permissions(path)
    return secret


def _ensure_private_permissions(path: Path) -> None:
    try:
        mode = stat.S_IMODE(path.stat().st_mode)
        if mode & 0o077:
            path.chmod(0o600)
            logger.warning(
                "JWT 密钥文件 %s 权限过宽（0o%o），已收紧为 0600", path, mode
            )
    except OSError as exc:  # 权限不足时不应阻断启动，但必须留痕
        logger.warning("无法收紧 JWT 密钥文件 %s 的权限: %s", path, exc)


def _load_or_create_secret_file(path: Path) -> str:
    existing = _read_secret_file(path)
    if existing:
        return existing

    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise InsecureJWTSecretError(
            f"无法创建 JWT 密钥目录 {path.parent}: {exc}。"
            "请在 .env 显式配置 JWT_SECRET。"
        ) from exc

    # 锁文件与密钥文件同目录：多 worker 同时首次启动时只会生成一个密钥。
    lock_path = path.with_name(path.name + ".lock")
    try:
        lock_fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT, 0o600)
    except OSError as exc:
        raise InsecureJWTSecretError(
            f"无法创建 JWT 密钥锁文件 {lock_path}: {exc}。"
            "请在 .env 显式配置 JWT_SECRET。"
        ) from exc

    try:
        if fcntl is not None:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

        # 拿到锁后重新读取：可能已被其它 worker 创建。
        existing = _read_secret_file(path)
        if existing:
            return existing

        generated = secrets.token_urlsafe(GENERATED_SECRET_BYTES)
        tmp_path = path.with_name(
            f"{path.name}.{os.getpid()}.{secrets.token_hex(6)}.tmp"
        )
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        # fdopen 接管 fd 的关闭；fsync 确保密钥落盘后再原子替换。
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(generated + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, 0o600)
        os.replace(tmp_path, path)
        return generated
    except OSError as exc:
        raise InsecureJWTSecretError(
            f"无法写入 JWT 密钥文件 {path}: {exc}。请在 .env 显式配置 JWT_SECRET。"
        ) from exc
    finally:
        if fcntl is not None:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            except OSError:
                pass
        os.close(lock_fd)
