"""처리상태·메모 저장소 (Notion DB).

b-pipeline에서 supabase.co 아웃바운드가 막혀 있어 사내 Notion DB로 이전.
DB 속성: 공고번호(title) / 처리상태(select) / 메모(text) / 상태변경일(date)
"""
import time
import requests
import streamlit as st

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"


def _headers():
    return {
        "Authorization": f"Bearer {st.secrets['notion']['token']}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _db_id():
    return st.secrets["notion"]["database_id"]


def _request(method, url, **kwargs):
    # Notion 레이트리밋(초당 약 3회) 대응: 429/5xx면 잠시 후 재시도
    for attempt in range(5):
        resp = requests.request(method, url, headers=_headers(), timeout=(10, 30), **kwargs)
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(float(resp.headers.get("Retry-After", 1 + attempt)))
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()


def _text(prop):
    items = (prop or {}).get("title") or (prop or {}).get("rich_text") or []
    return "".join(t.get("plain_text", "") for t in items)


def _props(status, memo, changed_at):
    return {
        "처리상태":  {"select": {"name": status}},
        "메모":      {"rich_text": [{"text": {"content": memo[:2000]}}] if memo else []},
        "상태변경일": {"date": {"start": changed_at} if changed_at else None},
    }


def _fetch_pages() -> dict:
    """공고번호 → {page_id, 처리상태, 메모, 상태변경일}"""
    out = {}
    body = {"page_size": 100}
    while True:
        data = _request("POST", f"{API}/databases/{_db_id()}/query", json=body)
        for page in data["results"]:
            p = page["properties"]
            key = _text(p.get("공고번호"))
            if not key:
                continue
            out[key] = {
                "page_id":  page["id"],
                "처리상태":  ((p.get("처리상태") or {}).get("select") or {}).get("name", "미검토"),
                "메모":      _text(p.get("메모")),
                "상태변경일": (((p.get("상태변경일") or {}).get("date") or {}).get("start") or "")[:10],
            }
        if not data.get("has_more"):
            return out
        body["start_cursor"] = data["next_cursor"]


@st.cache_data(ttl=5)
def load_store() -> dict:
    return {k: {kk: v[kk] for kk in ("처리상태", "메모", "상태변경일")}
            for k, v in _fetch_pages().items()}


def save_store(store: dict, to_delete: set = None):
    """바뀐 행만 Notion에 반영 (전체 upsert는 API 호출이 많아 diff로 처리)."""
    current = _fetch_pages()
    for k in (to_delete or set()):
        if k in current:
            _request("PATCH", f"{API}/pages/{current[k]['page_id']}", json={"archived": True})
    for k, v in store.items():
        status, memo, changed_at = v["처리상태"], v.get("메모", "") or "", v.get("상태변경일", "") or ""
        cur = current.get(k)
        if cur and (cur["처리상태"], cur["메모"], cur["상태변경일"]) == (status, memo, changed_at):
            continue
        props = _props(status, memo, changed_at)
        if cur:
            _request("PATCH", f"{API}/pages/{cur['page_id']}", json={"properties": props})
        else:
            props["공고번호"] = {"title": [{"text": {"content": k}}]}
            _request("POST", f"{API}/pages", json={"parent": {"database_id": _db_id()}, "properties": props})
    load_store.clear()
