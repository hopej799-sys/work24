"""Supabase memo_store CSV → Notion DB 1회성 이관.

사용법 (work24 폴더에서):
    .venv\\Scripts\\python.exe tools\\migrate_supabase_to_notion.py memo_store_rows.csv          # 미리보기
    .venv\\Scripts\\python.exe tools\\migrate_supabase_to_notion.py memo_store_rows.csv --apply  # 실제 등록

- 토큰/DB ID는 .streamlit/secrets.toml 의 [notion] 섹션에서 읽는다.
- 노션에 이미 있는 공고번호는 건너뛴다 (여러 번 돌려도 중복 생성 안 됨).
"""
import csv
import sys
import time
import tomllib
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.notion.com/v1"
STATUSES = {"미검토", "검토중", "검토완료", "이상없음", "게재중단"}


def main(csv_path, apply):
    cfg = tomllib.loads((ROOT / ".streamlit" / "secrets.toml").read_text(encoding="utf-8"))["notion"]
    headers = {
        "Authorization": f"Bearer {cfg['token']}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json",
    }
    db_id = cfg["database_id"]

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        rows = [r for r in csv.DictReader(f) if (r.get("wanted_auth_no") or "").strip()]
    print(f"CSV {len(rows)}건")

    # 노션에 이미 있는 공고번호
    existing, body = set(), {"page_size": 100}
    while True:
        data = requests.post(f"{API}/databases/{db_id}/query", headers=headers, json=body, timeout=30)
        data.raise_for_status()
        data = data.json()
        for page in data["results"]:
            title = page["properties"]["공고번호"]["title"]
            existing.add("".join(t["plain_text"] for t in title))
        if not data.get("has_more"):
            break
        body["start_cursor"] = data["next_cursor"]
    print(f"노션 기존 {len(existing)}건")

    todo = [r for r in rows if r["wanted_auth_no"].strip() not in existing]
    bad = [r for r in todo if r.get("status") not in STATUSES]
    print(f"신규 등록 대상 {len(todo)}건" + (f" (처리상태 값 이상 {len(bad)}건 → '미검토'로 등록)" if bad else ""))
    for r in todo[:5]:
        print("  예)", r["wanted_auth_no"], r.get("status"), (r.get("status_changed_at") or "")[:10], (r.get("memo") or "")[:30])
    if not apply:
        print("\n미리보기만 했습니다. 실제 등록은 --apply 를 붙여 다시 실행하세요.")
        return

    for i, r in enumerate(todo, 1):
        status = r.get("status") if r.get("status") in STATUSES else "미검토"
        memo = r.get("memo") or ""
        changed = (r.get("status_changed_at") or "")[:10]
        props = {
            "공고번호":  {"title": [{"text": {"content": r["wanted_auth_no"].strip()}}]},
            "처리상태":  {"select": {"name": status}},
            "메모":      {"rich_text": [{"text": {"content": memo[:2000]}}] if memo else []},
            "상태변경일": {"date": {"start": changed} if changed else None},
        }
        for attempt in range(5):
            resp = requests.post(f"{API}/pages", headers=headers, timeout=30,
                                 json={"parent": {"database_id": db_id}, "properties": props})
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(float(resp.headers.get("Retry-After", 1 + attempt)))
                continue
            resp.raise_for_status()
            break
        time.sleep(0.35)  # 레이트리밋(초당 약 3회)
        if i % 50 == 0 or i == len(todo):
            print(f"  {i}/{len(todo)} 완료")
    print("이관 끝")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    main(sys.argv[1], "--apply" in sys.argv)
