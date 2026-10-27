"""
认证路由

提供邮箱验证码登录 + 微信小程序登录接口，新用户自动注册。
"""

import logging
import re
import secrets
import smtplib
import time
import uuid
import threading
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status, Depends
from pydantic import Field

from api.contracts import ApiRequest, ApiResponse, standard_error_responses
from database import get_db, ensure_user_settings
from dependencies import create_access_token, get_current_user
from integrations.github import (
    GitHubAuthorizationRejected,
    GitHubProtocolError,
    get_github_client,
)
from integrations.http import IntegrationHttpError
from integrations.wechat import (
    WeChatAuthorizationRejected,
    WeChatProtocolError,
    get_wechat_client,
)
from utils.log_safe import safe_log
from utils.rate_limit import SlidingWindowLimiter, client_ip
from config import (
    SMTP_HOST,
    SMTP_PORT,
    SMTP_USER,
    SMTP_PASSWORD,
    SMTP_FROM_NAME,
    WECHAT_MP_APPID,
    WECHAT_MP_SECRET,
    GITHUB_CLIENT_ID,
    GITHUB_CLIENT_SECRET,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# --------------------------------------------------------------------------
# 验证码内存存储（单机部署足够，重启后清空）
# --------------------------------------------------------------------------

_verification_codes: dict[str, dict] = {}  # email -> {code, expires_at, attempts}
_codes_lock = threading.Lock()

# 验证码配置
CODE_LENGTH = 6
CODE_EXPIRE_SECONDS = 300  # 5 分钟过期
CODE_COOLDOWN_SECONDS = 60  # 60 秒内不可重发
MAX_VERIFY_ATTEMPTS = 5  # 最多验证 5 次

# 按来源 IP 限流：按邮箱的冷却/次数限制挡不住“换邮箱轰炸”和“换邮箱试验证码”。
# 阈值留有余量，避免校园/公司出口 IP 下的正常用户被误伤。
_send_code_ip_limiter = SlidingWindowLimiter(
    20, 3600, detail="该网络发送验证码过于频繁，请稍后再试"
)
_verify_code_ip_limiter = SlidingWindowLimiter(
    60, 600, detail="该网络验证尝试过多，请稍后再试"
)


def _limit_send_code_by_ip(request: Request) -> None:
    _send_code_ip_limiter.hit(client_ip(request))


def _limit_verify_code_by_ip(request: Request) -> None:
    _verify_code_ip_limiter.hit(client_ip(request))


def _generate_code() -> str:
    """生成 6 位数字验证码（使用密码学安全随机源）。"""
    return "".join(str(secrets.randbelow(10)) for _ in range(CODE_LENGTH))


def _cleanup_expired():
    """清理过期验证码。"""
    now = time.time()
    expired = [
        email for email, data in _verification_codes.items() if data["expires_at"] < now
    ]
    for email in expired:
        del _verification_codes[email]


def _send_email(to_email: str, code: str) -> None:
    """通过 SMTP 发送验证码邮件。"""
    if not all([SMTP_HOST, SMTP_USER, SMTP_PASSWORD]):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="邮件服务未配置，请联系管理员",
        )

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    msg["To"] = to_email
    msg["Subject"] = f"【{SMTP_FROM_NAME}】登录验证码"

    # 纯文本版本
    text_content = f"您的登录验证码是：{code}\n\n验证码 {CODE_EXPIRE_SECONDS // 60} 分钟内有效，请勿泄露给他人。\n\n如非本人操作，请忽略此邮件。"

    # HTML 版本（美观）
    html_content = f"""
    <div style="max-width:480px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
      <div style="background:linear-gradient(135deg,#6366f1,#a855f7);padding:32px 24px;border-radius:16px 16px 0 0;text-align:center;">
        <h1 style="color:#fff;margin:0;font-size:24px;font-weight:700;">{SMTP_FROM_NAME}</h1>
        <p style="color:rgba(255,255,255,0.85);margin:8px 0 0;font-size:14px;">你的专属知识大脑</p>
      </div>
      <div style="background:#fff;padding:32px 24px;border:1px solid #e5e7eb;border-top:none;">
        <p style="color:#374151;font-size:15px;margin:0 0 20px;">您正在登录 {SMTP_FROM_NAME}，验证码如下：</p>
        <div style="background:#f3f4f6;border-radius:12px;padding:20px;text-align:center;margin:0 0 20px;">
          <span style="font-size:36px;font-weight:700;letter-spacing:8px;color:#6366f1;">{code}</span>
        </div>
        <p style="color:#6b7280;font-size:13px;margin:0 0 8px;">⏱ 验证码 <strong>{CODE_EXPIRE_SECONDS // 60} 分钟</strong>内有效</p>
        <p style="color:#6b7280;font-size:13px;margin:0;">🔒 请勿将验证码泄露给他人</p>
      </div>
      <div style="padding:16px 24px;text-align:center;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 16px 16px;background:#f9fafb;">
        <p style="color:#9ca3af;font-size:12px;margin:0;">如非本人操作，请忽略此邮件</p>
      </div>
    </div>
    """

    msg.attach(MIMEText(text_content, "plain", "utf-8"))
    msg.attach(MIMEText(html_content, "html", "utf-8"))

    try:
        if SMTP_PORT == 465:
            # SSL 连接
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            # STARTTLS 连接
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
                server.starttls()
                server.login(SMTP_USER, SMTP_PASSWORD)
                server.send_message(msg)
        # 避免日志注入（CWE-117）
        logger.info("验证码邮件已发送至 %s", safe_log(to_email))
    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP 认证失败，请检查 SMTP_USER 和 SMTP_PASSWORD 配置")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="邮件服务认证失败，请联系管理员",
        )
    except Exception as e:
        logger.error("发送邮件失败: %s", e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="邮件发送失败，请稍后重试",
        )


# --------------------------------------------------------------------------
# 请求/响应模型
# --------------------------------------------------------------------------


class SendCodeRequest(ApiRequest):
    email: str = Field(min_length=3, max_length=320)


class SendCodeResponse(ApiResponse):
    message: str
    cooldown: int = CODE_COOLDOWN_SECONDS  # 告诉前端倒计时秒数


class VerifyCodeRequest(ApiRequest):
    email: str = Field(min_length=3, max_length=320)
    code: str = Field(min_length=1, max_length=16)
    name: str = Field(default="", max_length=80)  # 新用户可选昵称


class LoginResponse(ApiResponse):
    access_token: str
    token_type: str = "bearer"
    user_id: str
    user_name: str
    github_reward: dict | None = None


class WechatMpLoginRequest(ApiRequest):
    # wx.login() 返回的一次性 code，不允许异常大请求体占用认证工作线程。
    code: str = Field(min_length=1, max_length=512)


class GitHubCallbackRequest(ApiRequest):
    state: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")
    code: str = Field(min_length=1, max_length=512)  # GitHub OAuth 回调的 code


# --------------------------------------------------------------------------
# 邮箱验证码接口
# --------------------------------------------------------------------------


@router.post(
    "/send-code",
    response_model=SendCodeResponse,
    dependencies=[Depends(_limit_send_code_by_ip)],
)
def send_code(body: SendCodeRequest):
    """
    发送邮箱验证码。
    - 邮箱格式校验
    - 60 秒冷却期
    - 验证码 5 分钟有效
    """
    email = body.email.strip().lower()

    # 邮箱格式校验
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮箱格式不正确",
        )

    now = time.time()

    with _codes_lock:
        _cleanup_expired()

        # 冷却期检查
        if email in _verification_codes:
            existing = _verification_codes[email]
            sent_at = existing["expires_at"] - CODE_EXPIRE_SECONDS
            elapsed = now - sent_at
            if elapsed < CODE_COOLDOWN_SECONDS:
                remaining = int(CODE_COOLDOWN_SECONDS - elapsed)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"发送过于频繁，请 {remaining} 秒后重试",
                )

        # 生成并存储验证码
        code = _generate_code()
        _verification_codes[email] = {
            "code": code,
            "expires_at": now + CODE_EXPIRE_SECONDS,
            "attempts": 0,
        }

    # 发送邮件
    _send_email(email, code)

    return SendCodeResponse(message="验证码已发送，请查收邮件")


@router.post(
    "/verify-code",
    response_model=LoginResponse,
    dependencies=[Depends(_limit_verify_code_by_ip)],
)
def verify_code(body: VerifyCodeRequest):
    """
    验证邮箱验证码并登录。
    - 邮箱已注册：直接登录
    - 邮箱未注册：自动注册并登录
    """
    email = body.email.strip().lower()
    code = body.code.strip()

    # 校验验证码
    with _codes_lock:
        data = _verification_codes.get(email)
        if not data:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="验证码不存在或已过期，请重新发送",
            )

        # 过期检查
        if time.time() > data["expires_at"]:
            del _verification_codes[email]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="验证码已过期，请重新发送",
            )

        # 尝试次数检查
        data["attempts"] += 1
        if data["attempts"] > MAX_VERIFY_ATTEMPTS:
            del _verification_codes[email]
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="验证次数过多，请重新发送验证码",
            )

        # 验证码匹配
        if not secrets.compare_digest(
            str(data["code"]).encode("utf-8"), code.encode("utf-8")
        ):
            remaining = MAX_VERIFY_ATTEMPTS - data["attempts"]
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"验证码错误，还可尝试 {remaining} 次",
            )

        # 验证成功，删除验证码
        del _verification_codes[email]

    # 查找用户（通过 email）
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name FROM users WHERE email = ?", (email,)
        ).fetchone()

    if row:
        # 已有用户，直接登录
        user_id = row["id"]
        user_name = row["name"]
    else:
        # 新用户，自动注册
        import uuid

        user_id = f"u_{uuid.uuid4().hex[:8]}"
        user_name = body.name.strip() if body.name.strip() else email.split("@")[0]
        now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (id, name, email, password_hash, avatar_url, preferences, about, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (user_id, user_name, email, "", None, "{}", "{}", now_str),
            )

        # 初始化 settings
        ensure_user_settings(user_id)
        # 避免日志注入（CWE-117）
        logger.info("邮箱 %s 自动注册为用户 %s", safe_log(email), safe_log(user_id))

    # 签发 token
    from services.credit_wallet import balance

    balance(user_id)
    token = create_access_token(user_id=user_id)

    return LoginResponse(
        access_token=token,
        user_id=user_id,
        user_name=user_name,
    )


# --------------------------------------------------------------------------
# GitHub OAuth 登录接口
# --------------------------------------------------------------------------


@router.get("/github/authorize")
def github_authorize():
    """
    返回 GitHub OAuth 授权 URL，前端跳转到此 URL 让用户授权。
    """
    from services.github_reward import authorize

    return authorize()


@router.get("/github/reward/authorize")
def github_reward_authorize(user_id: str = Depends(get_current_user)):
    from services.github_reward import authorize

    return authorize(user_id, "reward")


@router.post(
    "/github/callback",
    response_model=LoginResponse,
    operation_id="complete_github_oauth_callback",
    responses=standard_error_responses(400, 502, 503, 422),
)
def github_callback(body: GitHubCallbackRequest):
    """
    GitHub OAuth 回调：用 code 换取 access_token，获取用户信息，完成登录/注册。
    """
    if not GITHUB_CLIENT_ID or not GITHUB_CLIENT_SECRET:
        raise HTTPException(503, detail="GitHub 登录未配置")

    from services.github_reward import consume_state, verify_and_grant, bind_account

    oauth_state = consume_state(body.state)

    github_client = get_github_client()

    # 1. 用单次 code 换取 access_token。该调用禁止自动重试，避免首个
    # 请求已被 GitHub 接受但响应丢失时重复使用一次性 code。
    try:
        access_token = github_client.exchange_code(
            client_id=GITHUB_CLIENT_ID,
            client_secret=GITHUB_CLIENT_SECRET,
            code=body.code,
        )
    except GitHubAuthorizationRejected:
        raise HTTPException(400, detail="GitHub 授权失败，请重新发起授权")
    except GitHubProtocolError as exc:
        logger.warning("GitHub OAuth 响应无效 error_type=%s", type(exc).__name__)
        raise HTTPException(502, detail="GitHub 服务响应异常，请稍后重试")
    except IntegrationHttpError as exc:
        logger.warning(
            "GitHub OAuth 交换未完成 error_type=%s retryable=%s",
            type(exc).__name__,
            exc.retryable,
        )
        raise HTTPException(503, detail="GitHub 服务暂不可用")

    # 2. 用 access_token 获取用户信息
    try:
        user_resp = github_client.current_user(access_token)
    except GitHubProtocolError as exc:
        logger.warning("GitHub 用户响应无效 error_type=%s", type(exc).__name__)
        raise HTTPException(502, detail="GitHub 服务响应异常，请稍后重试")
    except IntegrationHttpError as exc:
        logger.warning(
            "获取 GitHub 用户信息未完成 error_type=%s retryable=%s",
            type(exc).__name__,
            exc.retryable,
        )
        raise HTTPException(503, detail="获取 GitHub 用户信息失败")

    github_id = user_resp["id"]
    github_username = user_resp["login"]
    github_name = user_resp.get("name") or github_username
    github_email = user_resp.get("email")  # 可能为 None
    github_avatar = user_resp.get("avatar_url")

    # 3. 如果邮箱为空，尝试从 /user/emails 获取
    if oauth_state["purpose"] == "reward":
        user_id = oauth_state["user_id"]
        user_name = bind_account(user_id, github_id, github_username, github_avatar)
        reward = verify_and_grant(
            user_id, github_id, access_token, client=github_client
        )
        return LoginResponse(
            access_token=create_access_token(user_id),
            user_id=user_id,
            user_name=user_name,
            github_reward=reward,
        )

    if not github_email:
        try:
            github_email = github_client.verified_email(access_token)
        except IntegrationHttpError as exc:
            logger.warning(
                "获取 GitHub 邮箱失败（非致命） error_type=%s retryable=%s",
                type(exc).__name__,
                exc.retryable,
            )

    # 4. 查找或创建用户
    with get_db() as conn:
        # 先通过 github_id 查找
        row = conn.execute(
            "SELECT id, name FROM users WHERE github_id = ?", (github_id,)
        ).fetchone()

    if row:
        # 已绑定 GitHub 的用户，直接登录
        user_id = row["id"]
        user_name = row["name"]
    else:
        # 尝试通过邮箱匹配已有用户（合并账号）
        if github_email:
            with get_db() as conn:
                row = conn.execute(
                    "SELECT id, name FROM users WHERE email = ?", (github_email,)
                ).fetchone()

        if row:
            # 邮箱匹配到已有用户，绑定 GitHub 信息
            user_id = row["id"]
            user_name = row["name"]
            with get_db() as conn:
                conn.execute(
                    "UPDATE users SET github_id = ?, github_username = ?, avatar_url = COALESCE(avatar_url, ?) WHERE id = ?",
                    (github_id, github_username, github_avatar, user_id),
                )
            logger.info("已有用户 %s 已绑定 GitHub 账户", safe_log(user_id))
        else:
            # 全新用户，自动注册
            user_id = f"u_{uuid.uuid4().hex[:8]}"
            user_name = github_name
            now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

            with get_db() as conn:
                conn.execute(
                    "INSERT INTO users (id, name, email, password_hash, avatar_url, github_id, github_username, preferences, about, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (
                        user_id,
                        user_name,
                        github_email,
                        "",
                        github_avatar,
                        github_id,
                        github_username,
                        "{}",
                        "{}",
                        now_str,
                    ),
                )

            ensure_user_settings(user_id)
            logger.info("GitHub OAuth 用户自动注册为 %s", safe_log(user_id))

    # 5. 签发 JWT
    from services.credit_wallet import balance

    balance(user_id)
    token = create_access_token(user_id=user_id)

    reward = verify_and_grant(user_id, github_id, access_token, client=github_client)
    return LoginResponse(
        access_token=token,
        user_id=user_id,
        user_name=user_name,
        github_reward=reward,
    )


# --------------------------------------------------------------------------
# 微信小程序登录接口
# --------------------------------------------------------------------------


@router.post(
    "/wechat/mp-login",
    response_model=LoginResponse,
    operation_id="login_with_wechat_mini_program",
    responses=standard_error_responses(400, 502, 503, 422),
)
def wechat_mp_login(body: WechatMpLoginRequest):
    """
    小程序端调用：用 wx.login() 的 code 完成登录。
    1. 用 code 调用微信 jscode2session 接口换取 openid
    2. 查找/创建用户
    3. 返回 JWT token
    """
    if not WECHAT_MP_APPID or not WECHAT_MP_SECRET:
        raise HTTPException(503, detail="微信登录未配置")

    # 1. code 换 openid。微信 js_code 为临时一次性凭据，禁止自动重试。
    try:
        openid = get_wechat_client().exchange_code(
            app_id=WECHAT_MP_APPID,
            app_secret=WECHAT_MP_SECRET,
            code=body.code,
        )
    except WeChatAuthorizationRejected:
        raise HTTPException(400, detail="微信登录失败，请重新获取登录凭据")
    except WeChatProtocolError as exc:
        logger.warning("微信登录响应无效 error_type=%s", type(exc).__name__)
        raise HTTPException(502, detail="微信服务响应异常，请稍后重试")
    except IntegrationHttpError as exc:
        logger.warning(
            "调用微信登录未完成 error_type=%s retryable=%s",
            type(exc).__name__,
            exc.retryable,
        )
        raise HTTPException(503, detail="微信服务暂不可用")

    # 2. 查找或创建用户
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, name FROM users WHERE wechat_openid = ?", (openid,)
        ).fetchone()

    if row:
        user_id = row["id"]
        user_name = row["name"]
    else:
        # 新用户，自动注册
        user_id = f"u_{uuid.uuid4().hex}"
        user_name = "微信用户"
        now_str = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        with get_db() as conn:
            conn.execute(
                "INSERT INTO users (id, name, email, password_hash, avatar_url, wechat_openid, preferences, about, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (user_id, user_name, None, "", None, openid, "{}", "{}", now_str),
            )

        ensure_user_settings(user_id)
        logger.info("微信用户自动注册为 %s", safe_log(user_id))

    # 3. 签发 JWT
    from services.credit_wallet import balance

    balance(user_id)
    token = create_access_token(user_id=user_id)

    return LoginResponse(
        access_token=token,
        user_id=user_id,
        user_name=user_name,
    )
