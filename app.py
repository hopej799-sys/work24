import streamlit as st
from pathlib import Path

# Pretendard 폰트 — @import는 Streamlit <style> 내에서 무시되므로 <link>로 로드
st.markdown(
    '<link href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css" rel="stylesheet">',
    unsafe_allow_html=True,
)

_css = Path(__file__).parent / "style.css"
if _css.exists():
    st.markdown(f"<style>{_css.read_text(encoding='utf-8')}</style>", unsafe_allow_html=True)

pg = st.navigation([
    st.Page("pages/monitoring.py", title="📋 모니터링", icon="🔍"),
    st.Page("pages/monthly.py",    title="📊 월별 현황", icon="📊"),
    st.Page("pages/guide.py",      title="📖 운영 가이드", icon="📖"),
], position="hidden")
pg.run()
