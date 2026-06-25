"""
AggregatorService:observation → 共性归纳器（最小形态）

职责
====
  1. 按 (concept_id, observation_type) 桶扫描未处理的观察
  2. 桶内观察数达到 per-type 阈值 → 调 LLM 归纳是否值得抽象成教学知识
  3. 若值得 → **产一条 ``suggest_facet_pattern`` proposal**（pending），
     由管理员人工审阅决定是否落 facet
  4. 标记观察 processed_at

设计要点
========
  - **不再做语义查重**（哪怕重复也再产一条，让管理员去合并/拒绝）
  - **不再直写 facet / 不再 increment_support**（所有抽象动作都停在 proposal）
  - **不再走 AutoApproveGate**（这两种 op 永远 pending，不会被自动 approve）
  - 真正的"知识抽象"由 LLM 完成，aggregator 只做调度 + 产提议
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from ..models import (
    ObservationCreate,
    ObservationSchema,
    ProposalCreate,
)
from ..repositories import (
    ConceptRepository,
    ObservationRepository,
    ProposalRepository,
)

logger = logging.getLogger(__name__)


# 每种 observation_type 触发 LLM 归纳的最小桶大小
DEFAULT_TRIGGER_THRESHOLD: dict[str, int] = {
    "struggle": 8,
    "breakthrough": 5,
    "misconception": 6,
    "effective_metaphor": 5,
    "emotional_block": 8,
}


# ============================================================
# 服务
# ============================================================


class AggregatorService:
    def __init__(
        self,
        trigger_threshold: Optional[dict[str, int]] = None,
        bucket_fetch_limit: int = 30,
    ) -> None:
        self.obs_repo = ObservationRepository()
        self.concept_repo = ConceptRepository()
        self.proposal_repo = ProposalRepository()
        self.trigger_threshold = trigger_threshold or DEFAULT_TRIGGER_THRESHOLD
        self.bucket_fetch_limit = bucket_fetch_limit

    # ---------- 写入观察（agent 直接调）----------

    def submit_observation(self, data: ObservationCreate) -> ObservationSchema:
        """agent 在对话中写入一条观察；不做任何聚合，立即落库。"""
        return self.obs_repo.create(data)

    # ---------- 聚合（聚合器调度）----------

    def run_once(self, batch_size: int = 200) -> dict:
        """扫描所有桶，处理达阈值的桶。返回统计摘要。

        ``batch_size`` 这一轮最多处理多少个桶（避免 LLM 调用过多）。
        """
        stats = self.obs_repo.count_unprocessed_by_bucket()
        if not stats:
            return {
                "buckets_total": 0,
                "buckets_handled": 0,
                "proposed": 0,
                "skipped": 0,
            }

        buckets_handled = 0
        proposed = 0
        skipped = 0

        for s in stats:
            if buckets_handled >= batch_size:
                break

            cid = s["concept_id"]
            otype = s["observation_type"]
            cnt = s["count"]

            threshold = self.trigger_threshold.get(otype)
            if threshold is None:
                # 非法 type，标记为 processed 防止反复堵塞
                obs = self.obs_repo.list_unprocessed_in_bucket(cid, otype, limit=200)
                self.obs_repo.mark_processed([o.id for o in obs])
                logger.warning(
                    "observation_type=%s 不在已知列表，标记 %d 条 processed",
                    otype,
                    len(obs),
                )
                continue

            if cnt < threshold:
                continue

            outcome = self._handle_bucket(cid, otype)
            buckets_handled += 1
            if outcome == "propose":
                proposed += 1
            else:
                skipped += 1

        return {
            "buckets_total": len(stats),
            "buckets_handled": buckets_handled,
            "proposed": proposed,
            "skipped": skipped,
        }

    # ---------- 桶处理 ----------

    def _handle_bucket(self, concept_id: str, observation_type: str) -> str:
        observations = self.obs_repo.list_unprocessed_in_bucket(
            concept_id, observation_type, limit=self.bucket_fetch_limit
        )
        if not observations:
            return "ignore"

        concept = self.concept_repo.get_by_id(concept_id)
        if not concept:
            # concept 已不存在，标记 processed 不阻塞
            self.obs_repo.mark_processed([o.id for o in observations])
            return "ignore"

        # 调 LLM 归纳
        try:
            verdict = self._synthesize_with_llm(
                concept=concept,
                observation_type=observation_type,
                observations=observations,
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "LLM 归纳失败 concept=%s type=%s n=%d",
                concept_id,
                observation_type,
                len(observations),
            )
            # 不标记 processed，留待下次重试
            return "ignore"

        if not verdict.get("should_propose"):
            # LLM 认为这堆观察暂不构成共性 → 标记 processed 但不产 proposal
            self.obs_repo.mark_processed([o.id for o in observations])
            logger.info(
                "聚合 skip concept=%s type=%s n=%d reason=%s",
                concept_id,
                observation_type,
                len(observations),
                verdict.get("reason", ""),
            )
            return "skip"

        kind = (verdict.get("suggested_kind") or "").strip()
        if not kind:
            # LLM 未给出 kind 时，用 observation_type 当兑底标签
            kind = observation_type
        content = (verdict.get("synthesized_content") or "").strip()
        if not content:
            # LLM 没能给出有效内容，跳过
            self.obs_repo.mark_processed([o.id for o in observations])
            return "skip"

        # 产一条 suggest_facet_pattern proposal（pending），等管理员审
        try:
            proposal = self.proposal_repo.create(
                ProposalCreate(
                    op="suggest_facet_pattern",
                    proposer="agent:dialog_aggregator",
                    payload={
                        "concept_id": concept_id,
                        "concept_name": concept.canonical_name,
                        "kind": kind,
                        "content": content,
                        "observation_type": observation_type,
                        "observation_ids": [o.id for o in observations],
                        "observation_count": len(observations),
                        "user_count": len(
                            {o.user_id for o in observations if o.user_id}
                        ),
                        "session_ids": list(
                            {o.session_id for o in observations if o.session_id}
                        ),
                        "rationale": verdict.get("rationale", ""),
                        "suggested_confidence": min(
                            0.9, 0.4 + 0.05 * len(observations)
                        ),
                    },
                    target_concept_id=concept_id,
                )
            )
        except Exception:  # pylint: disable=broad-except
            logger.exception(
                "聚合产 proposal 失败 concept=%s kind=%s，不标记 processed 以便下次重试",
                concept_id,
                kind,
            )
            return "ignore"

        # 把 observations 标记 processed，并把 derived_proposal_id 回写到这些观察上，
        # 方便后续从 observation 反查"我是被哪条 proposal 归纳走的"。
        self.obs_repo.mark_processed(
            [o.id for o in observations],
            derived_proposal_id=proposal.id,
        )
        logger.info(
            "聚合 propose concept=%s type=%s n=%d kind=%s → suggest_facet_pattern (proposal=%s)",
            concept_id,
            observation_type,
            len(observations),
            kind,
            proposal.id,
        )
        return "propose"

    # ---------- LLM 归纳 ----------

    def _synthesize_with_llm(
        self,
        *,
        concept,
        observation_type: str,
        observations: list[ObservationSchema],
    ) -> dict:
        """调 LLM 把一组同 type、同 concept 的观察归纳成教学知识候选。

        返回 dict（已解析）：
          - should_propose: bool
          - suggested_kind: str?
          - synthesized_content: str?
          - rationale: str?
          - reason: str?  (should_propose=False 时给出)
        """
        from services.llm_factory import get_system_llm  # 延迟引入，避免循环

        # 系统内部组件，不消耗额度、不依赖任何真实用户配置
        llm = get_system_llm()

        obs_render = []
        for i, o in enumerate(observations, 1):
            obs_render.append(
                f"[{i}] (user={o.user_id or 'anon'}, conf={o.agent_confidence:.2f}) "
                f"{o.description}"
            )
        obs_text = "\n".join(obs_render)

        system = (
            "你是 KG 知识聚合器。"
            "你的任务：从一组针对同一概念的用户学习观察中，"
            "判断是否存在值得抽象成普适教学知识的共性模式，"
            "若有则归纳成一条面向未来教师/agent的教学知识。"
        )
        user = f"""请分析以下关于概念「{concept.canonical_name}」的 {len(observations)} 条用户学习观察。

这些观察都被 agent 标记为「{observation_type}」类。

请判断：
1. 这些观察是否反映了一个**普适、值得记入教学知识库**的模式？
   - 不能只是单一用户的偶然现象
   - 不能是已经众所周知的常识
   - 必须对未来教学其他用户有指导价值

2. 如果是，请输出：
   - suggested_kind：这条知识的标签（1-3 词中文，如："易错点"、"常见困惑"、
     "有效讲法"、"前置缺失"、"有效类比" 等，由你根据内容选合适的）
   - synthesized_content：用 1-2 句话写出这条教学知识（面向未来的教师/agent，不是面向学生）
   - rationale：为什么从这些观察归纳出这条
   - should_propose：true

3. 如果不是，请输出：
   - should_propose：false
   - reason：这堆观察暂时不够的原因

观察列表：
{obs_text}

只输出 JSON，不要任何额外文字。例如：
{{"should_propose": true, "suggested_kind": "易错点",
  "synthesized_content": "...", "rationale": "..."}}
"""
        resp = llm.think(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            config={"temperature": 0.2},
        )
        text = (resp.content or "").strip()
        # 容错：去掉可能的 ```json 包裹
        if text.startswith("```"):
            text = text.strip("`")
            if text.lower().startswith("json"):
                text = text[4:].strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM 返回非 JSON，按 skip 处理: %s", text[:200])
            return {"should_propose": False, "reason": "LLM 输出非 JSON"}
        if not isinstance(data, dict):
            return {"should_propose": False, "reason": "LLM 输出非对象"}
        return data
