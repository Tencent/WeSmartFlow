"""Normalize and validate static card fragments without truncating teaching content."""

from __future__ import annotations

import html
import re
import shutil
from copy import deepcopy
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit

from lxml import etree
from lxml import html as dom


class CardValidationError(ValueError):
    """The writer must revise the card before it can be published."""


_TAGS = set(
    "article section div span h1 h2 h3 h4 h5 h6 p strong em b i u small "
    "br hr ul ol li blockquote table thead tbody tfoot tr th td img figure "
    "figcaption pre code sub sup a dl dt dd".split()
)
_DROP = set(
    "script style iframe object embed svg canvas form input button textarea "
    "select video audio source link meta base title head noscript template".split()
)
_CLASSES = set(
    "card-title card-subtitle card-body highlight-box tag divider "
    "formula-center formula-block stat-row stat-card num label flow-row "
    "flow-node flow-arrow compare-table progress-bar-wrap progress-bar "
    "progress-label progress-val two-col col-item step-list step-item "
    "card-image card-image-caption".split()
)
_DEFAULT_CLASSES = {
    "p": "card-body",
    "h2": "card-subtitle",
    "h3": "card-subtitle",
    "table": "compare-table",
    "blockquote": "highlight-box",
    "figcaption": "card-image-caption",
    "hr": "divider",
}
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}


def clean_body_html(raw: str) -> str:
    """Remove an outer Markdown fence, preserving Unicode and math verbatim."""
    raw = raw.strip()
    match = re.fullmatch(r"```(?:html)?\s*\n?([\s\S]*?)\n?```", raw, re.I)
    return match.group(1).strip() if match else raw


def image_source(src: str, work_dir: Path) -> Path:
    """Resolve only generated images, including nested, relative and /tmp aliases."""
    url = urlsplit(src)
    if (
        not src
        or url.scheme not in ("", "file")
        or url.netloc
        or url.query
        or url.fragment
    ):
        raise CardValidationError("插图必须引用本次图片工具返回的本地文件路径")
    source = Path(unquote(url.path))
    if not source.is_absolute():
        source = work_dir / source
    source = source.resolve()
    if (
        not source.is_relative_to(work_dir.resolve())
        or not source.is_file()
        or source.suffix.lower() not in _IMAGE_EXTENSIONS
    ):
        raise CardValidationError(
            "插图不存在或不在本次工作目录，请使用已生成的图片，生成失败时删除图片引用"
        )
    return source


def _serialize(root) -> str:
    return (
        html.escape(root.text or "")
        + "".join(
            dom.tostring(child, encoding="unicode", method="html") for child in root
        )
    ).strip()


def prepare_card_html(
    raw: str, *, title: str, work_dir: Path | None = None
) -> tuple[str, list[str]]:
    """Repair presentation only; reject invalid/overfull content for a bounded rewrite.

    Never shorten prose, slice LaTeX, drop excess teaching blocks, or copy the
    instruction into the card to fill space. The writer owns those decisions.
    """
    raw = clean_body_html(raw)
    if not raw or len(raw) > 100_000:
        raise CardValidationError("请输出完整的 HTML 卡片片段，内容不能为空或过长")
    try:
        document = dom.document_fromstring(
            raw, parser=dom.HTMLParser(remove_comments=True, no_network=True)
        )
    except (etree.ParserError, ValueError) as exc:
        raise CardValidationError("HTML 无法解析，请重新输出卡片片段") from exc
    root = document.find("body")
    if root is None:
        raise CardValidationError("未找到卡片正文")
    issues = []
    for element in list(root.iterdescendants()):
        if not isinstance(element.tag, str) or element.getparent() is None:
            continue
        if element.tag in _DROP:
            element.drop_tree()
            issues.append("移除自定义脚本或样式")
            continue
        if element.tag not in _TAGS:
            element.drop_tag()
            continue
        classes = [c for c in element.get("class", "").split() if c in _CLASSES]
        attrs = {}
        if element.tag == "img":
            classes = ["card-image"]
            attrs.update(src=element.get("src", ""), alt=element.get("alt", ""))
        if not classes and element.tag in _DEFAULT_CLASSES:
            classes = [_DEFAULT_CLASSES[element.tag]]
        if classes:
            attrs["class"] = " ".join(dict.fromkeys(classes))
        if element.tag == "a":
            href = element.get("href", "").strip()
            if urlsplit(href).scheme in ("http", "https"):
                attrs.update(href=href, target="_blank", rel="noopener noreferrer")
        if element.tag in ("td", "th"):
            for key in ("colspan", "rowspan"):
                value = element.get(key, "")
                if value.isdigit() and 1 <= int(value) <= 5:
                    attrs[key] = value
        # The sole supported inline declaration is a numeric progress value.
        if "progress-bar" in classes:
            match = re.search(
                r"(?:^|;)\s*--pct\s*:\s*(\d+(?:\.\d+)?)%\s*(?:;|$)",
                element.get("style", ""),
            )
            if match and 0 <= float(match.group(1)) <= 100:
                attrs["style"] = f"--pct: {match.group(1)}%"
            else:
                raise CardValidationError(
                    '进度条缺少真实百分比，请使用 style="--pct: 0到100之间的数值%"，不要编造数据'
                )
        if element.get("style") != attrs.get("style"):
            issues.append("统一预设组件样式")
        element.attrib.clear()
        element.attrib.update(attrs)

    # A flow node is a flex container: per CSS itemization rules every text run
    # and inline element becomes a separate flex item squeezed onto one row —
    # prose shrinks to min-content (one CJK glyph per line) while atomic KaTeX
    # spans overflow and paint over the neighbouring fragments. Collapsing the
    # node content into a single child restores normal inline flow (<br> and
    # line wrapping work again) while keeping the flex vertical centering.
    for node in root.find_class("flow-node"):
        if len(node) == 1 and node[0].tag == "span" and not (node.text or "").strip():
            continue  # already wrapped
        if not (node.text or "").strip() and not len(node):
            continue  # nothing to wrap
        wrapper = dom.Element("span")
        wrapper.text = node.text
        node.text = None
        for child in list(node):
            wrapper.append(child)
        node.append(wrapper)
        issues.append("流程节点内容包裹为单一条目")

    # Validate actual teaching content before adding a missing title.
    titles = root.find_class("card-title")
    headings = list(root.iter("h1"))
    if not titles and headings:
        headings[0].set("class", "card-title")
        titles = [headings[0]]
    for element in list(
        dict.fromkeys(titles[1:] + [h for h in headings if h not in titles[:1]])
    ):
        element.tag = "h2"
        element.set("class", "card-subtitle")
        issues.append("统一标题层级")
    if not titles:
        heading = dom.Element("h1", {"class": "card-title"})
        heading.text = title
        root.insert(0, heading)
        titles = [heading]
        issues.append("补充标题")
    if not titles[0].text_content().strip():
        titles[0].text = title

    # Plain prose masquerading as an HTML response is not a usable card.
    content_root = deepcopy(root)
    for element in list(content_root.iterdescendants()):
        if (
            element.tag in ("h1", "h2", "h3", "h4", "h5", "h6")
            or "card-title" in element.classes
        ):
            element.drop_tree()
    content_nodes = list(content_root.iterdescendants())
    if not any(e.text_content().strip() or e.tag == "img" for e in content_nodes):
        raise CardValidationError(
            "卡片只有标题或纯文本，请补充解释、例子或一个教学组件"
        )

    errors = []
    limits = {
        "card-subtitle": 3,
        "card-body": 3,
        "highlight-box": 2,
        "flow-row": 1,
        "compare-table": 1,
        "step-list": 1,
        "stat-row": 1,
        "two-col": 1,
        "card-image": 1,
    }
    for name, limit in limits.items():
        if len(root.find_class(name)) > limit:
            errors.append(f"{name} 最多 {limit} 个，请合并内容而不是截断句子")
    if (
        len(root.find_class("formula-center")) + len(root.find_class("formula-block"))
        > 4
    ):
        errors.append("公式块合计最多 4 个")
    for parent, child, limit in [
        ("flow-row", "flow-node", 5),
        ("step-list", "step-item", 6),
        ("stat-row", "stat-card", 4),
        ("two-col", "col-item", 4),
    ]:
        for group in root.find_class(parent):
            if len(group.find_class(child)) > limit:
                errors.append(f"{parent} 内的 {child} 最多 {limit} 个")
    for table in root.iter("table"):
        if len(list(table.iter("tr"))) > 5:
            errors.append("表格最多 5 行（含表头）")
        if any(len(row.xpath("./th|./td")) > 3 for row in table.iter("tr")):
            errors.append("表格最多 3 列，更多对象请改为列表")
    if len(re.sub(r"\s+", " ", root.text_content()).strip()) > 2600:
        errors.append(
            "单张卡片内容过多，请聚焦一个知识点并保留完整推导、公式和必要条件"
        )
    for image in root.iter("img"):
        if work_dir is not None:
            image_source(image.get("src", ""), work_dir)
    if errors:
        raise CardValidationError("；".join(errors))
    return _serialize(root), list(dict.fromkeys(issues))


def archive_card_images(
    body_html: str, *, work_dir: Path, card_dir: Path, card_id: str
) -> str:
    """Copy referenced images only and rewrite src attributes, not prose or captions."""
    root = dom.fragment_fromstring(body_html, create_parent="div")
    for image in root.iter("img"):
        source = image_source(image.get("src", ""), work_dir)
        relative = Path("images") / source.relative_to(work_dir.resolve())
        destination = card_dir / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        image.set(
            "src",
            f"/api/documents/{card_id}/asset/{quote(relative.as_posix(), safe='/')}",
        )
    return _serialize(root)
