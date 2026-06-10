import streamlit as st
import streamlit.components.v1 as components
from pathlib import Path

st.set_page_config(page_title="운영 가이드", page_icon="📖", layout="wide")

with st.sidebar:
    st.page_link("pages/monitoring.py", label="← 모니터링", use_container_width=True)

html = (Path(__file__).parent.parent / "static" / "guide.html").read_text(encoding="utf-8")
components.html(html, height=6000, scrolling=True)
