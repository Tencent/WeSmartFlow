"""
WeSmartFlow 后端配置
"""

from pathlib import Path
import os
from dotenv import load_dotenv

from utils.jwt_secret import load_jwt_secret

# 加载仓库根目录的 .env（统一来源，模板见 backend/.env.example）
_root_env = Path(__file__).parent.parent / ".env"
if _root_env.exists():
    load_dotenv(_root_env)


# 项目根目录（支持通过环境变量 ROOT_DIR 配置，默认为 backend/ 的父目录）
ROOT_DIR = Path(os.getenv("ROOT_DIR", str(Path(__file__).parent.parent)))

# 数据目录
DATA_DIR = ROOT_DIR / "data"
DOCUMENTS_DIR = DATA_DIR / "documents"
UPLOADS_DIR = DOCUMENTS_DIR / "uploads"
CARDS_DIR = DOCUMENTS_DIR / "cards"
COURSES_DIR = DOCUMENTS_DIR / "courses"
VIZ_DIR = DOCUMENTS_DIR / "viz"
SESSIONS_DIR = DATA_DIR / "sessions"

# OKF 知识库根目录（概念 md 落盘根，由 ingest_okf 同步到 KG）
# 必须锚定到仓库根，避免进程 cwd 漂移导致 md 写到 backend/knowledge/ 这种错误位置。
# 子目录由写回工具按 subject 自行 mkdir，此处不预创建。
KNOWLEDGE_ROOT = Path(os.getenv("KNOWLEDGE_ROOT", str(ROOT_DIR / "knowledge")))

# 默认指向 SimplePlus-BeamerTheme 主题目录
TEX_TEMPLATE_DIR = Path(
    os.getenv("TEX_TEMPLATE_DIR", str(Path(__file__).parent / "SimplePlus-BeamerTheme"))
)

# 日志目录
LOG_DIR = DATA_DIR / "logs"

# SQLite 数据库
DB_PATH = DATA_DIR / "wesmartflow.db"

# JWT 配置
# 签名算法在 utils/jwt_tokens.py 中固定为 HS256，禁止由环境变量切换。
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "72"))

# 主密钥：显式配置必须是足够长的随机串；留空则在 data/ 下生成并持久化。
# 历史上公开的默认值会在启动时被拒绝，绝不静默回退。
JWT_SECRET_FILE = Path(
    os.getenv("JWT_SECRET_FILE", "").strip() or DATA_DIR / "jwt_secret.key"
)
if not JWT_SECRET_FILE.is_absolute():
    JWT_SECRET_FILE = ROOT_DIR / JWT_SECRET_FILE
JWT_SECRET, JWT_SECRET_SOURCE = load_jwt_secret(
    os.getenv("JWT_SECRET"), JWT_SECRET_FILE
)

# Admin 审核台账号（明文，单人后台用）
# 必须在 .env 配置；未配置则 admin 登录直接 503。
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "")
# admin token 单独的过期时间（更短）
ADMIN_TOKEN_EXPIRE_HOURS = int(os.getenv("ADMIN_TOKEN_EXPIRE_HOURS", "12"))

# credits 用量体系（1 credit = 1 元 / 1,000,000，见 services/pricing.py）
# 赠送规则与跨月余额见 services/credit_wallet.py。
# 开关关闭时仍记账和扣余额，但不阻止余额不足的调用。
CREDITS_ENFORCEMENT_ENABLED = os.getenv(
    "CREDITS_ENFORCEMENT_ENABLED", "true"
).lower() in {"1", "true", "yes"}
# 单次运行允许超出剩余额度的预借比例（0.2 = 最多超 20%），
# 用于在「credits 调用后才知道」的约束下换取实现简单。
CREDITS_BORROW_RATIO = float(os.getenv("CREDITS_BORROW_RATIO", "0.2"))

# SMTP 邮件配置（用于邮箱验证码登录和积分卡发送）
SMTP_HOST = os.getenv("SMTP_HOST", "")  # SMTP 服务器地址，如 smtp.qq.com
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # SMTP 端口，SSL 通常为 465
SMTP_USER = os.getenv("SMTP_USER", "")  # 发件邮箱地址
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # SMTP 授权码（非邮箱密码）
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "WeSmartFlow")  # 发件人显示名称

# 微信小程序配置（扫码登录）
WECHAT_MP_APPID = os.getenv("WECHAT_MP_APPID", "")  # 小程序 AppID
WECHAT_MP_SECRET = os.getenv("WECHAT_MP_SECRET", "")  # 小程序 AppSecret

# ── weclaw 微信通道（多租户：每个用户扫码绑定自己的 bot）──────────────
# 接收消息只能靠 clawbridge 长轮询（无 webhook）；本项目用 async httpx 协程池实现，
# 每个已启用的 bot 一个长轮询协程（≈ 一条 idle 长连接），由 ChannelManager 统一调度。
WECLAW_ENABLED = os.getenv("WECLAW_ENABLED", "false").lower() in {"1", "true", "yes"}
WECLAW_BASE_URL = os.getenv("WECLAW_BASE_URL", "https://clawbridge.weixin.qq.com")
WECLAW_CDN_BASE_URL = os.getenv(
    "WECLAW_CDN_BASE_URL", "https://novac2c.cdn.weixin.qq.com/c2c"
)
WECLAW_LONG_POLL_TIMEOUT_MS = int(os.getenv("WECLAW_LONG_POLL_TIMEOUT_MS", "35000"))
# 对外可访问的基础 URL，用于拼卡片 / PDF 链接（微信 webview 打开），末尾不带斜杠。
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
# 卡片渲染成图片（Playwright 无头 Chromium）：html/quiz/viz 卡片截图后作为图片发到微信。
WECLAW_RENDER_CARDS = os.getenv("WECLAW_RENDER_CARDS", "true").lower() in {
    "1",
    "true",
    "yes",
}
WECLAW_RENDER_WIDTH = int(os.getenv("WECLAW_RENDER_WIDTH", "480"))  # 截图视口宽度(px)
WECLAW_RENDER_TIMEOUT_MS = int(os.getenv("WECLAW_RENDER_TIMEOUT_MS", "15000"))
# EduViz 沙箱 SDK 源文件（用于后端复刻 viz 沙箱做截图）
EDUVIZ_SDK_PATH = (
    ROOT_DIR / "frontend" / "src" / "components" / "EduViz" / "eduviz-sdk.js"
)

# GitHub OAuth 配置
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

# 服务配置
# 默认只监听回环地址：登录 token 的保护不能依赖“别人连不上”。
# 需要局域网/公网访问时显式改为 0.0.0.0，并由反向代理/防火墙限制来源。
BACKEND_HOST = os.getenv("BACKEND_HOST", "127.0.0.1")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8080"))
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:5174,http://localhost:5173"
    ).split(",")
    if origin.strip()
]

# 文件上传限制
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "100"))
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}

# 确保数据目录存在
for _dir in [
    DATA_DIR,
    DOCUMENTS_DIR,
    UPLOADS_DIR,
    CARDS_DIR,
    COURSES_DIR,
    VIZ_DIR,
    SESSIONS_DIR,
    LOG_DIR,
]:
    _dir.mkdir(parents=True, exist_ok=True)

TTS_MODEL = os.getenv(
    "TTS_MODEL", "cosyvoice-v1"
)  # 角色语音模型（v1 默认；v2 需开通对应权限）


_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def security_warnings() -> list[str]:
    """启动时输出的安全配置提示（不阻断启动，密钥不安全会直接抛异常）。"""
    warnings: list[str] = []

    if JWT_SECRET_SOURCE == "generated":
        warnings.append(
            f"未显式配置 JWT_SECRET，已使用自动生成的密钥文件 {JWT_SECRET_FILE}；"
            "请备份该文件，生产环境建议在 .env 显式配置 JWT_SECRET"
        )

    if BACKEND_HOST not in _LOOPBACK_HOSTS:
        warnings.append(
            f"BACKEND_HOST={BACKEND_HOST}：服务监听非回环地址，"
            "请确保前面有反向代理/防火墙，不要把端口直接暴露到公网"
        )

    if "*" in CORS_ORIGINS:
        warnings.append(
            "CORS_ORIGINS 包含 *：请改为具体的前端源，避免任意站点携带凭据访问 API"
        )

    if not ADMIN_USERNAME.strip() or not ADMIN_PASSWORD:
        warnings.append(
            "未配置 ADMIN_USERNAME/ADMIN_PASSWORD：管理后台接口将一律返回 503"
        )
    elif len(ADMIN_PASSWORD) < 12:
        warnings.append("ADMIN_PASSWORD 长度小于 12，建议改用更长的随机口令")

    return warnings
