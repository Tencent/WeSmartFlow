"""
Admin 审核台路由

提供独立于普通用户体系的：
  - POST /api/admin/login      账密登录，返回 admin token
  - GET  /api/admin/me         校验 token 是否有效（前端守卫用）
  - GET  /api/admin/proposals/stats        各状态计数
  - GET  /api/admin/proposals              列出 proposal（按 status）
  - GET  /api/admin/proposals/{id}/detail  详情（含目标概念、已有 facet、关联 observation）
  - POST /api/admin/proposals/{id}/approve 通过（纯打标）
  - POST /api/admin/proposals/{id}/reject  驳回

所有非 login 接口都依赖 require_admin（独立的 JWT，跟普通用户互不影响）。
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Query,
    Request,
    status,
)
from pydantic import BaseModel, Field

from kg import (
    ConceptRepository,
    FacetRepository,
    ObservationRepository,
    ProposalRepository,
    ProposalService,
)
from utils.admin_auth import (
    ADMIN_NOT_CONFIGURED_DETAIL,
    admin_credentials_configured,
    create_admin_token,
    require_admin,
    verify_admin_credentials,
)
from utils.log_safe import safe_log
from utils.rate_limit import FailureLockout, client_ip

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ============================================================
# 登录 / 鉴权
# ============================================================


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


# 单 IP：15 分钟内失败 5 次锁 15 分钟。
# 全局：15 分钟内失败 30 次锁 15 分钟，抵御分布式（多 IP）猜口令；
# 代价是被攻击期间合法管理员最多等 15 分钟。
_LOGIN_LOCK_DETAIL = "登录失败次数过多，请稍后再试"
_GLOBAL_KEY = "admin-login"
_ip_lockout = FailureLockout(5, 900, 900, detail=_LOGIN_LOCK_DETAIL)
_global_lockout = FailureLockout(30, 900, 900, detail=_LOGIN_LOCK_DETAIL)


@router.post("/login", response_model=AdminLoginResponse)
def admin_login(body: AdminLoginRequest, request: Request):
    if not admin_credentials_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=ADMIN_NOT_CONFIGURED_DETAIL,
        )

    # 先查锁定再比对口令：被锁定期间即使口令正确也拒绝，不给暴力猜测任何信号。
    ip = client_ip(request)
    _ip_lockout.check(ip)
    _global_lockout.check(_GLOBAL_KEY)

    if not verify_admin_credentials(body.username, body.password):
        _ip_lockout.record_failure(ip)
        _global_lockout.record_failure(_GLOBAL_KEY)
        logger.warning("admin 登录失败 ip=%s", safe_log(ip))
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="账号或密码错误",
        )

    _ip_lockout.record_success(ip)
    return AdminLoginResponse(access_token=create_admin_token())


@router.get("/me")
def admin_me(_: str = Depends(require_admin)):
    """前端守卫用：返回 200 即为已登录。"""
    return {"role": "admin"}


# ============================================================
# 积分卡
# ============================================================


class CreditCardCreateRequest(BaseModel):
    mode: str = "add"
    amount: int
    max_redemptions: int = 1
    expires_at: str | None = None
    note: str = ""
    recipient_user_id: str | None = Field(default=None, max_length=100)
    email_request_id: str | None = Field(default=None, min_length=8, max_length=100)


class CreditCardStatusRequest(BaseModel):
    disabled: bool = True


class CreditCardGiftRequest(BaseModel):
    recipient_user_id: str = Field(min_length=1, max_length=100)
    email_request_id: str = Field(min_length=8, max_length=100)


@router.post("/credit-cards")
def create_credit_card(
    body: CreditCardCreateRequest,
    background_tasks: BackgroundTasks,
    admin_id: str = Depends(require_admin),
):
    """管理员生成积分卡。普通用户只能拿卡码去兑换，看不到该管理接口。"""
    from services.credit_wallet import (
        CreditCardError,
        create_credit_card as create_card,
    )

    from services.credit_card_mail import CardMailError, send_card_email

    try:
        result = create_card(
            mode=body.mode,
            amount=body.amount,
            max_redemptions=body.max_redemptions,
            expires_at=body.expires_at,
            note=body.note,
            created_by=admin_id,
            recipient_user_id=body.recipient_user_id,
            email_request_id=body.email_request_id,
        )
        if result.get("delivery"):
            background_tasks.add_task(
                send_card_email, result["card_id"], body.email_request_id
            )
        return result
    except (CreditCardError, CardMailError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/credit-cards/{card_id}/email")
def card_email_status(card_id: str, _: str = Depends(require_admin)):
    from services.credit_card_mail import CardMailError, get_delivery

    try:
        return get_delivery(card_id)
    except CardMailError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/credit-cards/{card_id}/gift")
def gift_credit_card(
    card_id: str,
    body: CreditCardGiftRequest,
    background_tasks: BackgroundTasks,
    _: str = Depends(require_admin),
):
    from services.credit_card_mail import CardMailError, gift_card, send_card_email

    try:
        result = gift_card(card_id, body.recipient_user_id, body.email_request_id)
        background_tasks.add_task(send_card_email, card_id, body.email_request_id)
        return result
    except CardMailError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/credit-cards/{card_id}/email/retry")
def retry_card_email(
    card_id: str, background_tasks: BackgroundTasks, _: str = Depends(require_admin)
):
    from services.credit_card_mail import CardMailError, retry_delivery, send_card_email

    try:
        result = retry_delivery(card_id)
        background_tasks.add_task(send_card_email, card_id, result["request_id"])
        return result
    except CardMailError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/credit-cards")
def list_credit_cards(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    mode: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None, alias="status"),
    q: Optional[str] = Query(None),
    min_amount: Optional[int] = Query(None, ge=0),
    max_amount: Optional[int] = Query(None, ge=0),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc"),
    _: str = Depends(require_admin),
):
    """管理员查看积分卡生成记录和兑换明细，支持筛选与排序。"""
    from database import get_db
    from services.credit_wallet import ensure_credit_card_columns

    where = []
    params: list = []

    if mode:
        normalized_mode = mode.strip().lower()
        if normalized_mode not in {"add", "reset"}:
            raise HTTPException(400, detail="mode 必须是 add 或 reset")
        where.append("mode = ?")
        params.append(normalized_mode)

    if status_filter:
        normalized_status = status_filter.strip().lower()
        if normalized_status == "active":
            where.append("disabled = 0")
        elif normalized_status == "disabled":
            where.append("disabled = 1")
        elif normalized_status == "redeemed":
            where.append("redeemed_count > 0")
        elif normalized_status == "unused":
            where.append("redeemed_count = 0")
        elif normalized_status == "exhausted":
            where.append("max_redemptions > 0 AND redeemed_count >= max_redemptions")
        else:
            raise HTTPException(
                400,
                detail="status 必须是 active|disabled|redeemed|unused|exhausted",
            )

    if min_amount is not None:
        where.append("amount >= ?")
        params.append(int(min_amount))
    if max_amount is not None:
        where.append("amount <= ?")
        params.append(int(max_amount))
    if min_amount is not None and max_amount is not None and min_amount > max_amount:
        raise HTTPException(400, detail="最小额度不能大于最大额度")

    if q:
        keyword = f"%{q.strip()}%"
        where.append(
            "(code_plain LIKE ? OR code_preview LIKE ? OR note LIKE ? OR created_by LIKE ?)"
        )
        params.extend([keyword, keyword, keyword, keyword])

    where_sql = f"WHERE {' AND '.join(where)}" if where else ""
    sort_columns = {
        "created_at": "created_at",
        "amount": "amount",
        "redeemed_count": "redeemed_count",
        "max_redemptions": "max_redemptions",
        "mode": "mode",
        "status": "disabled",
        "code": "code_plain",
    }
    order_column = sort_columns.get(sort_by, "created_at")
    order_direction = "ASC" if sort_order.lower() == "asc" else "DESC"

    with get_db() as conn:
        ensure_credit_card_columns(conn)
        total = conn.execute(
            f"SELECT COUNT(*) FROM credit_cards {where_sql}", tuple(params)
        ).fetchone()[0]
        cards = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT
                    code_hash,
                    code_plain,
                    code_preview,
                    mode,
                    amount,
                    max_redemptions,
                    redeemed_count,
                    expires_at,
                    note,
                    disabled,
                    created_by,
                    created_at
                FROM credit_cards
                {where_sql}
                ORDER BY {order_column} {order_direction}, created_at DESC
                LIMIT ? OFFSET ?
                """,
                tuple(params + [limit, offset]),
            ).fetchall()
        ]

        hashes = [card["code_hash"] for card in cards]
        redemption_map: dict[str, list[dict]] = {h: [] for h in hashes}
        if hashes:
            placeholders = ",".join("?" for _ in hashes)
            rows = conn.execute(
                f"""
                SELECT
                    r.id,
                    r.code_hash,
                    r.user_id,
                    r.amount,
                    r.balance_after,
                    r.created_at,
                    u.name AS user_name,
                    u.email AS user_email,
                    u.github_username AS github_username
                FROM credit_card_redemptions r
                LEFT JOIN users u ON u.id = r.user_id
                WHERE r.code_hash IN ({placeholders})
                ORDER BY r.id DESC
                """,
                tuple(hashes),
            ).fetchall()
            for row in rows:
                item = dict(row)
                code_hash = item.pop("code_hash")
                redemption_map.setdefault(code_hash, []).append(item)

        from services.credit_card_mail import public_delivery

        deliveries = {}
        if hashes:
            deliveries = {
                row["card_id"]: public_delivery(row)
                for row in conn.execute(
                    f"SELECT * FROM credit_card_email_deliveries WHERE card_id IN ({','.join('?' for _ in hashes)})",
                    tuple(hashes),
                )
            }
        for card in cards:
            card["delivery"] = deliveries.get(card["code_hash"])
            card["redemptions"] = redemption_map.get(card["code_hash"], [])
            card["card_id"] = card["code_hash"]
            card["code_hash_tail"] = card["code_hash"][-8:]
            del card["code_hash"]

    return {
        "items": cards,
        "limit": limit,
        "offset": offset,
        "total": total,
        "count": len(cards),
    }


@router.patch("/credit-cards/{card_id}/status")
def update_credit_card_status(
    card_id: str,
    body: CreditCardStatusRequest,
    _: str = Depends(require_admin),
):
    """管理员停用或恢复某张积分卡。停用后普通用户不能再兑换。"""
    from database import get_db
    from services.credit_wallet import ensure_credit_card_columns

    normalized_id = card_id.strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized_id):
        raise HTTPException(400, detail="积分卡 ID 无效")

    with get_db() as conn:
        ensure_credit_card_columns(conn)
        row = conn.execute(
            "SELECT code_hash FROM credit_cards WHERE code_hash=?", (normalized_id,)
        ).fetchone()
        if not row:
            raise HTTPException(404, detail="积分卡不存在")
        conn.execute(
            "UPDATE credit_cards SET disabled=? WHERE code_hash=?",
            (1 if body.disabled else 0, normalized_id),
        )

    return {"ok": True, "card_id": normalized_id, "disabled": body.disabled}


# ============================================================
# Proposal 列表 / 计数 / 详情
# ============================================================


def _proposal_summary(p) -> dict:
    """卡片视图（左列展示用）。"""
    payload = p.payload or {}
    if p.op == "suggest_facet_pattern":
        title = (payload.get("content") or "").strip()
        target_name = payload.get("concept_name") or ""
    elif p.op == "suggest_missing_concept":
        title = (payload.get("concept_name") or "").strip()
        target_name = ""
    else:
        title = ""
        target_name = ""

    return {
        "id": p.id,
        "op": p.op,
        "status": p.status,
        "proposer": p.proposer,
        "target_concept_id": p.target_concept_id or "",
        "target_concept_name": target_name,
        "title": title,
        "session_id": p.session_id or "",
        "created_at": p.created_at,
        "reviewed_at": p.reviewed_at or "",
        "reviewer_id": p.reviewer_id or "",
        "review_note": p.review_note or "",
        # 异步落盘流水线状态（UI 徽章用）
        "apply_status": p.apply_status or "idle",
        "apply_error": p.apply_error or "",
        "apply_started_at": p.apply_started_at or "",
        "apply_finished_at": p.apply_finished_at or "",
    }


@router.get("/proposals/stats")
def proposal_stats(_: str = Depends(require_admin)):
    """返回 pending / approved / rejected 三个状态的总数。"""
    repo = ProposalRepository()
    out = {}
    for st in ("pending", "approved", "rejected"):
        rows = repo.list_by_status(st, limit=10000, offset=0)
        out[st] = len(rows)
    return out


@router.get("/proposals")
def list_proposals(
    status_filter: str = Query("pending", alias="status"),
    op: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    _: str = Depends(require_admin),
):
    if status_filter not in ("pending", "approved", "rejected"):
        raise HTTPException(400, detail="status 必须是 pending|approved|rejected")

    repo = ProposalRepository()
    if status_filter == "pending":
        rows = repo.list_pending(op=op, limit=limit, offset=offset)
    else:
        rows = repo.list_by_status(status_filter, limit=limit, offset=offset)
        if op:
            rows = [r for r in rows if r.op == op]

    return {
        "items": [_proposal_summary(p) for p in rows],
        "limit": limit,
        "offset": offset,
        "count": len(rows),
    }


@router.get("/proposals/{proposal_id}/detail")
def proposal_detail(proposal_id: str, _: str = Depends(require_admin)):
    repo = ProposalRepository()
    p = repo.get_by_id(proposal_id)
    if not p:
        raise HTTPException(404, detail="proposal 不存在")

    payload = p.payload or {}
    detail: dict = {
        "id": p.id,
        "op": p.op,
        "status": p.status,
        "proposer": p.proposer,
        "session_id": p.session_id or "",
        "created_at": p.created_at,
        "reviewed_at": p.reviewed_at or "",
        "reviewer_id": p.reviewer_id or "",
        "review_note": p.review_note or "",
        "target_concept_id": p.target_concept_id or "",
        "target_facet_id": p.target_facet_id or "",
        "target_edge_id": p.target_edge_id or "",
        "payload": payload,
        "evidence": p.evidence or {},
        # 异步落盘流水线状态
        "apply_status": p.apply_status or "idle",
        "apply_error": p.apply_error or "",
        "apply_started_at": p.apply_started_at or "",
        "apply_finished_at": p.apply_finished_at or "",
    }

    # ---- op 专属上下文 ----
    if p.op == "suggest_facet_pattern":
        concept_id = (payload.get("concept_id") or p.target_concept_id or "").strip()
        if concept_id:
            concept = ConceptRepository().get_by_id(concept_id)
            if concept:
                detail["concept"] = {
                    "id": concept.id,
                    "canonical_name": concept.canonical_name,
                    "slug": concept.slug,
                    "subject": concept.subject,
                    "summary": concept.summary,
                }
                # 该概念已有的所有 facet（审核员对比"会不会重复"）
                facets = FacetRepository().list_by_concept(
                    concept_id, status="active", limit=100
                )
                detail["concept_facets"] = [
                    {
                        "id": f.id,
                        "kind": f.kind,
                        "content": f.content,
                        "confidence": f.confidence,
                        "support_count": f.support_count,
                        "origin": f.origin,
                    }
                    for f in facets
                ]
            else:
                detail["concept"] = None
                detail["concept_facets"] = []

        # 关联 observation 原文
        obs_ids = payload.get("observation_ids") or []
        obs_repo = ObservationRepository()
        obs_list = []
        for oid in obs_ids[:50]:  # 防爆
            o = obs_repo.get_by_id(oid)
            if not o:
                continue
            obs_list.append(
                {
                    "id": o.id,
                    "observation_type": o.observation_type,
                    "description": o.description,
                    "user_id": o.user_id or "",
                    "session_id": o.session_id or "",
                    "agent_confidence": o.agent_confidence,
                    "created_at": o.created_at,
                }
            )
        detail["observations"] = obs_list

    elif p.op == "suggest_missing_concept":
        # 用 concept_name 做一次 resolve，告诉审核员"是否已有近义概念"
        name = (payload.get("concept_name") or "").strip()
        if name:
            try:
                items = ConceptRepository().resolve(name, top_k=5)
                detail["resolve_hits"] = [
                    {
                        "concept_id": it.concept_id,
                        "canonical_name": it.canonical_name,
                        "slug": it.slug,
                        "match_type": it.match_type,
                        "score": it.score,
                    }
                    for it in items
                ]
            except Exception as exc:  # pylint: disable=broad-except
                logger.warning("resolve 失败 name=%s err=%s", name, exc)
                detail["resolve_hits"] = []
        else:
            detail["resolve_hits"] = []

    return detail


# ============================================================
# Approve / Reject
# ============================================================


class ReviewBody(BaseModel):
    note: str = ""


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: str,
    body: ReviewBody,
    _: str = Depends(require_admin),
):
    p = ProposalService().approve(
        proposal_id,
        reviewer_id="admin",
        review_note=body.note or "",
    )
    if not p:
        raise HTTPException(404, detail="proposal 不存在")
    return _proposal_summary(p)


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: str,
    body: ReviewBody,
    _: str = Depends(require_admin),
):
    p = ProposalService().reject(
        proposal_id,
        reviewer_id="admin",
        review_note=body.note or "",
    )
    if not p:
        raise HTTPException(404, detail="proposal 不存在")
    return _proposal_summary(p)


# ============================================================
# 异步落盘重试（仅限 apply_status='failed'）
# ============================================================


@router.post("/proposals/{proposal_id}/retry_apply")
def retry_apply_proposal(
    proposal_id: str,
    _: str = Depends(require_admin),
):
    """将一条 failed/aborted 的 approved proposal 重新踢回 queued，由 worker 重跑。

    限制：
      - status 必须是 approved
      - apply_status 必须是 failed 或 aborted（done 不允许重跑，queued/running 跳过）
    """
    repo = ProposalRepository()
    p = repo.get_by_id(proposal_id)
    if not p:
        raise HTTPException(404, detail="proposal 不存在")
    if p.status != "approved":
        raise HTTPException(
            400,
            detail=f"仅 approved 可重试，当前 status={p.status}",
        )
    if (p.apply_status or "") not in ("failed", "aborted"):
        raise HTTPException(
            400,
            detail=f"仅 apply_status=failed/aborted 可重试，当前 apply_status={p.apply_status}",
        )

    repo.mark_apply_queued(proposal_id)

    try:
        from services.apply_worker import notify_apply_pending

        notify_apply_pending()
    except Exception:  # pylint: disable=broad-except
        logger.exception("retry_apply: 通知 apply_worker 失败")

    return _proposal_summary(repo.get_by_id(proposal_id))


# ============================================================
# 单独重试 KG 同步（md 已落盘但 ingest 失败的情况）
# ============================================================

# apply_error 里 md 路径的标记格式：" | md=math/xxx.md"
_KG_FAILED_MD_RE = re.compile(r"\|\s*md=([^\s|]+)")


@router.post("/proposals/{proposal_id}/retry_kg_sync")
def retry_kg_sync(
    proposal_id: str,
    _: str = Depends(require_admin),
):
    """对 md 已落盘但 KG 同步失败的 proposal，单独重跑一次 ingest_single_md。

    适用场景：
      apply_status='done' 且 apply_error 以 'kg_sync_failed:' 开头
      （Agent 已经成功写了 .md，只是后续把 md 灌进 KG 那一步炸了）

    与 retry_apply 的区别：
      - retry_apply 把整个 proposal 推回 queued，让 Agent 重跑（会重写 .md，花钱）
      - retry_kg_sync 只把那个 .md 文件再 ingest 一次（同步、秒级、零成本）
    """
    repo = ProposalRepository()
    p = repo.get_by_id(proposal_id)
    if not p:
        raise HTTPException(404, detail="proposal 不存在")

    if p.status != "approved":
        raise HTTPException(400, detail=f"仅 approved 可重试，当前 status={p.status}")

    err = p.apply_error or ""
    if not err.startswith("kg_sync_failed:"):
        raise HTTPException(
            400,
            detail="该 proposal 不是 KG 同步失败状态（apply_error 不以 kg_sync_failed: 开头）",
        )

    m = _KG_FAILED_MD_RE.search(err)
    if not m:
        raise HTTPException(
            400,
            detail="apply_error 中未记录 md 路径，无法定位文件（可能是旧版本失败的记录，请用『重试落盘』）",
        )
    rel_md = m.group(1).strip()

    # 解析为绝对路径
    from services.apply_worker import _knowledge_root  # 复用内部函数

    if rel_md.startswith("/"):
        md_path = Path(rel_md)
    else:
        md_path = (_knowledge_root() / rel_md).resolve()

    if not md_path.exists():
        raise HTTPException(400, detail=f"md 文件不存在: {md_path}（可能已被手动删除）")

    # 跑一次单文件 ingest
    try:
        from ingest_okf import ingest_single_md

        report = ingest_single_md(md_path)
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("retry_kg_sync: ingest_single_md 抛异常 id=%s", proposal_id)
        new_err = f"kg_sync_failed: exception: {exc} | md={rel_md}"
        repo.mark_apply_finished(proposal_id, "done", new_err[:500])
        raise HTTPException(500, detail=f"重新同步失败: {exc}")

    if not report.get("ok"):
        err_msg = str(report.get("error") or "unknown")
        new_err = f"kg_sync_failed: {err_msg} | md={rel_md}"
        repo.mark_apply_finished(proposal_id, "done", new_err[:500])
        raise HTTPException(500, detail=f"重新同步失败: {err_msg}")

    # 成功 → 清掉 apply_error
    repo.mark_apply_finished(proposal_id, "done", "")
    logger.info(
        "retry_kg_sync: KG 同步成功 id=%s cid=%s action=%s",
        proposal_id,
        report.get("cid"),
        report.get("action"),
    )
    return _proposal_summary(repo.get_by_id(proposal_id))


# ============================================================
# KG 图谱可视化（admin 全图导出）
# ============================================================


@router.get("/kg/graph")
def kg_graph(
    subject: Optional[str] = None,
    include_pending: bool = False,
    _: str = Depends(require_admin),
):
    """导出 KG 全图（concept + edge），供 admin 控制台 3D 星云球渲染。

    参数：
      subject          可选学科过滤
      include_pending  是否包含 status=pending 的 concept / edge（默认仅 approved）

    返回：
      {
        "nodes": [
          {id, slug, title, subject, status, difficulty, summary,
           facet_count, in_degree, out_degree}
        ],
        "edges": [
          {id, src, dst, relation, weight, status}
        ],
        "stats": {
          "concept_count", "edge_count",
          "subjects": ["math", ...],
          "relation_types": {"prerequisite": N, ...}
        }
      }

    说明：
      - 不分页，直接全量；KG 规模上来后（万级以上）再考虑分批。
      - facet_count 指 status='active' 的 facet 数量。
      - 这里不暴露 facet 详细内容（点节点时另一接口返回）。
    """
    from kg.database import get_kg_db

    concept_status = ("approved", "pending") if include_pending else ("approved",)
    edge_status = ("approved", "pending") if include_pending else ("approved",)

    nodes: list[dict] = []
    edges: list[dict] = []
    subjects: set[str] = set()
    relation_dist: dict[str, int] = {}

    with get_kg_db() as conn:
        # ── concepts ─────────────────────────────────────────
        sql = (
            "SELECT id, slug, canonical_name, summary, subject, "
            "       difficulty, status FROM concept "
            "WHERE merged_into_id IS NULL "
            f"  AND status IN ({','.join('?' * len(concept_status))})"
        )
        params: list = list(concept_status)
        if subject:
            sql += " AND subject=?"
            params.append(subject)
        sql += " ORDER BY subject, canonical_name"
        rows = conn.execute(sql, tuple(params)).fetchall()

        # 提前批量取 facet 计数（一次 SQL 拿全部）
        facet_count_map: dict[str, int] = {}
        fc_rows = conn.execute(
            "SELECT concept_id, COUNT(*) AS c FROM facet "
            "WHERE status='active' GROUP BY concept_id"
        ).fetchall()
        for r in fc_rows:
            facet_count_map[r["concept_id"]] = r["c"]

        # 提前批量取 in/out degree
        in_deg: dict[str, int] = {}
        out_deg: dict[str, int] = {}
        deg_rows = conn.execute(
            "SELECT src_id, dst_id FROM concept_edge "
            f"WHERE status IN ({','.join('?' * len(edge_status))})",
            tuple(edge_status),
        ).fetchall()
        for r in deg_rows:
            out_deg[r["src_id"]] = out_deg.get(r["src_id"], 0) + 1
            in_deg[r["dst_id"]] = in_deg.get(r["dst_id"], 0) + 1

        valid_ids: set[str] = set()
        for r in rows:
            cid = r["id"]
            valid_ids.add(cid)
            subj = r["subject"] or ""
            if subj:
                subjects.add(subj)
            nodes.append(
                {
                    "id": cid,
                    "slug": r["slug"],
                    "title": r["canonical_name"],
                    "subject": subj,
                    "status": r["status"],
                    "difficulty": r["difficulty"] or 3,
                    "summary": (r["summary"] or "")[:200],
                    "facet_count": facet_count_map.get(cid, 0),
                    "in_degree": in_deg.get(cid, 0),
                    "out_degree": out_deg.get(cid, 0),
                }
            )

        # ── edges ────────────────────────────────────────────
        # 只取两端都在 valid_ids 中的 edge（避免悬挂边）
        e_rows = conn.execute(
            "SELECT id, src_id, dst_id, relation_type, weight, status "
            "FROM concept_edge "
            f"WHERE status IN ({','.join('?' * len(edge_status))})",
            tuple(edge_status),
        ).fetchall()
        for r in e_rows:
            if r["src_id"] not in valid_ids or r["dst_id"] not in valid_ids:
                continue
            rel = r["relation_type"]
            relation_dist[rel] = relation_dist.get(rel, 0) + 1
            edges.append(
                {
                    "id": r["id"],
                    "src": r["src_id"],
                    "dst": r["dst_id"],
                    "relation": rel,
                    "weight": float(r["weight"] or 1.0),
                    "status": r["status"],
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "concept_count": len(nodes),
            "edge_count": len(edges),
            "subjects": sorted(subjects),
            "relation_types": relation_dist,
        },
    }


@router.get("/kg/concept/{concept_id:path}/detail")
def kg_concept_detail(
    concept_id: str,
    _: str = Depends(require_admin),
):
    """点节点用：返回 concept 详情 + facets + 邻居（in/out 边）。

    路径参数使用 ``{concept_id:path}`` 转换器，以便兼容形如
    ``math/limit`` 这种带斜杠的 concept id。
    """
    from kg.repositories.edge_repo import ConceptEdgeRepository

    concept_repo = ConceptRepository()
    facet_repo = FacetRepository()
    edge_repo = ConceptEdgeRepository()

    c = concept_repo.get_by_id(concept_id)
    if not c:
        raise HTTPException(404, detail="concept 不存在")

    facets = facet_repo.list_by_concept(concept_id, status="active", limit=200)

    out_edges = edge_repo.neighbors(
        concept_id, direction="out", status="approved", limit=200
    )
    in_edges = edge_repo.neighbors(
        concept_id, direction="in", status="approved", limit=200
    )

    # 把邻居的 canonical_name 一并查出来（前端列表展示）
    neighbor_ids = {e.dst_id for e in out_edges} | {e.src_id for e in in_edges}
    name_map: dict[str, str] = {}
    if neighbor_ids:
        from kg.database import get_kg_db

        placeholders = ",".join("?" * len(neighbor_ids))
        with get_kg_db() as conn:
            rows = conn.execute(
                f"SELECT id, canonical_name FROM concept WHERE id IN ({placeholders})",
                tuple(neighbor_ids),
            ).fetchall()
        for r in rows:
            name_map[r["id"]] = r["canonical_name"]

    def _edge_to_dict(e, is_out: bool) -> dict:
        peer_id = e.dst_id if is_out else e.src_id
        return {
            "edge_id": e.id,
            "relation": e.relation_type,
            "weight": e.weight,
            "peer_id": peer_id,
            "peer_name": name_map.get(peer_id, ""),
            "direction": "out" if is_out else "in",
        }

    # alias 兼容两种来源：可能是 ConceptAlias 对象（含 name 字段），
    # 也可能直接是字符串列表。这里统一抽出可读的字符串。
    alias_strs: list[str] = []
    for a in c.aliases or []:
        if isinstance(a, str):
            alias_strs.append(a)
        elif hasattr(a, "name"):
            alias_strs.append(a.name)
        elif hasattr(a, "model_dump"):
            d = a.model_dump()
            alias_strs.append(d.get("name") or d.get("alias") or str(d))
        else:
            alias_strs.append(str(a))

    # 字段平铺到顶层，方便前端直接渲染
    return {
        "id": c.id,
        "cid": c.id,
        "slug": c.slug,
        "title": c.canonical_name,
        "canonical_name": c.canonical_name,
        "is_canonical": True,  # 进入此接口的 concept 都是规范节点（merged_into_id 为空）
        "aliases": alias_strs,
        "summary": c.summary,
        "subject": c.subject,
        "difficulty": c.difficulty,
        "status": c.status,
        "tags": c.tags,
        "facets": [
            {
                "id": f.id,
                "kind": f.kind,
                "content": f.content,
                "confidence": f.confidence,
                "support_count": f.support_count,
                "origin": f.origin,
            }
            for f in facets
        ],
        "neighbors": [_edge_to_dict(e, True) for e in out_edges]
        + [_edge_to_dict(e, False) for e in in_edges],
    }
