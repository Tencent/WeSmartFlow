"""
文档路由（上传 + 提取节点 + 节点挂接 + 文件读取）。

本层只负责：
  - 接收 HTTP / form 参数
  - 调用 DocumentService 执行业务
  - 把 Service 抛出的业务异常翻译成 HTTPException

文件读取走两个统一端点：
  - GET /api/documents/{doc_id}/raw           — 主资源
  - GET /api/documents/{doc_id}/asset/{sub}   — 同目录伴生文件
"""

from __future__ import annotations

import base64
import html
import io
import json
import logging
import mimetypes
import re
import zipfile
from pathlib import Path
from urllib.parse import quote, unquote

from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    Request,
    UploadFile,
    BackgroundTasks,
    Body,
)
from fastapi.responses import FileResponse, StreamingResponse

from models.document import DocumentSchema, DocumentBrief
from services import DocumentService
from services.document_service import (
    DocumentNotFound,
    DocumentNotReady,
    InvalidUpload,
    NodeAlreadyLinked,
    NodeNotFound,
)
from services.document_resolver import (
    AssetPathInvalid,
    DocumentNotFound as ResolverNotFound,
    resolve_asset,
    resolve_main,
)
from utils.file_ticket import MAX_TICKET_MINUTES, create_file_ticket
from utils.web_auth import COOKIE_NAME, get_user_from_request_flexible
from dependencies import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["documents"])

_GENERATED_PDF_FILE_TYPES = {"pdf_card", "chapter_pdf"}
_BAD_PDF_GUIDE_MARKERS = (
    "PDF二进制",
    "PDF 二进制",
    "FlateDecode",
    "xref",
    "文件头",
    "交叉引用",
    "电子取证",
    "解压",
    "字体及元数据",
)


# ── MIME / 响应辅助 ──────────────────────────────────────────────────

_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
    ".tex": "text/plain; charset=utf-8",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".svg": "image/svg+xml",
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".mp4": "video/mp4",
}


def _infer_mime(path: Path) -> str:
    return _MIME_TYPES.get(path.suffix.lower(), "application/octet-stream")


_DOWNLOAD_SUFFIX_BY_FILE_TYPE = {
    "html_card": ".html",
    "viz": ".html",
    "pdf_card": ".pdf",
    "md_note": ".md",
    "course_outline": ".json",
    "course_plan": ".md",
    "chapter_overview": ".md",
    "chapter_pdf": ".pdf",
    "chapter_exercises": ".md",
    "chapter_audio": ".zip",
    "chapter_notes": ".json",
}


def _safe_download_filename(title: str, fallback: str) -> str:
    name = (title or fallback or "document").strip()
    name = re.sub(r'[\\/:*?"<>|\r\n]+', "_", name)
    return name.strip(" .") or "document"


def _download_filename(
    title: str, file_type: str, file_name: str, abs_path: Path
) -> str:
    suffix = (
        _DOWNLOAD_SUFFIX_BY_FILE_TYPE.get(file_type)
        or abs_path.suffix
        or Path(file_name).suffix
    )
    if not suffix:
        suffix = ".txt"
    if not suffix.startswith("."):
        suffix = f".{suffix}"
    stem = _safe_download_filename(title, abs_path.stem or file_name)
    if stem.lower().endswith(suffix.lower()):
        return stem
    return f"{stem}{suffix}"


def _zip_audio_package(abs_path: Path, filename: str) -> StreamingResponse:
    buffer = io.BytesIO()
    audio_dir = abs_path.parent
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(abs_path, arcname=abs_path.name)
        for child in sorted(audio_dir.iterdir()):
            if child.is_file() and child != abs_path:
                zf.write(child, arcname=child.name)
    buffer.seek(0)
    encoded = quote(filename)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded}",
    }
    return StreamingResponse(
        buffer,
        media_type="application/zip",
        headers=headers,
    )


def _download_headers(filename: str) -> dict[str, str]:
    encoded = quote(filename)
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded}"}


def _stream_text_download(
    content: str, filename: str, media_type: str
) -> StreamingResponse:
    payload = content.encode("utf-8")
    headers = _download_headers(filename)
    headers["Content-Length"] = str(len(payload))
    return StreamingResponse(
        io.BytesIO(payload),
        media_type=media_type,
        headers=headers,
    )


def _resolve_download_asset(base_dir: Path, raw_src: str) -> Path | None:
    if not raw_src or raw_src.startswith("data:"):
        return None
    src = unquote(raw_src.split("?", 1)[0].split("#", 1)[0])
    asset_marker = "/asset/"
    if asset_marker in src:
        src = src.split(asset_marker, 1)[1]
    elif src.startswith(("http://", "https://", "//", "/")):
        return None
    target = (base_dir / src).resolve()
    try:
        if not target.is_relative_to(base_dir.resolve()):
            return None
    except AttributeError:
        if not str(target).startswith(str(base_dir.resolve())):
            return None
    return target if target.is_file() else None


def _inline_html_assets(abs_path: Path) -> str:
    """把 HTML 中本地/文档 asset 图片内嵌为 data URL，下载后可离线打开。"""
    html = abs_path.read_text("utf-8")
    base_dir = abs_path.parent

    def repl(match: re.Match) -> str:
        attr = match.group("attr")
        quote_char = match.group("quote")
        src = match.group("src")
        asset_path = _resolve_download_asset(base_dir, src)
        if not asset_path:
            return match.group(0)
        mime = mimetypes.guess_type(str(asset_path))[0] or "application/octet-stream"
        if not mime.startswith("image/"):
            return match.group(0)
        data = base64.b64encode(asset_path.read_bytes()).decode("ascii")
        return f"{attr}={quote_char}data:{mime};base64,{data}{quote_char}"

    return re.sub(
        r'(?P<attr>src)=(?P<quote>["\'])(?P<src>[^"\']+)(?P=quote)',
        repl,
        html,
        flags=re.IGNORECASE,
    )


def _build_standalone_viz_html(abs_path: Path, title: str) -> str:
    """把 viz.js 包装成用户双击即可打开的独立 HTML。"""
    from config import EDUVIZ_SDK_PATH

    code = abs_path.read_text("utf-8")
    sdk = EDUVIZ_SDK_PATH.read_text("utf-8") if EDUVIZ_SDK_PATH.exists() else ""
    safe_title = html.escape(title or "交互可视化")
    sdk_script = "<" + "script>" + sdk + "</" + "script>"
    user_code_json = json.dumps(code).replace("<", "\\u003c")
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{safe_title}</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.css">
  <script src="https://cdn.jsdelivr.net/npm/katex@0.16.9/dist/katex.min.js"></script>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    html, body {{ min-height: 100%; background: #0e0f14; color: #eeeef0; font-family: Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; }}
    body {{ padding: 16px; }}
    .export-title {{ margin: 0 0 12px; font-size: 18px; font-weight: 700; }}
    .export-hint {{ margin: 0 0 16px; color: #9394a5; font-size: 12px; }}
    .ev-error {{ padding: 12px 16px; margin: 8px 0; background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.3); border-radius: 8px; color: #ef4444; font-size: 12px; font-family: monospace; white-space: pre-wrap; word-break: break-all; }}
    canvas {{ border-radius: 8px; display: block; }}
    svg {{ overflow: visible; }}
  </style>
</head>
<body>
  <h1 class="export-title">{safe_title}</h1>
  <p class="export-hint">这是从 WeSmartFlow 导出的交互可视化文件。若使用了第三方图形库，请保持联网以加载依赖。</p>
  {sdk_script}
  <script>
    document.documentElement.setAttribute('data-theme', 'dark');
    if (window.EduViz && typeof window.EduViz.setTheme === 'function') {{
      window.EduViz.setTheme('dark');
    }}
    var AsyncFunction = Object.getPrototypeOf(async function() {{}}).constructor;
    function showError(reason) {{
      var div = document.createElement('div');
      div.className = 'ev-error';
      div.textContent = reason && reason.message ? reason.message : String(reason);
      document.body.prepend(div);
    }}
    window.onerror = function(msg, url, line, col, err) {{ showError(err || msg); return true; }};
    window.onunhandledrejection = function(event) {{ showError(event.reason); event.preventDefault(); }};
    Promise.resolve().then(function() {{ return new AsyncFunction({user_code_json})(); }}).catch(showError);
  </script>
</body>
</html>"""


def _download_prepared_document(rf, filename: str) -> StreamingResponse | FileResponse:
    if rf.doc.file_type == "chapter_audio":
        return _zip_audio_package(rf.abs_path, filename)
    if rf.doc.file_type == "html_card":
        return _stream_text_download(
            _inline_html_assets(rf.abs_path),
            filename,
            "text/html; charset=utf-8",
        )
    if rf.doc.file_type == "viz":
        return _stream_text_download(
            _build_standalone_viz_html(rf.abs_path, rf.doc.title),
            filename,
            "text/html; charset=utf-8",
        )
    return _file_response(rf.abs_path, download_filename=filename)


def _is_https_request(request: Request | None) -> bool:
    if request is None:
        return False
    forwarded = (request.headers.get("x-forwarded-proto") or "").split(",")[0]
    return request.url.scheme == "https" or forwarded.strip().lower() == "https"


def _file_response(
    abs_path: Path,
    *,
    query_token: str | None = None,
    download_filename: str | None = None,
    doc_id: str | None = None,
    request: Request | None = None,
) -> FileResponse:
    """统一的文件响应：自动推断 MIME，可选写 Cookie / Content-Disposition。"""
    headers: dict[str, str] = {}
    # Generated PDFs may be replaced in place by an audited resume.  Never let
    # the browser replay older bytes for the same document URL.
    if abs_path.suffix.lower() == ".pdf":
        headers["Cache-Control"] = "no-store, max-age=0"
        headers["Pragma"] = "no-cache"
    if query_token and doc_id:
        # iframe / web-view 首次以 ?ticket= 打开主资源后，子资源请求由 cookie 兜底。
        # Cookie 只写入单文档票据，且路径限定在该文档下。
        cookie = (
            f"{COOKIE_NAME}={query_token}; "
            f"Path=/api/documents/{quote(doc_id, safe='')}/; HttpOnly; SameSite=Lax"
        )
        if _is_https_request(request):
            cookie += "; Secure"
        headers["Set-Cookie"] = cookie
    return FileResponse(
        path=abs_path,
        media_type=_infer_mime(abs_path),
        filename=download_filename,
        headers=headers,
    )


# ── 文档列表 / 详情 / 上传 / 删除 / 节点挂接 ─────────────────────────


@router.get("", response_model=list[DocumentBrief])
def list_documents(user_id: str = Depends(get_current_user)):
    return DocumentService().list_documents(user_id)


def _is_bad_generated_pdf_guide(guide: dict) -> bool:
    text = "\n".join(
        str(guide.get(key, ""))
        for key in ("basics", "order", "difficulties", "estimated")
    )
    return any(marker in text for marker in _BAD_PDF_GUIDE_MARKERS)


def _extract_guide_json(text: str) -> dict:
    """从 LLM 返回文本中健壮地抽取学习建议 JSON。

    容错：markdown 代码块包裹、单引号 key/value、尾逗号、字段缺引号。
    全部失败时返回 {}。
    """
    import json as _json
    import re as _re

    # 1) 剥 markdown 代码块
    m_code = _re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, _re.DOTALL)
    if m_code:
        text = m_code.group(1)
    # 2) 直接找最外层大括号
    m = _re.search(r"\{.*\}", text, _re.DOTALL)
    if not m:
        return {}
    raw = m.group(0)
    # 3) 依次尝试：原样 / 单引号转双引号 / 去尾逗号
    candidates = [raw]
    candidates.append(raw.replace("'", '"'))
    candidates.append(_re.sub(r",\s*([}\]])", r"\1", raw))
    candidates.append(_re.sub(r",\s*([}\]])", r"\1", raw.replace("'", '"')))
    for cand in candidates:
        try:
            obj = _json.loads(cand)
            if isinstance(obj, dict):
                return obj
        except Exception:
            continue
    return {}


@router.get("/{doc_id}/study-guide")
async def get_study_guide(doc_id: str, user_id: str = Depends(get_current_user)):
    """返回已生成的学习建议（issue #1 系列：上传后先告诉用户怎么学）。"""
    try:
        doc = DocumentService()._assert_doc_owner(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="文档不存在") from None
    guide_path = Path(doc.get_file_path()).parent / "study_guide.json"
    if not guide_path.exists():
        return {"generated": False}
    import json as _json

    guide = _json.loads(guide_path.read_text("utf-8"))
    if doc.file_type in _GENERATED_PDF_FILE_TYPES and _is_bad_generated_pdf_guide(
        guide
    ):
        return {"generated": False}
    return {"generated": True, "guide": guide}


@router.post("/{doc_id}/study-guide")
async def generate_study_guide(doc_id: str, user_id: str = Depends(get_current_user)):
    """生成学习建议：适合什么基础 / 先看哪几节 / 哪里难（一次性 LLM 调用）。"""
    try:
        doc = DocumentService()._assert_doc_owner(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(status_code=404, detail="文档不存在") from None
    guide_path = Path(doc.get_file_path()).parent / "study_guide.json"
    if guide_path.exists():
        import json as _json

        guide = _json.loads(guide_path.read_text("utf-8"))
        if (
            doc.file_type not in _GENERATED_PDF_FILE_TYPES
            or not _is_bad_generated_pdf_guide(guide)
        ):
            return {"generated": True, "guide": guide}
        guide_path.unlink(missing_ok=True)

    # 读文档内容前 6000 字（够 LLM 判断基础/顺序/难点）
    try:
        content = DocumentService().get_content(user_id, doc_id).get("content", "")
    except Exception as e:  # pylint: disable=broad-except
        raise HTTPException(status_code=400, detail=f"文档内容读取失败: {e}") from e
    if not content or len(content.strip()) < 50:
        raise HTTPException(status_code=400, detail="文档内容为空，无法生成学习建议")

    from services.llm_factory import get_llm

    # 学习规划是用户触发的操作：走用户额度（拦截 + 记账）
    llm = get_llm(user_id, scene="chat")
    prompt = (
        "根据以下资料内容，输出一份简短的学习建议，"
        "帮助用户决定怎么学这份材料。只能是 JSON：\n"
        '{"basics": "适合什么基础的读者（50字内）", '
        '"order": "建议的阅读/学习顺序（80字内）", '
        '"difficulties": "可能的难点提示（80字内）", '
        '"estimated": "预计学习时长（20字内）"}\n\n'
        f"资料内容：\n{content[:6000]}"
    )
    try:
        resp = llm.think(
            messages=[
                {"role": "system", "content": "你是学习规划助手，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ]
        )
        text = getattr(resp, "content", "") or ""
        guide = _extract_guide_json(text)
    except Exception as e:  # pylint: disable=broad-except
        raise HTTPException(status_code=502, detail=f"学习建议生成失败: {e}") from e

    if not guide.get("basics"):
        raise HTTPException(
            status_code=502, detail="学习建议生成失败：模型未返回有效内容"
        )

    import json as _json

    guide_path.write_text(_json.dumps(guide, ensure_ascii=False, indent=2), "utf-8")
    return {"generated": True, "guide": guide}


@router.get("/{doc_id}", response_model=DocumentSchema)
def get_document(doc_id: str, user_id: str = Depends(get_current_user)):
    try:
        return DocumentService().get_document(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")


@router.post("/upload", response_model=DocumentSchema, status_code=201)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user),
):
    """上传文档（单文件），后台自动触发提取。"""
    content = await file.read()
    try:
        return await DocumentService().upload(
            user_id=user_id,
            filename=file.filename,
            content=content,
            background_tasks=background_tasks,
        )
    except InvalidUpload as e:
        raise HTTPException(400, str(e))


@router.post("/{doc_id}/extract")
async def trigger_extract(
    doc_id: str,
    background_tasks: BackgroundTasks,
    user_id: str = Depends(get_current_user),
):
    """手动触发（重新）提取。"""
    try:
        return DocumentService().trigger_extract(user_id, doc_id, background_tasks)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")


@router.get("/{doc_id}/content")
async def get_document_content(doc_id: str, user_id: str = Depends(get_current_user)):
    """获取文档内容（支持分段获取）。"""
    try:
        return DocumentService().get_content(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except DocumentNotReady:
        raise HTTPException(400, "文档尚未处理完成")


# ── 文件读取（核心两个接口） ──────────────────────────────────────────


async def _get_document_raw(doc_id: str, request: Request):
    """读取文档主资源。

    URL 参数：
      - ``ticket`` — 可选；单文档短时效票据，为 iframe / web-view 兜底鉴权，
        命中后会写限定在该文档路径下的 cookie。登录 token 不再允许放进 URL。
      - ``download=1`` — 强制 ``Content-Disposition: attachment``，触发浏览器下载。
    """
    user_id, query_ticket = get_user_from_request_flexible(request, doc_id)
    try:
        rf = resolve_main(doc_id, user_id)
    except ResolverNotFound:
        raise HTTPException(404, "文件不存在")

    download = request.query_params.get("download") in {"1", "true", "yes"}
    download_filename = _download_filename(
        rf.doc.title, rf.doc.file_type, rf.doc.file_name, rf.abs_path
    )
    if download:
        return _download_prepared_document(rf, download_filename)
    return _file_response(
        rf.abs_path,
        query_token=query_ticket,
        doc_id=doc_id,
        request=request,
    )


@router.get("/{doc_id}/raw", operation_id="get_document_raw")
async def get_document_raw(doc_id: str, request: Request):
    return await _get_document_raw(doc_id, request)


@router.head("/{doc_id}/raw", include_in_schema=False)
async def head_document_raw(doc_id: str, request: Request):
    return await _get_document_raw(doc_id, request)


@router.post("/{doc_id}/ticket", operation_id="create_document_ticket")
def create_document_ticket(
    doc_id: str,
    minutes: int = 30,
    user_id: str = Depends(get_current_user),
):
    """为 iframe / web-view / 分享链接签发单文档、短时效访问票据。

    票据只能读取 ``doc_id`` 这一个文档（含其伴生资源），通过 ``?ticket=`` 使用。
    """
    try:
        resolve_main(doc_id, user_id)
    except ResolverNotFound:
        raise HTTPException(404, "文件不存在")
    minutes = max(1, min(minutes, MAX_TICKET_MINUTES))
    return {
        "ticket": create_file_ticket(user_id, doc_id, expires_in_minutes=minutes),
        "expires_in": minutes * 60,
    }


async def _get_document_asset(doc_id: str, sub_path: str, request: Request):
    """读取文档主资源同目录下的伴生文件。

    例如 HTML 卡片 ``card.html`` 内嵌图片：
      ``/api/documents/{doc_id}/asset/images/cover.png``

    沉浸式课程章节音频帧：
      ``/api/documents/{audio_doc_id}/asset/frame_001.wav``
    """
    user_id, query_ticket = get_user_from_request_flexible(request, doc_id)
    try:
        rf = resolve_asset(doc_id, sub_path, user_id)
    except (ResolverNotFound, AssetPathInvalid):
        raise HTTPException(404, "文件不存在")
    return _file_response(
        rf.abs_path, query_token=query_ticket, doc_id=doc_id, request=request
    )


@router.get("/{doc_id}/asset/{sub_path:path}", operation_id="get_document_asset")
async def get_document_asset(doc_id: str, sub_path: str, request: Request):
    return await _get_document_asset(doc_id, sub_path, request)


@router.head("/{doc_id}/asset/{sub_path:path}", include_in_schema=False)
async def head_document_asset(doc_id: str, sub_path: str, request: Request):
    return await _get_document_asset(doc_id, sub_path, request)


# ── 删除 / 节点挂接 ──────────────────────────────────────────────────


@router.delete("/{doc_id}", status_code=204)
def delete_document(doc_id: str, user_id: str = Depends(get_current_user)):
    try:
        DocumentService().delete(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except PermissionError as e:
        raise HTTPException(403, str(e))


@router.get("/{doc_id}/nodes")
async def get_document_nodes(doc_id: str, user_id: str = Depends(get_current_user)):
    """获取文档关联的知识节点。"""
    try:
        return DocumentService().list_document_nodes(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")


@router.get("/nodes/{node_id}/documents")
async def get_node_documents(node_id: str, user_id: str = Depends(get_current_user)):
    """获取知识节点关联的文档。"""
    try:
        return DocumentService().list_node_documents(user_id, node_id)
    except NodeNotFound:
        raise HTTPException(404, "知识节点不存在")


@router.get("/{doc_id}/summary")
async def get_document_summary(doc_id: str, user_id: str = Depends(get_current_user)):
    """获取文档摘要信息。"""
    try:
        return DocumentService().get_summary(user_id, doc_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except DocumentNotReady:
        raise HTTPException(400, "文档尚未处理完成")


@router.post("/{doc_id}/add_node")
async def add_node_to_document(
    doc_id: str,
    node_id: str = Body(..., embed=True),
    user_id: str = Depends(get_current_user),
):
    """为文档手动添加现有节点。"""
    try:
        return DocumentService().add_node(user_id, doc_id, node_id)
    except DocumentNotFound:
        raise HTTPException(404, "文档不存在")
    except NodeNotFound:
        raise HTTPException(404, "节点不存在")
    except NodeAlreadyLinked:
        raise HTTPException(400, "节点已关联到该文档")
