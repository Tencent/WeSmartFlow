"""
AscendFlow Backend
FastAPI 应用入口
"""

import sys
from pathlib import Path

# 将 agent_core 路径加入模块搜索
sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))

import logging
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import BACKEND_HOST, BACKEND_PORT, CORS_ORIGINS, DATA_DIR
from database import init_db
from routers.nodes import router as nodes_router
from routers.sessions import router as sessions_router
from routers.documents import router as documents_router
from routers.quiz_user import quiz_router, user_router, brief_router
from routers.immersive import router as immersive_router
from routers.settings import router as settings_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

# --------------------------------------------------------------------------
# 应用初始化
# --------------------------------------------------------------------------

app = FastAPI(
    title="AscendFlow API",
    description="AI 学习助手后端",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------
# 路由注册
# --------------------------------------------------------------------------

app.include_router(nodes_router)
app.include_router(sessions_router)
app.include_router(documents_router)
app.include_router(quiz_router)
app.include_router(user_router)
app.include_router(brief_router)
app.include_router(settings_router)
app.include_router(immersive_router)

# 静态文件：生成的 PDF 卡片
_cards_dir = DATA_DIR / "generated_cards"
_cards_dir.mkdir(parents=True, exist_ok=True)
app.mount("/files/cards", StaticFiles(directory=str(_cards_dir)), name="cards")

# 静态文件：资产归档目录
_assets_dir = DATA_DIR / "assets"
_assets_dir.mkdir(parents=True, exist_ok=True)
app.mount("/files/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


# --------------------------------------------------------------------------
# 生命周期
# --------------------------------------------------------------------------


@app.on_event("startup")
def on_startup():
    init_db()
    logging.getLogger(__name__).info("AscendFlow 后端已启动，数据库初始化完成")


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------
# 启动入口
# --------------------------------------------------------------------------

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        reload=True,
        log_level="info",
    )
