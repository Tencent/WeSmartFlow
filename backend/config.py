"""
AscendFlow 后端配置
"""

from pathlib import Path
import os

# 尝试加载 .env 文件（可选，没有 dotenv 也不崩）
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).parent.parent / ".env")
except ImportError:
    pass

# 项目根目录（backend/ 的父目录）
ROOT_DIR = Path(__file__).parent.parent

# 数据目录
DATA_DIR = ROOT_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
SESSIONS_DIR = DATA_DIR / "sessions"
GENERATED_DIR = CARDS_DIR = DATA_DIR / "generated_cards"

# SQLite 数据库
DB_PATH = DATA_DIR / "ascendflow.db"

# LLM 配置（从环境变量读取）
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "")
LLM_MODEL = os.getenv("LLM_MODEL", "")

# 服务配置
BACKEND_HOST = os.getenv("BACKEND_HOST", "0.0.0.0")
BACKEND_PORT = int(os.getenv("BACKEND_PORT", "8000"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

# 文件上传限制
MAX_UPLOAD_SIZE_MB = 50
ALLOWED_EXTENSIONS = {".pdf", ".txt", ".md", ".docx"}

# 确保数据目录存在
for _dir in [DATA_DIR, UPLOADS_DIR, SESSIONS_DIR, GENERATED_DIR, CARDS_DIR]:
    _dir.mkdir(parents=True, exist_ok=True)
