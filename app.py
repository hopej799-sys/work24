import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import io
from datetime import date, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# ── 페이지 설정 ────────────────────────────────
st.set_page_config(
    page_title="연계채용정보 모니터링",
    page_icon="🔍",
    layout="wide",
)

API_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo220L01.do"

COLUMNS = [
    ("sysGbmNm",      "오류구분"),
    ("iorgGbnm",      "연계기관명"),
    ("wantedAuthNo",  "공고번호"),
    ("createDtm",     "모니터링일시"),
    ("ifDtm",         "연계일시"),
    ("errCont",       "에러내용"),
    ("lawVoltDobtYn", "법위반의심 여부"),
    ("lawMappCont",   "법령 맵핑 내용"),
]

# ── 사이드바 입력 ───────────────────────────────
with st.sidebar:
    st.title("🔍 조회 조건")

    auth_key = st.text_input(
        "인증키 *",
        type="password",
        placeholder="발급받은 인증키 입력",
    )

    st.markdown("**조회 기간 *** (최대 3일)")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("시작일", value=date.today() - timedelta(days=2))
    with col2:
        end_date = st.date_input("종료일", value=date.today())

    wanted_auth_no = st.text_input("공고번호 (선택)", placeholder="예) K123456789")
    law_volt = st.selectbox("법위반의심 여부 (선택)", ["전체", "Y (의심 항목만)"])

    search_btn = st.button("🔎 조회", use_container_width=True, type="primary")

# ── 유효성 검사 ────────────────────────────────
def validate():
    if not auth_key:
        st.error("인증키를 입력해 주세요.")
        return False
    delta = (end_date - start_date).days
    if delta < 0:
        st.error("종료일이 시작일보다 빠릅니다.")
        return False
    if delta > 2:
        st.error("최대 3일 범위까지만 조회 가능합니다.")
        return False
    return True

# ── API 호출 ───────────────────────────────────
def fetch(start, end, auth, wanted_no, law_y):
    params = {
        "authKey":    auth,
        "returnType": "XML",
        "callTp":     "D",
        "ifDtmStdt":  start.strftime("%Y%m%d"),
        "ifDtmEndt":  end.strftime("%Y%m%d"),
    }
    if wanted_no:
        params["wantedAuthNo"] = wanted_no
    if law_y == "Y (의심 항목만)":
        params["lawVoltDobtYn"] = "Y"

    resp = requests.get(API_URL, params=params, timeout=30)
    resp.raise_for_status()
    return resp.text

# ── XML 파싱 ───────────────────────────────────
def parse(xml_text):
    root = ET.fromstring(xml_text)
    rows = []
    for item in root.iter("item"):
        row = {}
        for key, label in COLUMNS:
            node = item.find(key)
            row[label] = node.text.strip() if node is not None and node.text else ""
        rows.append(row)
    return pd.DataFrame(rows, columns=[label for _, label in COLUMNS])

# ── 엑셀 생성 ──────────────────────────────────
def make_excel(df, start, end):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "모니터링결과"

    header_font  = Font(name="맑은 고딕", bold=True, color="FFFFFF", size=10)
    header_fill  = PatternFill("solid", start_color="1F5C8B")
    cell_font    = Font(name="맑은 고딕", size=10)
    center_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    left_align   = Alignment(horizontal="left",   vertical="center", wrap_text=True)
    thin         = Side(style="thin", color="CCCCCC")
    border       = Border(left=thin, right=thin, top=thin, bottom=thin)
    alt_fill     = PatternFill("solid", start_color="EAF2FB")

    ws.merge_cells("A1:H1")
    t = ws["A1"]
    t.value     = f"연계채용정보 모니터링 결과  |  {start.strftime('%Y%m%d')} ~ {end.strftime('%Y%m%d')}"
    t.font      = Font(name="맑은 고딕", bold=True, size=12, color="1F5C8B")
    t.alignment = center_align
    ws.row_dimensions[1].height = 28

    for ci, col in enumerate(df.columns, 1):
        c = ws.cell(row=2, column=ci, value=col)
        c.font = header_font; c.fill = header_fill
        c.alignment = center_align; c.border = border
    ws.row_dimensions[2].height = 22

    long_cols = {"에러내용", "법령 맵핑 내용"}
    for ri, row in enumerate(df.itertuples(index=False), 3):
        fill = alt_fill if ri % 2 == 1 else None
        for ci, (col, val) in enumerate(zip(df.columns, row), 1):
            c = ws.cell(row=ri, column=ci, value=val)
            c.font = cell_font; c.border = border
            c.alignment = left_align if col in long_cols else center_align
            if fill:
                c.fill = fill
        ws.row_dimensions[ri].height = 18

    for i, w in enumerate([18, 20, 20, 20, 20, 50, 16, 40], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf

# ── 메인 화면 ──────────────────────────────────
st.title("📋 연계채용정보 모니터링 결과조회")
st.caption("한국고용정보원 Work24 Open API")

if search_btn:
    if not validate():
        st.stop()

    with st.spinner("데이터 조회 중..."):
        try:
            xml_text = fetch(start_date, end_date, auth_key, wanted_auth_no, law_volt)
            df = parse(xml_text)
        except requests.HTTPError as e:
            st.error(f"API 오류: {e}")
            st.stop()
        except ET.ParseError:
            st.error("응답 파싱 오류입니다. 인증키를 확인해 주세요.")
            st.stop()
        except Exception as e:
            st.error(f"오류 발생: {e}")
            st.stop()

    if df.empty:
        st.info("조회된 데이터가 없습니다.")
        st.stop()

    # 요약 지표
    c1, c2, c3 = st.columns(3)
    c1.metric("총 건수", f"{len(df):,}건")
    c2.metric("법위반의심 건수", f"{(df['법위반의심 여부'] == 'Y').sum():,}건")
    c3.metric("연계기관 수", f"{df['연계기관명'].nunique():,}개")

    st.divider()

    # 필터
    with st.expander("🔧 결과 필터"):
        institutions = ["전체"] + sorted(df["연계기관명"].unique().tolist())
        sel_inst = st.selectbox("연계기관명", institutions)
        if sel_inst != "전체":
            df = df[df["연계기관명"] == sel_inst]

    st.dataframe(df, use_container_width=True, height=450)

    # 다운로드
    excel_buf = make_excel(df, start_date, end_date)
    filename = f"모니터링결과_{start_date.strftime('%Y%m%d')}-{end_date.strftime('%Y%m%d')}.xlsx"
    st.download_button(
        label="📥 엑셀 다운로드",
        data=excel_buf,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        type="primary",
    )
else:
    st.info("← 왼쪽 사이드바에서 조회 조건을 입력하고 **조회** 버튼을 누르세요.")
