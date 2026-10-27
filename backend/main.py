"""
WeSmartFlow Backend
FastAPI 应用入口
"""

import logging
from pathlib import Path
import logging.handlers
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import (
    BACKEND_HOST,
    BACKEND_PORT,
    CORS_ORIGINS,
    DATA_DIR,
    LOG_DIR,
    security_warnings,
)
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
from routers.admin import router as admin_router
from routers.admin_users import router as admin_users_router
from routers.weclaw import router as weclaw_router
from routers.court import router as court_router
from routers.examples import router as examples_router
from routers.backup import router as backup_router
from routers.graph import router as graph_router
from routers.learning_map import router as learning_map_router
from routers.v1.jobs import router as jobs_v1_router

from services.credit_quota import CreditsExceeded
from api import install_api_foundation, problem_response
from api.request_context import RequestContextLogFilter

# --------------------------------------------------------------------------
# 日志配置：控制台 + 按天轮转文件
# --------------------------------------------------------------------------

_LOG_FORMAT = (
    "%(asctime)s [%(levelname)s] %(name)s request_id=%(request_id)s - %(message)s"
)
_LOG_LEVEL = logging.INFO

# 根 logger（防止 reload 模式下重复添加 handler）
_root_logger = logging.getLogger()
_root_logger.setLevel(_LOG_LEVEL)

if not _root_logger.handlers:
    # 控制台 Handler
    _console_handler = logging.StreamHandler()
    _console_handler.setLevel(_LOG_LEVEL)
    _console_handler.addFilter(RequestContextLogFilter())
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
    _file_handler.addFilter(RequestContextLogFilter())
    _file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    _root_logger.addHandler(_file_handler)

# --------------------------------------------------------------------------
# 应用初始化
# --------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI):
    on_startup()
    await on_startup_weclaw()
    try:
        yield
    finally:
        await on_shutdown()


app = FastAPI(
    title="WeSmartFlow API",
    description="AI 学习助手后端",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)

# HTTP 的 request ID、统一错误结构和 OpenAPI 契约从这里集中装配。
# 必须在 CORS 之后注册，使它成为最外层 middleware，连 OPTIONS 预检
# 响应也能携带关联 ID。
install_api_foundation(app)


# demo 路径强制 no-cache（迭代频繁，避免浏览器缓存住旧版本）
@app.middleware("http")
async def _no_cache_living_history(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/living-history/") or path == "/living-history":
        response.headers["Cache-Control"] = (
            "no-store, no-cache, must-revalidate, max-age=0"
        )
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


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
app.include_router(admin_router)
app.include_router(admin_users_router)
app.include_router(weclaw_router)
app.include_router(court_router)
app.include_router(examples_router)
app.include_router(backup_router)
app.include_router(graph_router)
app.include_router(learning_map_router)
app.include_router(jobs_v1_router)


# --------------------------------------------------------------------------
# 全局异常处理：额度超限统一为标准 ProblemDetails
# --------------------------------------------------------------------------


@app.exception_handler(CreditsExceeded)
async def credits_exceeded_handler(_request, exc: CreditsExceeded):
    return problem_response(
        status=429,
        code="credits_exceeded",
        title="可用积分不足",
        detail=str(exc),
        retryable=False,
        extensions={"quota": exc.quota, "used": exc.used},
    )


# 静态文件：资产归档目录（先不动）
_assets_dir = DATA_DIR / "assets"
_assets_dir.mkdir(parents=True, exist_ok=True)
# app.mount("/files/assets", StaticFiles(directory=str(_assets_dir)), name="assets")


# --------------------------------------------------------------------------
# 生命周期
# --------------------------------------------------------------------------


def on_startup():
    init_db()
    init_kg_db()
    log = logging.getLogger(__name__)
    log.info("WeSmartFlow 后端已启动，主库 + KG 库初始化完成")

    # 认证信任根相关提示：弱密钥在 config 导入阶段已直接拒绝，这里只提示
    # 自动生成密钥、非回环监听、admin 未配置等需要运维知情的状态。
    for warning in security_warnings():
        log.warning("安全配置：%s", warning)

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

    # 启动 proposal 异步落盘 worker（admin approve 后调 MdAuthor 写 OKF .md）
    try:
        from services.apply_worker import start_apply_worker

        start_apply_worker()
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("启动 apply_worker 失败: %s", exc)

    # 清理 data/documents/courses 下的孤儿课程目录（无 outline.json 或无对应 session）
    try:
        from services.immersive.persistence import cleanup_orphan_course_dirs

        cleanup_orphan_course_dirs()
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("启动时清理孤儿课程目录失败: %s", exc)


async def on_startup_weclaw():
    """启动 weclaw 微信通道（多租户长轮询协程）。默认关闭，由 WECLAW_ENABLED 控制。"""
    from config import WECLAW_ENABLED

    if not WECLAW_ENABLED:
        return
    log = logging.getLogger(__name__)
    try:
        from channels.manager import manager as weclaw_manager

        await weclaw_manager.start()
        log.info("weclaw 微信通道已启动")
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("启动 weclaw 微信通道失败: %s", exc)


async def on_shutdown():
    log = logging.getLogger(__name__)

    # 关闭 weclaw 微信通道
    try:
        from config import WECLAW_ENABLED

        if WECLAW_ENABLED:
            from channels.manager import manager as weclaw_manager

            await weclaw_manager.stop()
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("关闭 weclaw 微信通道失败: %s", exc)

    # 关闭 apply_worker（避免事件循环关闭时 task 被强行取消的告警）
    try:
        from services.apply_worker import stop_apply_worker

        await stop_apply_worker()
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("关闭 apply_worker 失败: %s", exc)

    # 关闭 KG 后台周期任务，避免事件循环关闭时出现 task 被强行取消的告警
    try:
        from services.kg_background import stop_kg_background_loops

        await stop_kg_background_loops()
    except Exception as exc:  # pylint: disable=broad-except
        log.warning("关闭 KG 后台周期任务失败: %s", exc)


@app.get("/health")
def health():
    return {"status": "ok"}


# --------------------------------------------------------------------------
# 生产部署：挂载前端静态产物（存在 frontend/dist 时，同源服务页面与 /api）
# 开发模式下 dist 不存在，走 vite dev server（5173）+ /api 代理，互不影响
# --------------------------------------------------------------------------

_FRONTEND_DIST = os.environ.get("FRONTEND_DIST") or str(
    Path(__file__).resolve().parents[1] / "frontend" / "dist"
)
# 运行时图片库（live_science 模式：<img src="/court-assets/X.jpg"> 浏览器原生加载）
COURT_ASSETS_DIR = Path(__file__).parent / "court" / ".assets"
COURT_ASSETS_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/court-assets", StaticFiles(directory=str(COURT_ASSETS_DIR)), name="court-assets"
)

if os.path.isdir(_FRONTEND_DIST):
    app.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="frontend")
    print(f"[deploy] 已挂载前端静态产物: {_FRONTEND_DIST}")


# --------------------------------------------------------------------------
# 启动入口
# --------------------------------------------------------------------------

if __name__ == "__main__":
    # Long-running generation must not be killed by WatchFiles in deployment.
    # Local contributors can opt in with WESMARTFLOW_RELOAD=true.
    reload_enabled = os.environ.get("WESMARTFLOW_RELOAD", "").lower() in {
        "1",
        "true",
        "yes",
    }
    uvicorn.run(
        "main:app",
        host=BACKEND_HOST,
        port=BACKEND_PORT,
        reload=reload_enabled,
        log_level="info",
    )
