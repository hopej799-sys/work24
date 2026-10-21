"""운영 가이드: Notion 페이지를 읽어 HTML로 렌더링.

가이드는 Notion에서 수정하면 배포 없이 앱에 반영된다 (캐시 60초).
페이지에 work24-monitor 통합(API 토큰)이 '연결'되어 있어야 읽을 수 있다.
"""
import html
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from notion_store import API, _request

# 고용24 모니터링 결과 조회 — CS 사용 가이드
GUIDE_PAGE_ID = "4007d8322b04812f8fe1fd9c2d270be7"

_COLORS = {
    "gray": "#787774", "brown": "#9f6b53", "orange": "#d9730d", "yellow": "#cb912f",
    "green": "#448361", "blue": "#337ea9", "purple": "#9065b0", "pink": "#c14c8a", "red": "#d44c47",
}
_BG = {
    "gray": "#f1f1ef", "brown": "#f4eeee", "orange": "#fbecdd", "yellow": "#fbf3db",
    "green": "#edf3ec", "blue": "#e7f3f8", "purple": "#f6f3f9", "pink": "#faf1f5", "red": "#fdebec",
}


def _fetch_children(block_id):
    out, cursor = [], None
    while True:
        url = f"{API}/blocks/{block_id}/children?page_size=100"
        if cursor:
            url += f"&start_cursor={cursor}"
        data = _request("GET", url)
        out.extend(data["results"])
        if not data.get("has_more"):
            return out
        cursor = data["next_cursor"]


def _tree(block_id, pool):
    """블록 트리를 한 번에 받아 둔다. 깊이별로 하위 블록을 병렬 요청 (순차 요청 시 첫 로딩 15초+)."""
    root = _fetch_children(block_id)
    level = [b for b in root if b.get("has_children")]
    while level:
        for b, kids in zip(level, pool.map(lambda x: _fetch_children(x["id"]), level)):
            b["_children"] = kids
        level = [k for b in level for k in b["_children"] if k.get("has_children")]
    return root


def _children(block_id_or_block):
    return block_id_or_block.get("_children", [])


def _rich(items):
    parts = []
    for t in items or []:
        s = html.escape(t.get("plain_text", "")).replace("\n", "<br>")
        a = t.get("annotations", {})
        if a.get("code"):
            s = f"<code>{s}</code>"
        if a.get("bold"):
            s = f"<strong>{s}</strong>"
        if a.get("italic"):
            s = f"<em>{s}</em>"
        if a.get("strikethrough"):
            s = f"<s>{s}</s>"
        if a.get("underline"):
            s = f"<u>{s}</u>"
        color = a.get("color", "default")
        if color.endswith("_background"):
            s = f'<span style="background:{_BG.get(color[:-11], "")}">{s}</span>'
        elif color in _COLORS:
            s = f'<span style="color:{_COLORS[color]}">{s}</span>'
        href = t.get("href")
        if href:
            s = f'<a href="{html.escape(href)}" target="_blank">{s}</a>'
        parts.append(s)
    return "".join(parts)


def _render(blocks):
    out, i = [], 0
    while i < len(blocks):
        b = blocks[i]
        t = b["type"]
        # 연속된 목록 항목은 하나의 ul/ol로 묶는다
        if t in ("bulleted_list_item", "numbered_list_item"):
            tag = "ul" if t == "bulleted_list_item" else "ol"
            items = []
            while i < len(blocks) and blocks[i]["type"] == t:
                li = blocks[i]
                kids = _render(_children(li))
                items.append(f"<li>{_rich(li[t]['rich_text'])}{kids}</li>")
                i += 1
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        d = b.get(t, {})
        kids = _render(_children(b)) if t != "table" else ""
        if t in ("heading_1", "heading_2", "heading_3"):
            n = {"heading_1": 2, "heading_2": 3, "heading_3": 4}[t]
            out.append(f"<h{n}>{_rich(d['rich_text'])}</h{n}>{kids}")
        elif t == "paragraph":
            out.append(f"<p>{_rich(d['rich_text']) or '&nbsp;'}</p>{kids}")
        elif t == "callout":
            icon = (d.get("icon") or {}).get("emoji", "")
            bg = _BG.get(d.get("color", "").replace("_background", ""), "#f1f1ef")
            out.append(f'<div class="callout" style="background:{bg}"><span class="ci">{icon}</span>'
                       f'<div>{_rich(d["rich_text"])}{kids}</div></div>')
        elif t == "quote":
            out.append(f"<blockquote>{_rich(d['rich_text'])}{kids}</blockquote>")
        elif t == "toggle":
            out.append(f"<details><summary>{_rich(d['rich_text'])}</summary>{kids}</details>")
        elif t == "to_do":
            mark = "☑" if d.get("checked") else "☐"
            out.append(f"<p>{mark} {_rich(d['rich_text'])}</p>{kids}")
        elif t == "code":
            out.append(f"<pre>{_rich(d['rich_text'])}</pre>")
        elif t == "divider":
            out.append("<hr>")
        elif t == "table":
            rows = _children(b)
            head_row, head_col = d.get("has_row_header"), d.get("has_column_header")
            trs = []
            for r, row in enumerate(rows):
                cells = []
                for c, cell in enumerate(row["table_row"]["cells"]):
                    tag = "th" if (head_row and r == 0) or (head_col and c == 0) else "td"
                    cells.append(f"<{tag}>{_rich(cell)}</{tag}>")
                trs.append(f"<tr>{''.join(cells)}</tr>")
            out.append(f"<table>{''.join(trs)}</table>")
        elif t == "image":
            src = d.get(d.get("type", ""), {}).get("url", "")
            out.append(f'<img src="{html.escape(src)}" style="max-width:100%">')
        elif t == "column_list":
            out.append(f'<div class="cols">{kids}</div>')
        elif t == "column":
            out.append(f"<div>{kids}</div>")
        else:
            out.append(kids)
        i += 1
    return "".join(out)


CSS = """
<style>
.nguide{font-size:15px;line-height:1.7;color:#37352f;max-width:960px}
.nguide h2{font-size:1.6em;margin:1.6em 0 .4em;padding-bottom:.2em;border-bottom:1px solid #e9e9e7}
.nguide h3{font-size:1.25em;margin:1.2em 0 .3em}
.nguide h4{font-size:1.05em;margin:1em 0 .2em}
.nguide p{margin:.3em 0}
.nguide table{border-collapse:collapse;width:100%;margin:.6em 0;font-size:14px}
.nguide th,.nguide td{border:1px solid #e9e9e7;padding:6px 10px;vertical-align:top;text-align:left}
.nguide th{background:#f7f6f3;font-weight:600}
.nguide .callout{display:flex;gap:10px;padding:12px 14px;border-radius:6px;margin:.6em 0}
.nguide .ci{font-size:1.1em}
.nguide blockquote{border-left:3px solid #37352f;padding-left:12px;margin:.6em 0}
.nguide code{background:#f1f1ef;padding:1px 4px;border-radius:3px;font-size:.9em}
.nguide pre{background:#f7f6f3;padding:12px;border-radius:6px;white-space:pre-wrap}
.nguide .cols{display:flex;gap:16px}.nguide .cols>div{flex:1}
.nguide hr{border:none;border-top:1px solid #e9e9e7;margin:1em 0}
</style>
"""


@st.cache_data(ttl=60, show_spinner="가이드 불러오는 중...")
def load_guide_html() -> str:
    page = _request("GET", f"{API}/pages/{GUIDE_PAGE_ID}")
    title = _rich(page["properties"]["title"]["title"])
    with ThreadPoolExecutor(max_workers=3) as pool:  # Notion 레이트리밋 초당 약 3회
        body = _render(_tree(GUIDE_PAGE_ID, pool))
    return f'{CSS}<div class="nguide"><h1>{title}</h1>{body}</div>'
