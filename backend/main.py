"""
WeSmartFlow Backend
FastAPI 应用入口
"""

import logging
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import BACKEND_HOST, BACKEND_PORT, CORS_ORIGINS, DATA_DIR
from database import init_db
from routers.nodes import router as nodes_router
from routers.sessions import router as sessions_router
from routers.documents import router as documents_router
from routers.quiz import router as quiz_router
from routers.users import router as user_router
from routers.brief import router as brief_router
from routers.immersive import router as immersive_router
from routers.settings import router as settings_router
from routers.auth import router as auth_router
from routers.cards import router as cards_router
from routers.usage import router as usage_router

from services.quota import QuotaExceededError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)

# --------------------------------------------------------------------------
# 应用初始化
# --------------------------------------------------------------------------

app = FastAPI(
    title="WeSmartFlow API",
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

app.include_router(auth_router)
app.include_router(nodes_router)
app.include_router(sessions_router)
app.include_router(documents_router)
app.include_router(quiz_router)
app.include_router(user_router)
app.include_router(brief_router)
app.include_router(settings_router)
app.include_router(immersive_router)
app.include_router(cards_router)
app.include_router(usage_router)

# --------------------------------------------------------------------------
# 全局异常处理：额度超限返回 429
# --------------------------------------------------------------------------


@app.exception_handler(QuotaExceededError)
async def quota_exceeded_handler(request: Request, exc: QuotaExceededError):
    return JSONResponse(
        status_code=429,
        content={
            "detail": str(exc),
            "category": exc.category,
            "limit": exc.limit,
        },
    )


# 静态文件：资产归档目录（先不动）
_assets_dir = DATA_DIR / "assets"
_assets_dir.mkdir(parents=True, exist_ok=True)
# app.mount("/files/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


# --------------------------------------------------------------------------
# 生命周期
# --------------------------------------------------------------------------


@app.on_event("startup")
def on_startup():
    init_db()
    logging.getLogger(__name__).info("WeSmartFlow 后端已启动，数据库初始化完成")


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
