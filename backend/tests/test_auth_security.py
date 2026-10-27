"""认证信任根与 admin 鉴权的回归测试。

覆盖漏洞报告中的关键路径：
- 历史公开默认密钥不能再用（启动直接失败）；
- 未配置/弱密钥不会静默回退；
- 用户 token 与 admin token 不能互相越权；
- 未配置管理员账号时 admin 接口一律拒绝；
- admin 口令轮换后旧 token 立即失效；
- default 用户不再携带公开口令。
"""

from __future__ import annotations

import bcrypt
import os
import secrets
import sqlite3
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import jwt  # noqa: E402
from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

import database  # noqa: E402
from config import JWT_SECRET  # noqa: E402
from dependencies import create_access_token, get_current_user  # noqa: E402
from utils import admin_auth  # noqa: E402
from utils.jwt_secret import (  # noqa: E402
    InsecureJWTSecretError,
    load_jwt_secret,
    validate_jwt_secret,
)
from utils.jwt_tokens import (  # noqa: E402
    ADMIN_TOKEN_AUDIENCE,
    JWT_ISSUER,
    USER_TOKEN_AUDIENCE,
    derive_signing_key,
    encode_token,
)

LEGACY_SECRETS = (
    "change-me-in-production",
    "wesmartflow-dev-secret-change-in-production",
)


class JWTSecretTests(unittest.TestCase):
    def test_public_placeholder_secrets_are_rejected(self):
        for secret in LEGACY_SECRETS + ("secret", "please-change-me"):
            with self.subTest(secret=secret):
                with self.assertRaises(InsecureJWTSecretError):
                    validate_jwt_secret(secret)

    def test_weak_or_low_entropy_secrets_are_rejected(self):
        for secret in ("short", "a" * 64, "ab" * 32):
            with self.subTest(secret=secret):
                with self.assertRaises(InsecureJWTSecretError):
                    validate_jwt_secret(secret)

    def test_strong_explicit_secret_is_used(self):
        secret = secrets.token_urlsafe(48)
        loaded, source = load_jwt_secret(secret, Path("/nonexistent/ignored"))
        self.assertEqual(loaded, secret)
        self.assertEqual(source, "environment")

    def test_missing_secret_generates_private_persistent_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data" / "jwt_secret.key"
            first, source = load_jwt_secret(None, path)
            self.assertEqual(source, "generated")
            self.assertGreaterEqual(len(first), 32)
            self.assertTrue(path.exists())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode) & 0o077, 0)

            second, _ = load_jwt_secret("", path)
            self.assertEqual(first, second)

    def test_tampered_secret_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "jwt_secret.key"
            path.write_text("change-me-in-production", encoding="utf-8")
            with self.assertRaises(InsecureJWTSecretError):
                load_jwt_secret(None, path)

    def test_config_refuses_to_start_with_public_default(self):
        env = dict(os.environ)
        env["JWT_SECRET"] = "change-me-in-production"
        result = subprocess.run(
            [sys.executable, "-c", "import config"],
            cwd=str(BACKEND_DIR),
            env=env,
            capture_output=True,
            text=True,
            timeout=120,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("公开占位符", result.stderr)


class TokenScopeTests(unittest.TestCase):
    def setUp(self):
        self.app = FastAPI()

        @self.app.get("/user")
        def user_route(user_id: str = Depends(get_current_user)):
            return {"user_id": user_id}

        @self.app.get("/admin")
        def admin_route(_: str = Depends(admin_auth.require_admin)):
            return {"role": "admin"}

        self.client = TestClient(self.app)
        self.patches = [
            patch.object(admin_auth, "ADMIN_USERNAME", "admin"),
            patch.object(admin_auth, "ADMIN_PASSWORD", "test-admin-password"),
            patch.object(admin_auth, "JWT_SECRET", JWT_SECRET),
        ]
        for item in self.patches:
            item.start()

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()

    @staticmethod
    def headers(token: str) -> dict:
        return {"Authorization": "Bearer " + token}

    def test_user_token_cannot_access_admin_api(self):
        token = create_access_token("default")
        self.assertEqual(
            self.client.get("/user", headers=self.headers(token)).status_code, 200
        )
        self.assertEqual(
            self.client.get("/admin", headers=self.headers(token)).status_code, 401
        )

    def test_admin_token_cannot_access_user_api(self):
        token = admin_auth.create_admin_token()
        self.assertEqual(
            self.client.get("/admin", headers=self.headers(token)).status_code, 200
        )
        self.assertEqual(
            self.client.get("/user", headers=self.headers(token)).status_code, 401
        )

    def test_legacy_public_secret_forgery_is_rejected(self):
        now = int(time.time())
        for audience, path, extra in (
            (USER_TOKEN_AUDIENCE, "/user", {}),
            (
                ADMIN_TOKEN_AUDIENCE,
                "/admin",
                {"role": "admin", "cred": "forged"},
            ),
        ):
            payload = {
                "sub": "admin" if audience == ADMIN_TOKEN_AUDIENCE else "default",
                "iss": JWT_ISSUER,
                "aud": audience,
                "iat": now,
                "exp": now + 3600,
                **extra,
            }
            for legacy in LEGACY_SECRETS:
                with self.subTest(audience=audience, legacy=legacy):
                    token = jwt.encode(payload, legacy, algorithm="HS256")
                    self.assertEqual(
                        self.client.get(path, headers=self.headers(token)).status_code,
                        401,
                    )

    def test_raw_master_secret_is_not_a_signing_key(self):
        now = int(time.time())
        payload = {
            "sub": "default",
            "iss": JWT_ISSUER,
            "aud": USER_TOKEN_AUDIENCE,
            "iat": now,
            "exp": now + 3600,
        }
        token = jwt.encode(payload, JWT_SECRET, algorithm="HS256")
        self.assertEqual(
            self.client.get("/user", headers=self.headers(token)).status_code, 401
        )

    def test_missing_or_wrong_audience_is_rejected(self):
        now = int(time.time())
        key = derive_signing_key(JWT_SECRET, USER_TOKEN_AUDIENCE)
        for payload in (
            {"sub": "default", "iss": JWT_ISSUER, "iat": now, "exp": now + 3600},
            {
                "sub": "default",
                "iss": JWT_ISSUER,
                "aud": "someone-else",
                "iat": now,
                "exp": now + 3600,
            },
        ):
            token = jwt.encode(payload, key, algorithm="HS256")
            self.assertEqual(
                self.client.get("/user", headers=self.headers(token)).status_code, 401
            )

    def test_admin_api_is_disabled_without_configured_credentials(self):
        token = encode_token(
            subject="admin",
            audience=ADMIN_TOKEN_AUDIENCE,
            master_secret=JWT_SECRET,
            expires_in_hours=1,
            extra_claims={"role": "admin", "cred": "anything"},
        )
        with (
            patch.object(admin_auth, "ADMIN_USERNAME", ""),
            patch.object(admin_auth, "ADMIN_PASSWORD", ""),
        ):
            response = self.client.get("/admin", headers=self.headers(token))
        self.assertEqual(response.status_code, 503)

    def test_admin_token_is_invalidated_by_password_rotation(self):
        token = admin_auth.create_admin_token()
        self.assertEqual(
            self.client.get("/admin", headers=self.headers(token)).status_code, 200
        )
        with patch.object(admin_auth, "ADMIN_PASSWORD", "rotated-password-123"):
            response = self.client.get("/admin", headers=self.headers(token))
        self.assertEqual(response.status_code, 401)

    def test_admin_claims_without_credential_binding_are_rejected(self):
        token = encode_token(
            subject="admin",
            audience=ADMIN_TOKEN_AUDIENCE,
            master_secret=JWT_SECRET,
            expires_in_hours=1,
            extra_claims={"role": "admin"},
        )
        self.assertEqual(
            self.client.get("/admin", headers=self.headers(token)).status_code, 401
        )


class PlatformCredentialIsolationTests(unittest.TestCase):
    """平台图像 Key 只能发往平台 Base URL，不能被用户设置重定向。"""

    PLATFORM_ENV = {
        "IMG_API_KEY": "platform-image-key",
        "IMG_BASE_URL": "https://platform.example/v1",
    }

    def _read(self, settings: dict) -> dict:
        from services import image_factory

        with (
            patch.dict(os.environ, self.PLATFORM_ENV),
            patch("database.get_setting", lambda _uid, key: settings.get(key, "")),
        ):
            return image_factory._read_config("user")

    def test_user_base_url_without_own_key_cannot_redirect_platform_key(self):
        cfg = self._read({"img_base_url": "https://attacker.example/v1"})
        self.assertEqual(cfg["api_key"], "platform-image-key")
        self.assertEqual(cfg["base_url"], "https://platform.example/v1")

    def test_user_key_and_base_url_are_used_together(self):
        cfg = self._read(
            {"img_api_key": "user-key", "img_base_url": "https://user.example/v1"}
        )
        self.assertEqual(cfg["api_key"], "user-key")
        self.assertEqual(cfg["base_url"], "https://user.example/v1")

    def test_platform_config_used_when_user_has_no_settings(self):
        cfg = self._read({})
        self.assertEqual(cfg["api_key"], "platform-image-key")
        self.assertEqual(cfg["base_url"], "https://platform.example/v1")


class VerificationCodeTests(unittest.TestCase):
    def test_code_is_six_digits_from_csprng(self):
        from routers import auth

        for _ in range(50):
            code = auth._generate_code()
            self.assertRegex(code, r"^\d{6}$")
        self.assertFalse(hasattr(auth, "random"))


class FileTicketTests(unittest.TestCase):
    """URL/Cookie 里只允许单文档短时效票据，登录 token 不得出现在 URL。"""

    def setUp(self):
        from utils.web_auth import COOKIE_NAME, get_user_from_request_flexible

        self.cookie_name = COOKIE_NAME
        app = FastAPI()

        @app.get("/doc/{doc_id}")
        def doc(doc_id: str, request: Request):
            user_id, ticket = get_user_from_request_flexible(request, doc_id)
            return {"user_id": user_id, "from_query": bool(ticket)}

        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_ticket_grants_access_to_its_document_only(self):
        from utils.file_ticket import create_file_ticket

        ticket = create_file_ticket("u1", "doc-a")
        ok = self.client.get(f"/doc/doc-a?ticket={ticket}")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["user_id"], "u1")
        self.assertEqual(
            self.client.get(f"/doc/doc-b?ticket={ticket}").status_code, 401
        )

    def test_login_token_in_url_or_cookie_is_rejected(self):
        login = create_access_token("u1")
        self.assertEqual(self.client.get(f"/doc/doc-a?token={login}").status_code, 401)
        self.assertEqual(self.client.get(f"/doc/doc-a?ticket={login}").status_code, 401)
        self.client.cookies.set(self.cookie_name, login)
        self.assertEqual(self.client.get("/doc/doc-a").status_code, 401)

    def test_ticket_cannot_be_used_as_login_token(self):
        from utils.file_ticket import create_file_ticket

        ticket = create_file_ticket("u1", "doc-a")
        app = FastAPI()

        @app.get("/me")
        def me(user_id: str = Depends(get_current_user)):
            return {"user_id": user_id}

        with TestClient(app) as client:
            response = client.get("/me", headers={"Authorization": "Bearer " + ticket})
        self.assertEqual(response.status_code, 401)

    def test_expired_ticket_is_rejected(self):
        from utils.file_ticket import create_file_ticket

        ticket = create_file_ticket("u1", "doc-a", expires_in_minutes=1)
        with patch(
            "jwt.api_jwt.PyJWT._validate_exp", side_effect=jwt.ExpiredSignatureError
        ):
            response = self.client.get(f"/doc/doc-a?ticket={ticket}")
        self.assertEqual(response.status_code, 401)

    def test_bearer_login_token_still_works(self):
        login = create_access_token("u1")
        response = self.client.get(
            "/doc/doc-a", headers={"Authorization": "Bearer " + login}
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["from_query"])

    def test_wechat_links_carry_ticket_not_login_token(self):
        from channels import bridge

        url = bridge._build_asset_url("doc-a", "u1", download=False)
        self.assertIn("?ticket=", url)
        self.assertNotIn("token=", url)
        ticket = url.split("ticket=")[1].split("&")[0]
        from utils.file_ticket import verify_file_ticket

        self.assertEqual(verify_file_ticket(ticket, "doc-a"), "u1")
        with self.assertRaises(jwt.InvalidTokenError):
            verify_file_ticket(ticket, "doc-b")


class RateLimitTests(unittest.TestCase):
    def test_sliding_window_blocks_after_limit(self):
        from fastapi import HTTPException

        from utils.rate_limit import SlidingWindowLimiter

        limiter = SlidingWindowLimiter(3, 60, detail="too many")
        for _ in range(3):
            limiter.hit("1.2.3.4")
        with self.assertRaises(HTTPException) as ctx:
            limiter.hit("1.2.3.4")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Retry-After", ctx.exception.headers)
        limiter.hit("5.6.7.8")  # 其它来源不受影响

    def test_failure_lockout_and_success_reset(self):
        from fastapi import HTTPException

        from utils.rate_limit import FailureLockout

        lock = FailureLockout(3, 60, 60, detail="locked")
        for _ in range(2):
            lock.record_failure("ip")
        lock.check("ip")
        lock.record_success("ip")
        for _ in range(3):
            lock.record_failure("ip")
        with self.assertRaises(HTTPException) as ctx:
            lock.check("ip")
        self.assertEqual(ctx.exception.status_code, 429)

    def test_admin_login_locks_out_even_with_correct_password(self):
        from routers import admin

        app = FastAPI()
        app.include_router(admin.router)
        admin._ip_lockout.reset()
        admin._global_lockout.reset()
        try:
            with (
                patch.object(admin_auth, "ADMIN_USERNAME", "admin"),
                patch.object(admin_auth, "ADMIN_PASSWORD", "correct-horse-battery"),
                patch.object(admin, "admin_credentials_configured", lambda: True),
                patch.object(
                    admin,
                    "verify_admin_credentials",
                    admin_auth.verify_admin_credentials,
                ),
                TestClient(app) as client,
            ):
                for _ in range(5):
                    r = client.post(
                        "/api/admin/login",
                        json={"username": "admin", "password": "bad"},
                    )
                    self.assertEqual(r.status_code, 401)
                locked = client.post(
                    "/api/admin/login",
                    json={"username": "admin", "password": "correct-horse-battery"},
                )
                self.assertEqual(locked.status_code, 429)
        finally:
            admin._ip_lockout.reset()
            admin._global_lockout.reset()

    def test_send_code_is_limited_per_ip(self):
        from routers import auth

        auth._send_code_ip_limiter.reset()
        app = FastAPI()
        app.include_router(auth.router)
        try:
            with (
                patch.object(auth, "_send_email", lambda *_: None),
                TestClient(app) as client,
            ):
                statuses = [
                    client.post(
                        "/api/auth/send-code", json={"email": f"user{i}@example.com"}
                    ).status_code
                    for i in range(22)
                ]
            self.assertEqual(statuses[:20], [200] * 20)
            self.assertEqual(statuses[20:], [429, 429])
        finally:
            auth._send_code_ip_limiter.reset()
            auth._verification_codes.clear()


class DefaultUserPasswordTests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript(database._CREATE_TABLES_SQL)

    def tearDown(self):
        self.conn.close()

    def test_new_default_user_has_empty_password(self):
        database._ensure_default_user(self.conn)
        row = self.conn.execute(
            "SELECT password_hash FROM users WHERE id='default'"
        ).fetchone()
        self.assertEqual(row[0], "")

    def test_legacy_default_password_is_cleared(self):
        legacy_hash = bcrypt.hashpw(
            database.LEGACY_DEFAULT_PASSWORD.encode("utf-8"), bcrypt.gensalt()
        ).decode("utf-8")
        self.conn.execute(
            "INSERT INTO users (id,name,password_hash,created_at) VALUES ('default','默认用户',?,'2026-01-01')",
            (legacy_hash,),
        )
        database._ensure_default_user(self.conn)
        row = self.conn.execute(
            "SELECT password_hash FROM users WHERE id='default'"
        ).fetchone()
        self.assertEqual(row[0], "")


if __name__ == "__main__":
    unittest.main()
