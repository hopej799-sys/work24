"""처리상태·메모 저장소 (Notion DB).

b-pipeline에서 supabase.co 아웃바운드가 막혀 있어 사내 Notion DB로 이전.
DB 속성: 공고번호(title) / 처리상태(select) / 메모(text) / 상태변경일(date)
        + 모니터링 항목(DETAIL_COLS) — 저장 시점의 조회 결과를 함께 기록
"""
import time
import requests
import streamlit as st

API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"

# 모니터링 화면 컬럼 → Notion 속성 (구인공고 URL만 url 타입, 나머지는 text)
DETAIL_COLS = ["오류구분", "모니터링일시", "연계일시", "에러내용",
               "구인공고 URL", "법위반의심 여부", "법령 맵핑 내용"]
URL_COL = "구인공고 URL"


def _headers():
    return {
        "Authorization": f"Bearer {st.secrets['notion']['token']}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def _db_id():
    return st.secrets["notion"]["database_id"]


def _request(method, url, **kwargs):
    # Notion 레이트리밋(초당 약 3회) 대응: 429/5xx/타임아웃이면 잠시 후 재시도
    for attempt in range(5):
        try:
            resp = requests.request(method, url, headers=_headers(), timeout=(10, 30), **kwargs)
        except (requests.Timeout, requests.ConnectionError):
            if attempt == 4:
                raise
            time.sleep(1 + attempt)
            continue
        if resp.status_code == 429 or resp.status_code >= 500:
            time.sleep(float(resp.headers.get("Retry-After", 1 + attempt)))
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()


def _text(prop):
    items = (prop or {}).get("title") or (prop or {}).get("rich_text") or []
    return "".join(t.get("plain_text", "") for t in items)


def _rich(value):
    return {"rich_text": [{"text": {"content": value[:2000]}}] if value else []}


def _props(status, memo, changed_at, detail=None):
    props = {
        "처리상태":  {"select": {"name": status}},
        "메모":      _rich(memo),
        "상태변경일": {"date": {"start": changed_at} if changed_at else None},
    }
    for col, val in (detail or {}).items():
        val = str(val or "")
        props[col] = {"url": val or None} if col == URL_COL else _rich(val)
    return props


def _fetch_pages() -> dict:
    """공고번호 → {page_id, 처리상태, 메모, 상태변경일, 상세}"""
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
                "상세": {c: ((p.get(c) or {}).get("url") or "") if c == URL_COL else _text(p.get(c))
                         for c in DETAIL_COLS},
            }
        if not data.get("has_more"):
            return out
        body["start_cursor"] = data["next_cursor"]


@st.cache_data(ttl=5)
def load_store() -> dict:
    return {k: {kk: v[kk] for kk in ("처리상태", "메모", "상태변경일")}
            for k, v in _fetch_pages().items()}


def save_store(store: dict, to_delete: set = None, details: dict = None):
    """바뀐 행만 Notion에 반영 (전체 upsert는 API 호출이 많아 diff로 처리).

    details: 공고번호 → {DETAIL_COLS: 값}. 저장하는 행의 모니터링 항목을 함께 기록.
    """
    details = details or {}
    current = _fetch_pages()
    for k in (to_delete or set()):
        if k in current:
            _request("PATCH", f"{API}/pages/{current[k]['page_id']}", json={"archived": True})
    for k, v in store.items():
        status, memo, changed_at = v["처리상태"], v.get("메모", "") or "", v.get("상태변경일", "") or ""
        detail = {c: str(details[k].get(c, "") or "") for c in DETAIL_COLS} if k in details else None
        cur = current.get(k)
        if (cur and (cur["처리상태"], cur["메모"], cur["상태변경일"]) == (status, memo, changed_at)
                and (detail is None or detail == cur["상세"])):
            continue
        props = _props(status, memo, changed_at, detail)
        if cur:
            _request("PATCH", f"{API}/pages/{cur['page_id']}", json={"properties": props})
        else:
            props["공고번호"] = {"title": [{"text": {"content": k}}]}
            _request("POST", f"{API}/pages", json={"parent": {"database_id": _db_id()}, "properties": props})
    load_store.clear()
