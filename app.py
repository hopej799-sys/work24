import hmac
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

# 접속 비밀번호: 서버 secrets의 app_password (GitLab 변수 BUILD_ENV_APP_PASSWORD). 세션당 1회 입력.
if not st.session_state.get("authed"):
    st.title("🔒 연계채용정보 모니터링")
    with st.form("login"):
        pw = st.text_input("비밀번호", type="password")
        ok = st.form_submit_button("들어가기", type="primary")
    if ok:
        expected = st.secrets.get("app_password", "")
        if not expected:
            st.error("서버에 접속 비밀번호(APP_PASSWORD)가 설정되지 않았습니다. 관리자에게 문의해 주세요.")
            st.stop()
        if hmac.compare_digest(pw.encode(), expected.encode()):
            st.session_state["authed"] = True
            st.rerun()
        st.error("비밀번호가 맞지 않습니다.")
    st.stop()

# 로그인 후 사이드바 상단 메뉴로 세 화면 이동
pg = st.navigation([
    st.Page("pages/monitoring.py", title="모니터링",   icon="📋", default=True),
    st.Page("pages/monthly.py",    title="월별 통계",  icon="📊"),
    st.Page("pages/guide.py",      title="운영 가이드", icon="📖"),
], position="sidebar")

with st.sidebar:
    if st.button("로그아웃", use_container_width=True):
        st.session_state.pop("authed", None)
        st.rerun()
    st.divider()

pg.run()
