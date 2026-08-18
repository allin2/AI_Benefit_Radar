import streamlit as st
from ai_benefit_desk.db.init_db import init_db
from ai_benefit_desk.config import APP_TITLE, PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION

# Initialize DB
init_db()

st.set_page_config(
    page_title=APP_TITLE,
    page_icon="🧭",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS for polished, clean Chinese UI
st.markdown("""
<style>
    .main-title {
        font-size: 2.2rem;
        font-weight: 700;
        color: #1E293B;
        margin-bottom: 0.2rem;
    }
    .sub-title {
        font-size: 1.0rem;
        color: #64748B;
        margin-bottom: 1.5rem;
    }
    .metric-card {
        background-color: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 8px;
        padding: 16px;
        text-align: center;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 700;
        color: #0F172A;
    }
    .metric-label {
        font-size: 0.85rem;
        color: #64748B;
    }
    .status-badge {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 0.8rem;
        font-weight: 600;
    }
    .badge-confirmed { background-color: #DCFCE7; color: #166534; }
    .badge-likely { background-color: #FEF3C7; color: #92400E; }
    .badge-unverified { background-color: #F1F5F9; color: #475569; }
    .badge-disputed { background-color: #FEE2E2; color: #991B1B; }
    .badge-active { background-color: #E0F2FE; color: #0369A1; }
    .badge-expiring { background-color: #FFEDD5; color: #C2410C; }
</style>
""", unsafe_allow_html=True)

st.sidebar.markdown(f"### 🧭 {APP_TITLE}")
st.sidebar.caption(f"协议版本: V{PROTOCOL_VERSION} | Schema: V{BENEFIT_SCHEMA_VERSION}")
st.sidebar.markdown("---")

st.markdown("""
<div class="main-title">🧭 AI Benefit Desk V0.1</div>
<div class="sub-title">个人 AI 福利与资源监控系统 · 长期数据与真理层</div>
""", unsafe_allow_html=True)

st.info("👈 请使用左侧侧边栏导航访问各功能页面（总览、福利库、线索队列、覆盖记录、官方入口、人工检查、导入/导出）。")
