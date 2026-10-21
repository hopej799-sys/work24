import streamlit as st

from notion_guide import load_guide_html

st.set_page_config(page_title="운영 가이드", page_icon="📖", layout="wide")

# 가이드 본문은 Notion 페이지에서 읽어 온다 (수정 시 배포 불필요, 최대 1분 뒤 반영)
try:
    st.html(load_guide_html())
except Exception as e:
    st.error("운영 가이드를 불러오지 못했습니다. 잠시 후 새로고침해 주세요.")
    st.caption(f"상세: {e}")
