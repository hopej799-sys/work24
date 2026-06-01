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
    total  = raw.groupby("날짜").size().rename("전체(raw)")
    excl   = raw[~raw["에러내용"].str.contains("고용형태", na=False)].groupby("날짜").size().rename("고용형태 제외(raw)")
    unique = (raw.drop_duplicates(subset=["공고번호"])
                 .groupby("날짜")["공고번호"].count()
                 .rename("유니크"))
    df = pd.concat([total, excl, unique], axis=1).fillna(0).astype(int).reset_index()
    df.rename(columns={"날짜": "날짜"}, inplace=True)
    return df


# ── 사이드바 ───────────────────────────────────
with st.sidebar:
    st.page_link("pages/monitoring.py", label="← 모니터링", use_container_width=True)
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

    c1, c2, c3 = st.columns(3)
    c1.metric("전체 합계(raw)", f"{daily['전체(raw)'].sum():,}건")
    c2.metric("고용형태 제외(raw)", f"{daily['고용형태 제외(raw)'].sum():,}건")
    c3.metric("유니크 합계", f"{daily['유니크'].sum():,}건")

    st.divider()
    st.caption("전체·고용형태 제외: 중복 포함 raw 건수 / 유니크: 공고번호 기준 중복 제거")
    st.dataframe(daily, hide_index=True, use_container_width=True)

else:
    st.info("← 왼쪽에서 인증키와 조회 월을 선택하고 **조회** 버튼을 누르세요.")
