"""
UserRepository
"""

from __future__ import annotations
import json
from typing import Optional
from models.user import UserSchema, UserPreferences, UserAbout
from .base import BaseRepository, utcnow_str


class UserRepository(BaseRepository):
    def get_by_id(self, user_id: str) -> Optional[UserSchema]:
        row = self._fetchone("SELECT * FROM users WHERE id=?", (user_id,))
        if not row:
            return None
        prefs = json.loads(row["preferences"] or "{}")
        about = json.loads(row["about"] or "{}")
        return UserSchema(
            id=row["id"],
            name=row["name"],
            avatar_url=row["avatar_url"],
            preferences=UserPreferences(**prefs),
            about=UserAbout(**about),
            created_at=row["created_at"],
        )

    def get_or_create_default(self) -> UserSchema:
        """单用户模式：始终返回 id='default' 的用户，不存在则创建"""
        user = self.get_by_id("default")
        if user:
            return user
        now = utcnow_str()
        self._execute(
            "INSERT INTO users (id, name, preferences, about, created_at) VALUES (?,?,?,?,?)",
            ("default", "用户", "{}", "{}", now),
        )
        return self.get_by_id("default")

    def update(
        self,
        user_id: str,
        name: Optional[str] = None,
        avatar_url: Optional[str] = None,
        preferences: Optional[UserPreferences] = None,
        about: Optional[UserAbout] = None,
    ) -> Optional[UserSchema]:
        fields, values = [], []
        if name is not None:
            fields.append("name=?")
            values.append(name)
        if avatar_url is not None:
            fields.append("avatar_url=?")
            values.append(avatar_url)
        if preferences is not None:
            fields.append("preferences=?")
            values.append(json.dumps(preferences.model_dump()))
        if about is not None:
            fields.append("about=?")
            values.append(json.dumps(about.model_dump()))
        if not fields:
            return self.get_by_id(user_id)
        values.append(user_id)
        self._execute(f"UPDATE users SET {', '.join(fields)} WHERE id=?", tuple(values))
        return self.get_by_id(user_id)
