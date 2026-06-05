import streamlit as st
from pathlib import Path

_css = Path(__file__).parent / "style.css"
if _css.exists():
    st.markdown(f"<style>{_css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

pg = st.navigation([
    st.Page("pages/monitoring.py", title="📋 모니터링", icon="🔍"),
    st.Page("pages/monthly.py",    title="📊 월별 현황", icon="📊"),
], position="hidden")
pg.run()
