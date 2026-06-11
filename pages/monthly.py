import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import calendar
from datetime import date, timedelta
from supabase import create_client

st.set_page_config(page_title="월별 현황", page_icon="📊", layout="wide")

API_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo220L01.do"

STATUS_ORDER = ["검토중", "검토완료", "이상없음", "게재중단"]


@st.cache_resource
def _sb():
    return create_client(st.secrets["supabase"]["url"], st.secrets["supabase"]["key"])


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
                    "날짜":     (item.findtext("ifDtm") or "")[:10],
                    "공고번호": item.findtext("wantedAuthNo") or "",
                    "에러내용": item.findtext("errCont") or "",
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
    first = (raw.sort_values("날짜")
                .drop_duplicates(subset=["공고번호"], keep="first")
                .groupby("날짜")["공고번호"].count()
                .rename("신규 공고"))
    df = pd.concat([total, first], axis=1).fillna(0).astype(int).reset_index()
    return df


@st.cache_data(ttl=60)
def load_cs_processing(year, month):
    """Supabase memo_store에서 해당 월 처리 내역 로드."""
    rows = (_sb().table("memo_store")
                 .select("status, status_changed_at")
                 .not_.is_("status_changed_at", "null")
                 .neq("status_changed_at", "")
                 .execute().data)
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    prefix = f"{year:04d}-{month:02d}"
    df = df[df["status_changed_at"].str.startswith(prefix, na=False)].copy()
    df.rename(columns={"status_changed_at": "날짜", "status": "처리상태"}, inplace=True)
    return df


# ── 사이드바 ───────────────────────────────────
with st.sidebar:
    st.page_link("pages/monitoring.py", label="← 모니터링", use_container_width=True)
    st.page_link("pages/guide.py", label="📖 운영 가이드", use_container_width=True)
    st.title("📊 월별 현황")
    col1, col2 = st.columns(2)
    with col1:
        sel_year  = st.selectbox("연도", [2025, 2026], index=1)
    with col2:
        sel_month = st.selectbox("월", list(range(1, 13)),
                                  index=date.today().month - 1,
                                  format_func=lambda x: f"{x}월")
    st.divider()
    st.caption("API 피드백 탭은 인증키가 필요합니다.")
    auth_key = st.text_input("인증키", type="password", placeholder="발급받은 인증키 입력")
    run_btn = st.button("🔎 API 조회", use_container_width=True, type="primary")

# ── 메인 ───────────────────────────────────────
st.title("📊 월별 현황")

tab1, tab2 = st.tabs(["📡 Work24 API 피드백", "📋 모니터링 처리 현황"])

# ── Tab 1: API 피드백 ─────────────────────────
with tab1:
    if run_btn:
        if not auth_key:
            st.error("인증키를 입력해 주세요.")
            st.stop()

        with st.spinner(f"{sel_year}년 {sel_month}월 조회 중... (약 10~20초 소요)"):
            raw = fetch_month(sel_year, sel_month, auth_key)

        if raw.empty:
            st.info("조회된 데이터가 없습니다.")
            st.stop()

        daily        = build_daily(raw)
        total_raw    = int(daily["피드백 건수(raw)"].sum())
        unique_count = int(raw["공고번호"].nunique())
        st.session_state["monthly_daily"] = daily.copy()   # Tab 2에서 병합용
        st.session_state["monthly_key"]   = (sel_year, sel_month)

        c1, c2 = st.columns(2)
        c1.metric("피드백 건수 (raw)", f"{total_raw:,}건",
                  help="API에서 받은 전체 오류 피드백 횟수. 같은 공고가 여러 에러로 여러 번 잡히면 그 횟수만큼 포함.")
        c2.metric("유니크 공고 수", f"{unique_count:,}건",
                  help="공고번호 기준 중복 제거. 실제로 이슈가 발생한 공고 수.")

        st.divider()
        st.caption(
            f"※ 통계 설명\n"
            f"* 아래 통계는 조회한 월({sel_year}년 {sel_month}월) 기준입니다. 이전 달 데이터는 포함되지 않습니다.\n"
            f"* 피드백 건수(raw): API가 반환한 전체 오류 횟수로 같은 공고도 에러 유형·날짜별로 중복 집계됩니다.\n"
            f"* 유니크 공고 수: 공고번호 기준 중복 제거한 실제 이슈 공고 수입니다.\n"
            f"* 일별 신규 공고는 해당 날짜에 이번 달 처음 등장한 공고번호 수로, 당일 새로 유입된 공고 규모를 파악할 때 사용합니다."
        )
        st.dataframe(daily, hide_index=True, use_container_width=True)

    else:
        st.info("← 왼쪽에서 인증키와 조회 월을 선택하고 **API 조회** 버튼을 누르세요.")

# ── Tab 2: 모니터링 처리 현황 ─────────────────
with tab2:
    cs_raw = load_cs_processing(sel_year, sel_month)

    if cs_raw.empty:
        st.info(f"{sel_year}년 {sel_month}월에 처리된 내역이 없습니다.")
    else:
        total_cs = len(cs_raw)
        status_counts = cs_raw["처리상태"].value_counts()

        # 상단 요약 메트릭
        cols = st.columns(len(STATUS_ORDER) + 1)
        cols[0].metric("총 처리 건수", f"{total_cs:,}건")
        for i, s in enumerate(STATUS_ORDER):
            cols[i + 1].metric(s, f"{status_counts.get(s, 0):,}건")

        st.divider()

        # 일별 처리 현황 피벗 테이블
        pivot = (cs_raw.groupby(["날짜", "처리상태"])
                       .size()
                       .unstack(fill_value=0)
                       .reset_index())

        # 실제 존재하는 상태만 순서대로 컬럼 정렬
        ordered_cols = [s for s in STATUS_ORDER if s in pivot.columns]
        pivot = pivot[["날짜"] + ordered_cols]
        pivot.insert(1, "합계", pivot[ordered_cols].sum(axis=1))
        # API 피드백 데이터가 같은 월로 조회된 경우 병합
        api_daily = st.session_state.get("monthly_daily")
        api_key   = st.session_state.get("monthly_key")
        if api_daily is not None and api_key == (sel_year, sel_month):
            pivot = pivot.merge(api_daily, on="날짜", how="outer").fillna(0)
            pivot["합계"]          = pivot["합계"].astype(int)
            pivot["피드백 건수(raw)"] = pivot["피드백 건수(raw)"].astype(int)
            pivot["신규 공고"]     = pivot["신규 공고"].astype(int)
            # 컬럼 순서: 날짜 | 피드백(raw) | 신규 공고 | 합계 | 상태별
            front = ["날짜", "피드백 건수(raw)", "신규 공고", "합계"]
            pivot = pivot[front + ordered_cols]

        pivot = pivot.sort_values("날짜", ascending=True).reset_index(drop=True)

        st.caption(
            f"※ {sel_year}년 {sel_month}월 기준 처리 현황입니다.\n"
            f"* 합계: 해당 날짜에 처리상태가 변경된 공고 수입니다.\n"
            f"* 동일 공고를 같은 날 여러 번 변경해도 마지막 상태 1건으로 집계됩니다.\n"
            f"* 이전 달에 처리한 공고를 이번 달에 재변경하면 이번 달 수치에 포함됩니다."
        )
        st.dataframe(pivot, hide_index=True, use_container_width=True)
