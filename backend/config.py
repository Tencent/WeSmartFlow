"""
WeSmartFlow 后端配置
"""

from pathlib import Path
import os
from dotenv import load_dotenv

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

# 默认指向 SimplePlus-BeamerTheme 主题目录
TEX_TEMPLATE_DIR = Path(
    os.getenv("TEX_TEMPLATE_DIR", str(Path(__file__).parent / "SimplePlus-BeamerTheme"))
)

# 日志目录
LOG_DIR = DATA_DIR / "logs"

# SQLite 数据库
DB_PATH = DATA_DIR / "wesmartflow.db"

# JWT 配置
JWT_SECRET = os.getenv("JWT_SECRET", "wesmartflow-dev-secret-change-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = int(os.getenv("JWT_EXPIRE_HOURS", "72"))

# 免费额度配置（每用户总量，使用平台公共 Key 时生效）
# 注意：额度按实际 API 调用次数计数（一次对话可能触发多次 LLM 调用）
# 10¥ ≈ $1.37 预算，按 6:3:1 分配
FREE_LLM_TOTAL = int(os.getenv("FREE_LLM_TOTAL", "100"))  # LLM 调用总次数
FREE_SEARCH_TOTAL = int(os.getenv("FREE_SEARCH_TOTAL", "30"))  # 搜索总次数
FREE_IMAGE_TOTAL = int(os.getenv("FREE_IMAGE_TOTAL", "15"))  # 图片生成总次数

# SMTP 邮件配置（用于邮箱验证码登录）
SMTP_HOST = os.getenv("SMTP_HOST", "")  # SMTP 服务器地址，如 smtp.qq.com
SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))  # SMTP 端口，SSL 通常为 465
SMTP_USER = os.getenv("SMTP_USER", "")  # 发件邮箱地址
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")  # SMTP 授权码（非邮箱密码）
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "WeSmartFlow")  # 发件人显示名称

# 微信小程序配置（扫码登录）
WECHAT_MP_APPID = os.getenv("WECHAT_MP_APPID", "")  # 小程序 AppID
WECHAT_MP_SECRET = os.getenv("WECHAT_MP_SECRET", "")  # 小程序 AppSecret

# GitHub OAuth 配置
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")

# 服务配置
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8080"))
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS", "http://localhost:5174,http://localhost:5173"
).split(",")

# 文件上传限制
MAX_UPLOAD_SIZE_MB = 50
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
