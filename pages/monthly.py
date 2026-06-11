import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import calendar
from datetime import date, timedelta

st.set_page_config(page_title="월별 현황", page_icon="📊", layout="wide")

API_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo220L01.do"


def fetch_chunk(start, end, auth):
    resp = requests.get(API_URL, params={
        "authKey": auth, "returnType": "XML", "callTp": "D",
        "ifDtmStdt": start.strftime("%Y%m%d"),
        "ifDtmEndt": end.strftime("%Y%m%d"),
    }, timeout=30)
    resp.raise_for_status()
    return resp.text


def fetch_month(year, month, auth):
    frames = []
    cur = date(year, month, 1)
    end = date(year, month, calendar.monthrange(year, month)[1])
    while cur <= end:
        chunk_end = min(cur + timedelta(days=2), end)
        try:
            xml = fetch_chunk(cur, chunk_end, auth)
            root = ET.fromstring(xml)
            rows = []
            for item in root.iter("monitoringErrInfo"):
                rows.append({
                    "날짜":         (item.findtext("ifDtm") or "")[:10],
                    "공고번호":     item.findtext("wantedAuthNo") or "",
                    "에러내용":     item.findtext("errCont") or "",
                })
            if rows:
                frames.append(pd.DataFrame(rows))
        except Exception:
            pass
        cur = chunk_end + timedelta(days=1)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def build_daily(raw):
    raw = raw[raw["날짜"].str.len() == 10].copy()
    total = raw.groupby("날짜").size().rename("피드백 건수(raw)")
    # 날짜순 정렬 후 공고번호 첫 등장일만 추출 → 해당월 기준 당일 신규 공고 수
    first = (raw.sort_values("날짜")
                .drop_duplicates(subset=["공고번호"], keep="first")
                .groupby("날짜")["공고번호"].count()
                .rename("신규 공고"))
    df = pd.concat([total, first], axis=1).fillna(0).astype(int).reset_index()
    return df


# ── 사이드바 ───────────────────────────────────
with st.sidebar:
    st.page_link("pages/monitoring.py", label="← 모니터링", use_container_width=True)
    st.page_link("pages/guide.py", label="📖 운영 가이드", use_container_width=True)
    st.title("📊 월별 현황")
    auth_key = st.text_input("인증키 *", type="password", placeholder="발급받은 인증키 입력")
    col1, col2 = st.columns(2)
    with col1:
        sel_year  = st.selectbox("연도", [2025, 2026], index=1)
    with col2:
        sel_month = st.selectbox("월", list(range(1, 13)),
                                  index=date.today().month - 1,
                                  format_func=lambda x: f"{x}월")
    run_btn = st.button("🔎 조회", use_container_width=True, type="primary")

# ── 메인 ───────────────────────────────────────
st.title("📊 월별 현황")
st.caption(f"Work24 Open API — 일별 피드백 건수 집계")

if run_btn:
    if not auth_key:
        st.error("인증키를 입력해 주세요.")
        st.stop()

    with st.spinner(f"{sel_year}년 {sel_month}월 조회 중... (약 10~20초 소요)"):
        raw = fetch_month(sel_year, sel_month, auth_key)

    if raw.empty:
        st.info("조회된 데이터가 없습니다.")
        st.stop()

    daily = build_daily(raw)
    total_raw    = int(daily["피드백 건수(raw)"].sum())
    unique_count = int(raw["공고번호"].nunique())
    dup_count    = total_raw - unique_count

    c1, c2 = st.columns(2)
    c1.metric("피드백 건수 (raw)", f"{total_raw:,}건",
              help="API에서 받은 모든 피드백 횟수. 한 공고가 여러 에러로 여러 번 잡히면 그 횟수만큼 포함.")
    c2.metric("유니크 공고 수", f"{unique_count:,}건",
              help="공고번호 기준 중복 제거. 실제로 이슈가 발생한 공고 수.")

    st.divider()
    st.caption(
        f"※ 아래 통계는 조회한 월({sel_year}년 {sel_month}월) 기준입니다. 이전 달 데이터는 포함되지 않습니다.\n"
        f"피드백 건수(raw): API가 반환한 전체 오류 횟수로 같은 공고도 에러 유형·날짜별로 중복 집계됩니다. "
        f"유니크 공고 수: 공고번호 기준 중복 제거한 실제 이슈 공고 수입니다. "
        f"두 값의 차이({dup_count:,}건)는 동일 공고가 해당 월에 2회 이상 반복 오류로 잡힌 건수입니다. "
        f"일별 신규 공고는 해당 날짜에 이번 달 처음 등장한 공고번호 수로, 당일 새로 유입된 공고 규모를 파악할 때 사용합니다."
    )
    st.dataframe(daily, hide_index=True, use_container_width=True)

else:
    st.info("← 왼쪽에서 인증키와 조회 월을 선택하고 **조회** 버튼을 누르세요.")
