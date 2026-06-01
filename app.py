import streamlit as st

pg = st.navigation([
    st.Page("pages/monitoring.py", title="📋 모니터링", icon="🔍"),
    st.Page("pages/monthly.py",    title="📊 월별 현황", icon="📊"),
])
pg.run()
