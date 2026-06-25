"""L2 用户画像（结构化记忆）数据访问层。

包含四个 Repository：
- ProfileFactRepository     ：事实库的优先级 upsert / 观测晋升 / 冲突淘汰 /
                              读时衰减过滤 / 惰性归档，每次写操作同连接追加 fact_history。
- ProfileOverviewRepository ：统一画像总览，集中承载整体判断、兴趣、水平、知识面与学习行为。
- ProfileSkillRepository    ：技能 upsert / list_active / 按 task_type 激活查询。
- ProfileFactHistoryRepository：审计流水 append / list_by_fact。

时间衰减采用「读时计算 effective_confidence + consolidate 惰性归档」，
不引入后台定时任务，契合现有无 scheduler 架构。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from models.profile import (
    ARCHIVABLE_EVIDENCE_TYPES,
    DECAY_ARCHIVE_THRESHOLD,
    OBSERVATION_PROMOTION_STEP,
    effective_confidence,
    evidence_priority,
)

from .base import BaseRepository, _dumps, _loads, new_id, utcnow_str


class ProfileFactHistoryRepository(BaseRepository):
    """画像变更流水（append-only 审计）。"""

    @staticmethod
    def build_insert(
        *,
        user_id: str,
        fact_id: str,
        category: str,
        key: str,
        change_type: str,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        old_confidence: Optional[float] = None,
        new_confidence: Optional[float] = None,
        evidence_type: str = "",
        source_ref: str = "",
        reason: str = "",
        created_at: Optional[str] = None,
    ) -> tuple[str, tuple]:
        """构造一条 history 的 (sql, params)，供同连接 _executemany 原子写入。"""
        sql = """
            INSERT INTO user_profile_fact_history
                (id, user_id, fact_id, category, key, change_type,
                 old_value, new_value, old_confidence, new_confidence,
                 evidence_type, source_ref, reason, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        params = (
            new_id(),
            user_id,
            fact_id,
            category,
            key,
            change_type,
            old_value,
            new_value,
            old_confidence,
            new_confidence,
            evidence_type,
            source_ref,
            reason,
            created_at or utcnow_str(),
        )
        return sql, params

    def list_by_fact(self, user_id: str, fact_id: str) -> list[dict]:
        return self._fetchall(
            """
            SELECT * FROM user_profile_fact_history
            WHERE user_id=? AND fact_id=?
            ORDER BY created_at ASC
            """,
            (user_id, fact_id),
        )


class ProfileFactRepository(BaseRepository):
    """结构化事实库。"""

    def __init__(self) -> None:
        self._history = ProfileFactHistoryRepository()

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def get(self, user_id: str, category: str, key: str) -> Optional[dict]:
        return self._fetchone(
            "SELECT * FROM user_profile_facts WHERE user_id=? AND category=? AND key=?",
            (user_id, category, key),
        )

    def list_active(
        self,
        user_id: str,
        *,
        min_effective_confidence: float = 0.0,
        now: Optional[datetime] = None,
    ) -> list[dict]:
        """返回 active 事实，附带读时计算的 effective_confidence。

        SQL 侧只按 status 粗筛，effective_confidence 在 Python 侧计算并精筛、排序，
        避免在 SQL 写复杂幂运算。结果按 (effective_confidence * importance) 降序。
        """
        now = now or datetime.now(timezone.utc)
        rows = self._fetchall(
            "SELECT * FROM user_profile_facts WHERE user_id=? AND status='active'",
            (user_id,),
        )
        result: list[dict] = []
        for row in rows:
            eff = effective_confidence(
                row["confidence"], row["evidence_type"], row["last_reinforced_at"], now
            )
            if eff < min_effective_confidence:
                continue
            row = dict(row)
            row["effective_confidence"] = eff
            row["evidence"] = _loads(row.get("evidence"), [])
            result.append(row)
        result.sort(
            key=lambda r: r["effective_confidence"] * (r.get("importance") or 0.5),
            reverse=True,
        )
        return result

    def list_active_by_source(
        self, user_id: str, source_ref: str, *, category: Optional[str] = None
    ) -> list[dict]:
        """按来源读取 active facts，用于用户自填信息的增删同步。"""
        if category:
            return self._fetchall(
                """
                SELECT * FROM user_profile_facts
                WHERE user_id=? AND source_ref=? AND category=? AND status='active'
                """,
                (user_id, source_ref, category),
            )
        return self._fetchall(
            """
            SELECT * FROM user_profile_facts
            WHERE user_id=? AND source_ref=? AND status='active'
            """,
            (user_id, source_ref),
        )

    # ------------------------------------------------------------------
    # 写入：优先级 upsert + 观测晋升 + 冲突淘汰
    # ------------------------------------------------------------------

    def upsert_candidate(
        self,
        user_id: str,
        *,
        category: str,
        key: str,
        value: str,
        evidence_type: str = "inference",
        confidence: float = 0.5,
        importance: float = 0.5,
        evidence: Optional[list] = None,
        source_ref: str = "",
        value_type: str = "text",
    ) -> str:
        """按证据优先级写入单条候选事实，返回变更类型。

        规则：
        - 不存在 → 新建（created）。
        - 已存在且 value 相同 → 观测晋升（reinforced）：confidence 提升、
          observation_count+1、刷新 last_reinforced_at。
        - 已存在但 value 不同：
            * 新证据优先级/置信度 ≥ 旧 → 旧值标记 superseded，写入新事实（created）。
            * 否则忽略本候选（不降级既有事实）。

        所有分支的事实写入与 history 追加在同一连接内原子完成。
        """
        evidence = evidence or []
        now = utcnow_str()
        existing = self.get(user_id, category, key)

        # —— 新建 ——
        if existing is None:
            return self._create_fact(
                user_id,
                category=category,
                key=key,
                value=value,
                evidence_type=evidence_type,
                confidence=confidence,
                importance=importance,
                evidence=evidence,
                source_ref=source_ref,
                value_type=value_type,
                now=now,
            )

        # —— 同值：观测晋升 ——
        if existing["status"] == "active" and existing["value"] == value:
            return self._reinforce_fact(existing, evidence_type, source_ref, now)

        # —— 不同值：按优先级决定是否覆盖 ——
        new_pri = evidence_priority(evidence_type)
        old_pri = evidence_priority(existing["evidence_type"])
        new_wins = (new_pri > old_pri) or (
            new_pri == old_pri and confidence >= existing["confidence"]
        )
        if not new_wins:
            return "ignored"

        # 旧值 superseded（仅当其仍 active），再新建当前值
        ops: list[tuple[str, tuple]] = []
        if existing["status"] == "active":
            ops.append(
                (
                    "UPDATE user_profile_facts SET status='superseded', updated_at=? WHERE id=?",
                    (now, existing["id"]),
                )
            )
            ops.append(
                self._history.build_insert(
                    user_id=user_id,
                    fact_id=existing["id"],
                    category=category,
                    key=key,
                    change_type="superseded",
                    old_value=existing["value"],
                    new_value=value,
                    old_confidence=existing["confidence"],
                    new_confidence=confidence,
                    evidence_type=evidence_type,
                    source_ref=source_ref,
                    reason="higher_priority_conflict",
                    created_at=now,
                )
            )
        # 因 UNIQUE(user_id,category,key)，需先删除被 superseded 的旧行的唯一占位：
        # 这里采用「就地覆盖」策略——直接更新旧行为新值并复位为 active，避免唯一约束冲突。
        # （superseded 历史已写入 fact_history 审计，事实演变可追溯。）
        fact_id = existing["id"]
        ops.append(
            (
                """
                UPDATE user_profile_facts
                SET value=?, value_type=?, evidence_type=?, confidence=?,
                    importance=?, observation_count=1, source_ref=?, evidence=?,
                    status='active', last_reinforced_at=?, updated_at=?
                WHERE id=?
                """,
                (
                    value,
                    value_type,
                    evidence_type,
                    confidence,
                    importance,
                    source_ref,
                    _dumps(evidence),
                    now,
                    now,
                    fact_id,
                ),
            )
        )
        ops.append(
            self._history.build_insert(
                user_id=user_id,
                fact_id=fact_id,
                category=category,
                key=key,
                change_type="created",
                old_value=existing["value"],
                new_value=value,
                old_confidence=existing["confidence"],
                new_confidence=confidence,
                evidence_type=evidence_type,
                source_ref=source_ref,
                reason="overwrite_after_supersede",
                created_at=now,
            )
        )
        self._executemany(ops)
        return "superseded"

    def archive_fact(
        self,
        user_id: str,
        category: str,
        key: str,
        *,
        source_ref: str = "",
        reason: str = "user_cleared",
    ) -> bool:
        """将指定 active fact 归档，并写入审计流水。"""
        existing = self.get(user_id, category, key)
        if not existing or existing.get("status") != "active":
            return False
        now = utcnow_str()
        self._executemany(
            [
                (
                    "UPDATE user_profile_facts SET status='archived', updated_at=? WHERE id=?",
                    (now, existing["id"]),
                ),
                self._history.build_insert(
                    user_id=user_id,
                    fact_id=existing["id"],
                    category=category,
                    key=key,
                    change_type="archived",
                    old_value=existing["value"],
                    new_value=existing["value"],
                    old_confidence=existing["confidence"],
                    new_confidence=existing["confidence"],
                    evidence_type=existing["evidence_type"],
                    source_ref=source_ref or existing.get("source_ref", ""),
                    reason=reason,
                    created_at=now,
                ),
            ]
        )
        return True

    def _create_fact(
        self,
        user_id: str,
        *,
        category: str,
        key: str,
        value: str,
        evidence_type: str,
        confidence: float,
        importance: float,
        evidence: list,
        source_ref: str,
        value_type: str,
        now: str,
    ) -> str:
        fact_id = new_id()
        ops = [
            (
                """
                INSERT INTO user_profile_facts
                    (id, user_id, category, key, value, value_type, evidence_type,
                     confidence, importance, observation_count, source_ref, evidence,
                     status, last_reinforced_at, valid_from, valid_until,
                     created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, 'active', ?, NULL, NULL, ?, ?)
                """,
                (
                    fact_id,
                    user_id,
                    category,
                    key,
                    value,
                    value_type,
                    evidence_type,
                    confidence,
                    importance,
                    source_ref,
                    _dumps(evidence),
                    now,
                    now,
                    now,
                ),
            ),
            self._history.build_insert(
                user_id=user_id,
                fact_id=fact_id,
                category=category,
                key=key,
                change_type="created",
                old_value=None,
                new_value=value,
                old_confidence=None,
                new_confidence=confidence,
                evidence_type=evidence_type,
                source_ref=source_ref,
                reason="new_fact",
                created_at=now,
            ),
        ]
        self._executemany(ops)
        return "created"

    def _reinforce_fact(
        self, existing: dict, evidence_type: str, source_ref: str, now: str
    ) -> str:
        """同值再观测：confidence 晋升、observation_count+1、刷新衰减基准。"""
        old_conf = existing["confidence"]
        new_conf = min(1.0, old_conf + OBSERVATION_PROMOTION_STEP)
        ops = [
            (
                """
                UPDATE user_profile_facts
                SET confidence=?, observation_count=observation_count+1,
                    last_reinforced_at=?, updated_at=?
                WHERE id=?
                """,
                (new_conf, now, now, existing["id"]),
            ),
            self._history.build_insert(
                user_id=existing["user_id"],
                fact_id=existing["id"],
                category=existing["category"],
                key=existing["key"],
                change_type="reinforced",
                old_value=existing["value"],
                new_value=existing["value"],
                old_confidence=old_conf,
                new_confidence=new_conf,
                evidence_type=evidence_type,
                source_ref=source_ref,
                reason="observed_again",
                created_at=now,
            ),
        ]
        self._executemany(ops)
        return "reinforced"

    # ------------------------------------------------------------------
    # 惰性归档（时间衰减维护）
    # ------------------------------------------------------------------

    def decay_maintenance(self, user_id: str, *, now: Optional[datetime] = None) -> int:
        """扫描该用户 active 事实，将 effective_confidence 跌破阈值且
        证据类型可归档（behavior/inference）的事实置为 archived。

        explicit/quiz 不自动归档。每条归档同连接写一条 history。
        返回归档条数。
        """
        now = now or datetime.now(timezone.utc)
        now_str = now.isoformat()
        rows = self._fetchall(
            "SELECT * FROM user_profile_facts WHERE user_id=? AND status='active'",
            (user_id,),
        )
        ops: list[tuple[str, tuple]] = []
        archived = 0
        for row in rows:
            if row["evidence_type"] not in ARCHIVABLE_EVIDENCE_TYPES:
                continue
            eff = effective_confidence(
                row["confidence"], row["evidence_type"], row["last_reinforced_at"], now
            )
            if eff >= DECAY_ARCHIVE_THRESHOLD:
                continue
            ops.append(
                (
                    "UPDATE user_profile_facts SET status='archived', updated_at=? WHERE id=?",
                    (now_str, row["id"]),
                )
            )
            ops.append(
                self._history.build_insert(
                    user_id=user_id,
                    fact_id=row["id"],
                    category=row["category"],
                    key=row["key"],
                    change_type="archived",
                    old_value=row["value"],
                    new_value=row["value"],
                    old_confidence=row["confidence"],
                    new_confidence=round(eff, 4),
                    evidence_type=row["evidence_type"],
                    source_ref="",
                    reason="decayed_below_threshold",
                    created_at=now_str,
                )
            )
            archived += 1
        if ops:
            self._executemany(ops)
        return archived


class ProfileOverviewRepository(BaseRepository):
    """统一画像总览：对外读取的唯一画像入口。"""

    def get(self, user_id: str) -> Optional[dict]:
        row = self._fetchone(
            "SELECT * FROM user_profile_overview WHERE user_id=?", (user_id,)
        )
        if not row:
            return None
        row["interests"] = _loads(row.get("interests"), [])
        row["source_snapshot"] = _loads(row.get("source_snapshot"), {})
        row["facts_snapshot"] = _loads(row.get("facts_snapshot"), [])
        return row

    def upsert(
        self,
        user_id: str,
        *,
        overall_judgement: str = "",
        interests: Optional[list[str]] = None,
        learning_level: str = "",
        knowledge_scope: str = "",
        dialogue_preference: str = "",
        learning_behavior: str = "",
        weakness_summary: str = "",
        strategy_summary: str = "",
        source_snapshot: Optional[dict[str, Any]] = None,
        facts_snapshot: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self._execute(
            """
            INSERT INTO user_profile_overview
                (user_id, overall_judgement, interests, learning_level, knowledge_scope,
                 dialogue_preference, learning_behavior, weakness_summary, strategy_summary,
                 source_snapshot, facts_snapshot, version, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                overall_judgement=excluded.overall_judgement,
                interests=excluded.interests,
                learning_level=excluded.learning_level,
                knowledge_scope=excluded.knowledge_scope,
                dialogue_preference=excluded.dialogue_preference,
                learning_behavior=excluded.learning_behavior,
                weakness_summary=excluded.weakness_summary,
                strategy_summary=excluded.strategy_summary,
                source_snapshot=excluded.source_snapshot,
                facts_snapshot=excluded.facts_snapshot,
                version=user_profile_overview.version+1,
                updated_at=excluded.updated_at
            """,
            (
                user_id,
                overall_judgement,
                _dumps(interests or []),
                learning_level,
                knowledge_scope,
                dialogue_preference,
                learning_behavior,
                weakness_summary,
                strategy_summary,
                _dumps(source_snapshot or {}),
                _dumps(facts_snapshot or []),
                utcnow_str(),
            ),
        )

    def build_source_snapshot(self, user_id: str) -> dict[str, Any]:
        """把知识图谱、会话、学习日志聚合为画像侧统一快照。"""
        node_rows = self._fetchall(
            """
            SELECT title, tags, mastery_level, due_date, last_review_at, updated_at
            FROM nodes WHERE user_id=? ORDER BY updated_at DESC LIMIT 200
            """,
            (user_id,),
        )
        session_rows = self._fetchall(
            """
            SELECT title, topic, status, message_count, duration_minutes, created_at, ended_at
            FROM sessions WHERE user_id=? ORDER BY created_at DESC LIMIT 50
            """,
            (user_id,),
        )
        study_rows = self._fetchall(
            """
            SELECT date, SUM(minutes) AS minutes
            FROM study_logs WHERE user_id=? GROUP BY date ORDER BY date DESC LIMIT 84
            """,
            (user_id,),
        )

        levels = [float(r.get("mastery_level") or 0.0) for r in node_rows]
        total_nodes = len(node_rows)
        mastered_nodes = sum(1 for v in levels if v >= 0.8)
        weak_nodes = [
            r for r in node_rows if float(r.get("mastery_level") or 0.0) < 0.34
        ]
        avg_mastery = round(sum(levels) / total_nodes, 3) if total_nodes else 0.0

        tag_counts: dict[str, int] = {}
        for row in node_rows:
            for tag in _loads(row.get("tags"), []) or []:
                tag = str(tag).strip()
                if tag:
                    tag_counts[tag] = tag_counts.get(tag, 0) + 1
        top_tags = sorted(tag_counts, key=tag_counts.get, reverse=True)[:8]

        total_minutes = sum(int(r.get("minutes") or 0) for r in study_rows)
        active_days = sum(1 for r in study_rows if int(r.get("minutes") or 0) > 0)
        recent_topics: list[str] = []
        for row in session_rows[:10]:
            topic = (
                (row.get("topic") or row.get("title") or "")
                .replace("[AI课程]", "")
                .strip()
            )
            if topic and topic not in recent_topics:
                recent_topics.append(topic)

        return {
            "knowledge": {
                "total_nodes": total_nodes,
                "mastered_nodes": mastered_nodes,
                "weak_nodes": len(weak_nodes),
                "average_mastery": avg_mastery,
                "top_tags": top_tags,
                "recent_weak_nodes": [
                    {
                        "title": r.get("title", ""),
                        "mastery_level": float(r.get("mastery_level") or 0.0),
                    }
                    for r in sorted(
                        weak_nodes,
                        key=lambda x: x.get("updated_at") or "",
                        reverse=True,
                    )[:6]
                ],
                "recent_strong_nodes": [
                    {
                        "title": r.get("title", ""),
                        "mastery_level": float(r.get("mastery_level") or 0.0),
                    }
                    for r in sorted(
                        [
                            r
                            for r in node_rows
                            if float(r.get("mastery_level") or 0.0) >= 0.8
                        ],
                        key=lambda x: x.get("updated_at") or "",
                        reverse=True,
                    )[:6]
                ],
            },
            "learning_behavior": {
                "total_sessions": len(session_rows),
                "completed_sessions": sum(
                    1 for r in session_rows if r.get("status") == "completed"
                ),
                "total_minutes": total_minutes,
                "active_days": active_days,
                "average_minutes_per_active_day": round(total_minutes / active_days, 1)
                if active_days
                else 0,
                "recent_topics": recent_topics[:8],
            },
        }

    def build_facts_snapshot(
        self, user_id: str, limit: int = 50
    ) -> list[dict[str, Any]]:
        """构建当前 active facts 快照，供 overview 快速注入和调试。"""
        rows = self._fetchall(
            """
            SELECT id, category, key, value, evidence_type, confidence, importance,
                   observation_count, updated_at
            FROM user_profile_facts
            WHERE user_id=? AND status='active'
            ORDER BY importance DESC, confidence DESC, updated_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        return [dict(r) for r in rows]

    def refresh_source_snapshot(self, user_id: str) -> Optional[dict]:
        """刷新总览中的客观统计和 facts 快照，保留 LLM 编译出的主观字段。"""
        snapshot = self.build_source_snapshot(user_id)
        facts_snapshot = self.build_facts_snapshot(user_id)
        current = self.get(user_id)
        if (
            current
            and current.get("source_snapshot") == snapshot
            and current.get("facts_snapshot") == facts_snapshot
        ):
            return current
        self.upsert(
            user_id,
            overall_judgement=(current or {}).get("overall_judgement", ""),
            interests=(current or {}).get("interests", []),
            learning_level=(current or {}).get("learning_level", ""),
            knowledge_scope=(current or {}).get("knowledge_scope", ""),
            dialogue_preference=(current or {}).get("dialogue_preference", ""),
            learning_behavior=(current or {}).get("learning_behavior", ""),
            weakness_summary=(current or {}).get("weakness_summary", ""),
            strategy_summary=(current or {}).get("strategy_summary", ""),
            source_snapshot=snapshot,
            facts_snapshot=facts_snapshot,
        )
        return self.get(user_id)


class ProfileSkillRepository(BaseRepository):
    """由 facts 编译的画像技能（按任务激活）。"""

    def upsert(
        self,
        user_id: str,
        *,
        skill_name: str,
        content: str,
        skill_type: str = "",
        trigger_conditions: Optional[list] = None,
        source_fact_ids: Optional[list] = None,
        priority: float = 0.5,
    ) -> None:
        now = utcnow_str()
        self._execute(
            """
            INSERT INTO user_profile_skills
                (id, user_id, skill_name, skill_type, content, trigger_conditions,
                 source_fact_ids, priority, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
            ON CONFLICT(user_id, skill_name) DO UPDATE SET
                skill_type=excluded.skill_type,
                content=excluded.content,
                trigger_conditions=excluded.trigger_conditions,
                source_fact_ids=excluded.source_fact_ids,
                priority=excluded.priority,
                status='active',
                updated_at=excluded.updated_at
            """,
            (
                new_id(),
                user_id,
                skill_name,
                skill_type,
                content,
                _dumps(trigger_conditions or []),
                _dumps(source_fact_ids or []),
                priority,
                now,
                now,
            ),
        )

    def list_active(self, user_id: str) -> list[dict]:
        rows = self._fetchall(
            """
            SELECT * FROM user_profile_skills
            WHERE user_id=? AND status='active'
            ORDER BY priority DESC
            """,
            (user_id,),
        )
        for row in rows:
            row["trigger_conditions"] = _loads(row.get("trigger_conditions"), [])
            row["source_fact_ids"] = _loads(row.get("source_fact_ids"), [])
        return rows

    def list_for_task(self, user_id: str, task_type: str) -> list[dict]:
        """返回可被指定 task_type 激活的技能（trigger_conditions 含该 task 或为空）。"""
        result = []
        for row in self.list_active(user_id):
            triggers = row.get("trigger_conditions") or []
            if not triggers or task_type in triggers:
                result.append(row)
        return result
