import streamlit as st
import requests
import xml.etree.ElementTree as ET
import pandas as pd
import io
import json
from pathlib import Path
from datetime import date, timedelta
import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

st.set_page_config(
    page_title="연계채용정보 모니터링",
    page_icon="🔍",
    layout="wide",
)

API_URL = "https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo220L01.do"

COLUMNS = [
    ("sysGbnNm",      "오류구분"),
    ("iorgGbnm",      "연계기관명"),
    ("wantedAuthNo",  "공고번호"),
    ("createDtm",     "모니터링일시"),
    ("ifDtm",         "연계일시"),
    ("errCont",       "에러내용"),
    ("lawVoltDobtYn", "법위반의심 여부"),
    ("lawMappCont",   "법령 맵핑 내용"),
]

STATUS_OPTIONS = ["미검토", "이상없음", "게재중단"]
STORE_FILE = Path(__file__).parent / "memo_store.json"


def load_store() -> dict:
    if STORE_FILE.exists():
        try:
            return json.loads(STORE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_store(store: dict):
    STORE_FILE.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")

# ── 사이드바 ───────────────────────────────────
with st.sidebar:
    st.title("🔍 조회 조건")

    auth_key = st.text_input("인증키 *", type="password", placeholder="발급받은 인증키 입력")

    st.markdown("**조회 기간 *** (최대 3일)")
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input("시작일", value=date.today() - timedelta(days=2))
    with col2:
        end_date = st.date_input("종료일", value=date.today())

    wanted_auth_no = st.text_input("공고번호 (선택)", placeholder="예) K123456789")
    law_volt = st.selectbox("법위반의심 여부 (선택)", ["전체", "Y (의심 항목만)"])

    st.divider()
    st.markdown("**조회 필터**")
    exclude_employment = st.checkbox(
        "고용형태 에러 제외",
        help="에러내용에 '고용형태'가 포함된 항목을 조회 결과에서 제외합니다",
    )

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
    for item in root.iter("monitoringErrInfo"):
        row = {}
        for key, label in COLUMNS:
            node = item.find(key)
            row[label] = node.text.strip() if node is not None and node.text else ""
        rows.append(row)
    df = pd.DataFrame(rows, columns=[label for _, label in COLUMNS])
    df.insert(0, "처리상태", "미검토")
    df.insert(1, "메모", "")
    return df


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
    green_fill   = PatternFill("solid", start_color="D9F2D9")
    red_fill     = PatternFill("solid", start_color="FFD9D9")

    ncols = len(df.columns)
    ws.merge_cells(f"A1:{get_column_letter(ncols)}1")
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
        status = row[0]
        if status == "이상없음":
            row_fill = green_fill
        elif status == "게재중단":
            row_fill = red_fill
        else:
            row_fill = alt_fill if ri % 2 == 1 else None

        for ci, (col, val) in enumerate(zip(df.columns, row), 1):
            c = ws.cell(row=ri, column=ci, value=val)
            c.font = cell_font; c.border = border
            c.alignment = left_align if col in long_cols else center_align
            if row_fill:
                c.fill = row_fill
        ws.row_dimensions[ri].height = 18

    col_widths = [12, 30, 18, 20, 20, 20, 20, 50, 16, 40]
    for i, w in enumerate(col_widths[:ncols], 1):
        ws.column_dimensions[get_column_letter(i)].width = w

    ws.freeze_panes = "A3"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ── 편집 딕셔너리를 raw_df에 적용 ─────────────────
def apply_edits(df: pd.DataFrame, edits: dict) -> pd.DataFrame:
    df = df.copy()
    for idx in df.index:
        key = df.at[idx, "공고번호"]
        if key and key in edits:
            df.at[idx, "처리상태"] = edits[key].get("처리상태", "미검토")
            df.at[idx, "메모"]     = edits[key].get("메모", "")
    return df


# ── 메인 ───────────────────────────────────────
st.title("📋 연계채용정보 모니터링 결과조회")
st.caption("한국고용정보원 Work24 Open API")

if search_btn:
    if not validate():
        st.stop()

    with st.spinner("데이터 조회 중..."):
        try:
            xml_text = fetch(start_date, end_date, auth_key, wanted_auth_no, law_volt)
        except requests.HTTPError as e:
            st.error(f"API 오류: {e}")
            st.stop()
        except Exception as e:
            st.error(f"오류 발생: {e}")
            st.stop()

    try:
        df = parse(xml_text)
    except ET.ParseError as e:
        st.error(f"XML 파싱 오류: {e}")
        st.stop()

    if exclude_employment:
        df = df[~df["에러내용"].str.contains("고용형태", na=False)].reset_index(drop=True)

    # raw_df는 API 원본 그대로 유지, 편집은 edits 딕셔너리로만 관리
    st.session_state["raw_df"] = df
    st.session_state["edits"]  = load_store()   # 파일에서 이전 저장 복원
    st.session_state["period"] = (start_date, end_date)


if "raw_df" not in st.session_state:
    st.info("← 왼쪽 사이드바에서 조회 조건을 입력하고 **조회** 버튼을 누르세요.")
    st.stop()

raw_df      = st.session_state["raw_df"]
edits       = st.session_state["edits"]        # {공고번호: {처리상태, 메모}}
start_saved, end_saved = st.session_state["period"]

# 편집 딕셔너리를 raw_df에 적용해서 화면용 df 생성
df_display = apply_edits(raw_df, edits)

if df_display.empty:
    st.info("조회된 데이터가 없습니다.")
    st.stop()

# 요약 지표
c1, c2, c3, c4 = st.columns(4)
c1.metric("총 건수",   f"{len(df_display):,}건")
c2.metric("법위반의심", f"{(df_display['법위반의심 여부'] == 'Y').sum():,}건")
c3.metric("미검토",    f"{(df_display['처리상태'] == '미검토').sum():,}건")
c4.metric("처리완료",  f"{(df_display['처리상태'] != '미검토').sum():,}건")

st.divider()

# 결과 필터
with st.expander("🔧 결과 필터", expanded=True):
    f1, f2, f3 = st.columns([2, 2, 1])
    with f1:
        status_filter = st.selectbox("처리 상태", ["전체", "미검토", "이상없음", "게재중단"])
    with f2:
        err_type_filter = st.selectbox("오류구분", ["전체", "사전필터링", "구인 모니터링"])
    with f3:
        st.markdown("<br>", unsafe_allow_html=True)
        law_only  = st.checkbox("법령 맵핑 내용 있는것만")
        memo_only = st.checkbox("메모 있는것만")

# 필터 적용
filtered = df_display.copy()
if status_filter != "전체":
    filtered = filtered[filtered["처리상태"] == status_filter]
if err_type_filter == "사전필터링":
    filtered = filtered[filtered["오류구분"].str.contains("사전", na=False)]
elif err_type_filter == "구인 모니터링":
    filtered = filtered[filtered["오류구분"].str.contains("구인", na=False)]
if law_only:
    filtered = filtered[filtered["법령 맵핑 내용"].str.strip().ne("")]
if memo_only:
    filtered = filtered[filtered["메모"].str.strip().ne("")]

st.caption(f"필터 결과: {len(filtered):,}건 / 전체 {len(df_display):,}건")

filtered_display = filtered.reset_index(drop=True)

edited = st.data_editor(
    filtered_display,
    column_config={
        "처리상태": st.column_config.SelectboxColumn(
            "처리상태",
            options=STATUS_OPTIONS,
            required=True,
            width="small",
        ),
        "메모":       st.column_config.TextColumn("메모",       width="medium"),
        "에러내용":   st.column_config.TextColumn("에러내용",   width="large"),
        "법령 맵핑 내용": st.column_config.TextColumn("법령 맵핑 내용", width="large"),
    },
    hide_index=True,
    use_container_width=True,
    height=450,
    key="data_editor",
)

# 현재 화면의 편집 상태를 edits 딕셔너리에 반영
# prev(edits 딕셔너리)와 비교해서 dirty 감지, 항상 현재값을 edits에 기록
for i in range(len(edited)):
    wanted     = edited.iloc[i]["공고번호"]
    new_status = edited.iloc[i]["처리상태"]
    raw_memo   = edited.iloc[i]["메모"]
    new_memo   = "" if pd.isna(raw_memo) else str(raw_memo)
    if not wanted:
        continue
    if new_status != "미검토" or new_memo.strip():
        edits[wanted] = {"처리상태": new_status, "메모": new_memo}
    elif wanted in edits:
        del edits[wanted]
st.session_state["edits"] = edits

st.divider()

# 현재 의미있는 edits가 파일에 저장된 내용과 다르면 미저장 변경사항 있음
_meaningful = {k: v for k, v in edits.items() if v["처리상태"] != "미검토" or v["메모"].strip()}
has_changes = _meaningful != load_store()

btn_col, dl_col = st.columns([1, 2])

with btn_col:
    save_label = "💾 저장" + (" ●" if has_changes else "")
    if st.button(save_label, type="primary", use_container_width=True, key="save_btn"):
        store = {
            k: v for k, v in edits.items()
            if v["처리상태"] != "미검토" or v["메모"].strip()
        }
        save_store(store)
        st.toast(f"저장 완료 ({len(store)}건)", icon="✅")
        st.rerun()

with dl_col:
    df_export = apply_edits(raw_df, edits)
    excel_buf = make_excel(df_export, start_saved, end_saved)
    filename  = f"모니터링결과_{start_saved.strftime('%Y%m%d')}-{end_saved.strftime('%Y%m%d')}.xlsx"
    st.download_button(
        label="📥 엑셀 다운로드 (전체)",
        data=excel_buf,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )
