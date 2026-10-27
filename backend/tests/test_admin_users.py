"""Admin read views: authorization, field boundaries, filtering and zero writes."""

from contextlib import contextmanager
from pathlib import Path
import json
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient
import database
from routers import admin_users
from services.credit_wallet import SCHEMA
from utils import admin_auth


class AdminUserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "admin.db"

        @contextmanager
        def db():
            conn = sqlite3.connect(self.path)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()

        self.db = db
        self.patches = [
            patch.object(admin_users, "get_db", db),
            patch.object(
                admin_auth, "JWT_SECRET", "test-only-admin-secret-32-characters"
            ),
            # admin 接口要求显式配置账号，未配置时一律 503。
            patch.object(admin_auth, "ADMIN_USERNAME", "admin"),
            patch.object(admin_auth, "ADMIN_PASSWORD", "test-admin-password"),
        ]
        for item in self.patches:
            item.start()
        with db() as conn:
            conn.executescript(database._CREATE_TABLES_SQL)
            conn.executescript(SCHEMA)
            for ident, name, email, github, created in [
                ("a", "Alice", "a@example.test", "alice", "2026-01-01"),
                ("b", "Bob", None, None, "2026-02-02"),
                ("c", "Percent%", "c@example.test", None, "2026-03-03"),
                ("__system__", "System", None, None, "2026-04-04"),
            ]:
                conn.execute(
                    "INSERT INTO users(id,name,email,github_id,github_username,password_hash,wechat_openid,created_at,preferences,about) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (
                        ident,
                        name,
                        email,
                        github,
                        github,
                        "PRIVATE_HASH",
                        "PRIVATE_OPENID_" + ident,
                        created,
                        '{"api_key":"PRIVATE_KEY"}',
                        '{"token":"PRIVATE_TOKEN"}',
                    ),
                )
            conn.execute(
                "INSERT INTO credit_wallets VALUES ('a',123,'2025-01','2025-01-01')"
            )
            conn.execute(
                "INSERT INTO credit_wallets VALUES ('c',-10,'2025-01','2025-01-01')"
            )
            conn.execute(
                "INSERT INTO usage_summary VALUES ('a',?,80,2)", (admin_users._month(),)
            )
            for ident, user, amount in [(1, "a", 123), (2, "b", 999)]:
                conn.execute(
                    "INSERT INTO credit_transactions(id,user_id,kind,amount,balance_after,unique_key,created_at) VALUES (?,?,?,?,?,?,?)",
                    (ident, user, "signup", amount, amount, str(ident), "2026-01-01"),
                )
            conn.execute(
                "INSERT INTO settings(user_id,key,value) VALUES ('a','llm_api_key','PRIVATE_KEY')"
            )
            conn.execute(
                "INSERT INTO user_profile_overview(user_id,overall_judgement,updated_at,source_snapshot) VALUES ('a','学习中','2026-01-01','PRIVATE_SNAPSHOT')"
            )
            for ident, charged, system in [("e1", 1, 0), ("e2", 0, 0), ("e3", 1, 1)]:
                conn.execute(
                    "INSERT INTO usage_events(id,user_id,period,category,scene,credits,is_system,created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (ident, "a", "2026-03", "llm", "chat", 20, system, "2026-03-03"),
                )
                conn.execute(
                    "INSERT INTO usage_details(event_id,counts_quota) VALUES (?,?)",
                    (ident, charged),
                )
        app = FastAPI()
        app.include_router(admin_users.router)
        self.client = TestClient(app)
        self.headers = {"Authorization": "Bearer " + admin_auth.create_admin_token()}

    def tearDown(self):
        self.client.close()
        for item in reversed(self.patches):
            item.stop()
        self.tmp.cleanup()

    def get(self, path="", **params):
        return self.client.get(
            "/api/admin/users" + path, params=params, headers=self.headers
        )

    def snapshot(self):
        with self.db() as conn:
            return "\n".join(conn.iterdump())

    def test_all_routes_require_real_admin_claims(self):
        normal = jwt.encode({"sub": "a"}, admin_auth.JWT_SECRET, algorithm="HS256")
        forged_role = jwt.encode(
            {"sub": "a", "role": "admin"}, admin_auth.JWT_SECRET, algorithm="HS256"
        )
        expired = jwt.encode(
            {"sub": "admin", "role": "admin", "exp": 1},
            admin_auth.JWT_SECRET,
            algorithm="HS256",
        )
        for path in ["", "/a", "/a/records", "/a/usage"]:
            for token in ["", normal, forged_role, expired]:
                with self.subTest(path=path, token_type=bool(token)):
                    response = self.client.get(
                        "/api/admin/users" + path,
                        headers={"Authorization": "Bearer " + token} if token else {},
                    )
                    self.assertIn(response.status_code, (401, 403))

    def test_read_views_never_grant_or_mutate(self):
        before = self.snapshot()
        for path in ["", "/a", "/b", "/a/usage", "/b/records"]:
            self.assertEqual(self.get(path).status_code, 200)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.get("/a").json()["user"]["balance"], 123)
        self.assertFalse(self.get("/b").json()["user"]["wallet_initialized"])

    def test_safe_projection_and_system_exclusion(self):
        listing = self.get().json()
        self.assertEqual(listing["total"], 3)
        detail = self.get("/a").json()
        for forbidden in [
            "PRIVATE_",
            "password_hash",
            "wechat_openid",
            "source_snapshot",
            "llm_api_key",
        ]:
            self.assertNotIn(forbidden, json.dumps([listing, detail]))
        self.assertEqual(self.get("/__system__").status_code, 404)
        self.assertEqual(self.get("/unknown/records").status_code, 404)

    def test_search_pagination_filters_and_order(self):
        self.assertEqual(self.get(q="alice").json()["items"][0]["id"], "a")
        self.assertEqual(self.get(q="%").json()["total"], 1)
        self.assertEqual(self.get(q="' OR 1=1 --").json()["total"], 0)
        self.assertEqual(self.get(binding="github").json()["total"], 1)
        self.assertEqual(self.get(min_balance=0).json()["total"], 1)
        self.assertEqual(self.get(max_balance=0).json()["items"][0]["id"], "c")
        self.assertEqual(
            self.get(created_from="2026-02-01", created_to="2026-02-28").json()[
                "total"
            ],
            1,
        )
        self.assertEqual(
            self.get(limit=1, offset=1, sort_order="asc").json()["items"][0]["id"], "b"
        )
        self.assertEqual(self.get(sort_by="used").json()["items"][0]["used"], 80)
        self.assertEqual(self.get(min_balance=5, max_balance=1).status_code, 400)
        self.assertEqual(
            self.get(created_from="2026-03-01", created_to="2026-01-01").status_code,
            400,
        )
        self.assertEqual(self.get(sort_by="DROP TABLE users").status_code, 422)
        self.assertEqual(self.get(limit=1000).status_code, 422)

    def test_records_are_scoped_and_paginated(self):
        data = self.get("/a/records", kind="transactions", limit=1).json()
        self.assertEqual(data["total"], 1)
        self.assertEqual(data["items"][0]["amount"], 123)
        self.assertEqual(self.get("/a/records", offset=1).json()["items"], [])
        self.assertEqual(self.get("/a/records", kind="settings").status_code, 422)

    def test_usage_distinguishes_system_and_own_key(self):
        data = self.get("/a/usage", period="2026-03").json()
        self.assertEqual(data["items"][0]["credits"], 60)
        self.assertEqual(data["items"][0]["charged"], 20)
        self.assertEqual(self.get("/b/usage", period="2026-03").json()["items"], [])
        self.assertEqual(self.get("/a/usage", period="2026-13").status_code, 422)


if __name__ == "__main__":
    unittest.main()
