"""
WeSmartFlow Backend
FastAPI 应用入口
"""

import logging
import logging.handlers

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from config import BACKEND_HOST, BACKEND_PORT, CORS_ORIGINS, DATA_DIR, LOG_DIR
from database import init_db
from kg import init_kg_db
from routers.nodes import router as nodes_router
from routers.sessions import router as sessions_router
from routers.documents import router as documents_router
from routers.quiz import router as quiz_router
from routers.users import router as user_router
from routers.brief import router as brief_router
from routers.immersive import router as immersive_router
from routers.settings import router as settings_router
from routers.auth import router as auth_router
from routers.cards import gen_router as cards_gen_router
from routers.usage import router as usage_router
from routers.viz import router as viz_router
from routers.llm import router as llm_router

from services.quota import QuotaExceededError

# --------------------------------------------------------------------------
# 日志配置：控制台 + 按天轮转文件
# --------------------------------------------------------------------------

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s - %(message)s"
_LOG_LEVEL = logging.INFO

# 根 logger（防止 reload 模式下重复添加 handler）
_root_logger = logging.getLogger()
_root_logger.setLevel(_LOG_LEVEL)

if not _root_logger.handlers:
    # 控制台 Handler
    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(_LOG_LEVEL)
    _console_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    _root_logger.addHandler(_console_handler)

    # 文件 Handler：按天轮转，保留 30 天，UTF-8 编码
    _file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=str(LOG_DIR / "app.log"),
        when="midnight",  # 每天午夜轮转
        interval=1,  # 每 1 天
        backupCount=30,  # 保留最近 30 天的日志
        encoding="utf-8",
    )
    _file_handler.suffix = "%Y-%m-%d"  # 轮转后文件名后缀：app.log.2026-06-01
    _file_handler.setLevel(_LOG_LEVEL)
    _file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    _root_logger.addHandler(_file_handler)

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
app.include_router(cards_gen_router)
app.include_router(usage_router)
app.include_router(viz_router)
app.include_router(llm_router)

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
    init_kg_db()
    log = logging.getLogger(__name__)
    log.info("WeSmartFlow 后端已启动，主库 + KG 库初始化完成")

    # 注："document → KG exhibit 自动登记"钩子已废弃。
    # KG 反馈闭环模型(最小形态):
    #   - 教学 Agent 通过 kg_facade.agent_record_observation 写入对用户的观察
    #     聚合器周期按 (concept_id, observation_type) 分桶 → LLM 归纳出共性 →
    #     产 suggest_facet_pattern proposal（pending），等管理员人审落 facet
    #   - 教学 Agent 通过 kg_facade.agent_propose_missing_concept 提议「KG 缺概念」
    #     直接产 suggest_missing_concept proposal（pending），等管理员处理
    # document 不再与 KG 直接耦合;教学 Agent 也不再有 add_facet / add_edge 直写工具。

    # 启动后台 KG 周期任务:
    #  - aggregator loop: observation → 共性归纳 → suggest_facet_pattern proposal
    try:
        from services.kg_background import start_kg_background_loops

        start_kg_background_loops()
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("启动 KG 后台周期任务失败: %s", exc)

    # 清理 data/documents/courses 下的孤儿课程目录（无 outline.json 或无对应 session）
    try:
        from services.immersive.persistence import cleanup_orphan_course_dirs

        cleanup_orphan_course_dirs()
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("启动时清理孤儿课程目录失败: %s", exc)


@app.on_event("shutdown")
async def on_shutdown():
    # 关闭 KG 后台周期任务，避免事件循环关闭时出现 task 被强行取消的告警
    try:
        from services.kg_background import stop_kg_background_loops

        await stop_kg_background_loops()
    except Exception as exc:  # pylint: disable=broad-except
        log = logging.getLogger(__name__)
        log.warning("关闭 KG 后台周期任务失败: %s", exc)


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
