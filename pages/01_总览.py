import streamlit as st
from ai_benefit_desk.db.database import SessionLocal
from ai_benefit_desk.db.models import ManualCheckModel
from ai_benefit_desk.services.review_service import ReviewService
from ai_benefit_desk.utils.enum_labels import (
    VERIFICATION_STATUS_LABELS, STATUS_LABELS, MANUAL_CHECK_PRIORITY_LABELS,
    MANUAL_CHECK_CHANNEL_LABELS, get_label
)

st.title("📊 首页 / 总览")
st.caption("展示当前系统关键行动指标、基线状态及待办事项")

db = SessionLocal()
try:
    metrics = ReviewService.get_overview_metrics(db)

    # 1. Top Action Metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("🎁 已确认且有效福利", metrics["confirmed_active_count"])
    with c2:
        exp_count = metrics["expiring_soon_count"]
        exp_delta = f"{exp_count} 项需关注" if exp_count > 0 else None
        st.metric("⏰ 即将过期福利 (7天内)", exp_count, delta=exp_delta, delta_color="inverse")
    with c3:
        st.metric("📬 我的待处理福利", metrics["not_reviewed_count"])
    with c4:
        st.metric("⭐ 我感兴趣的福利", metrics["interested_count"])

    st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
    
    c5, c6, c7, c8 = st.columns(4)
    with c5:
        st.metric("🔄 到期待复查福利", metrics["review_due_count"])
    with c6:
        st.metric("🔍 开放未确认线索", metrics["open_leads_count"])
    with c7:
        st.metric("👁️‍🗨️ 渠道监控盲区", metrics["blind_spots_count"])
    with c8:
        st.metric("🛠️ 待人工检查任务", metrics["open_manual_checks_count"])

    st.markdown("---")

    # 2. System Baseline Bar
    col_s1, col_s2, col_s3 = st.columns([1, 1, 2])
    with col_s1:
        st.write(f"**当前 Baseline Revision:** `{metrics['baseline_revision']}`")
    with col_s2:
        b_state_label = "🟢 已就绪 (READY)" if metrics["baseline_state"] == "READY" else "🟡 未初始化 (EMPTY)"
        st.write(f"**基线状态:** {b_state_label}")
    with col_s3:
        st.write(f"**最近扫描批次:** `{metrics['latest_scan_id']}` ({metrics['latest_scan_time']})")

    st.markdown("---")

    # 3. Action Boards
    tab1, tab2, tab3 = st.tabs(["⏰ 即将过期福利", "🔄 到期待复查福利", "🛠️ 待办人工检查"])

    with tab1:
        expiring = metrics["expiring_soon_items"]
        if not expiring:
            st.success("✅ 当前没有 7 天内即将过期的福利。")
        else:
            for b in expiring:
                with st.expander(f"⚠️ [{b.vendor}] {b.product} - {b.campaign_name} (截止: {b.end_date})"):
                    st.write(f"**福利详情:** {b.benefit_detail}")
                    st.write(f"**领取方式:** {b.claim_method}")
                    st.write(f"**官方来源:** [{b.official_source}]({b.official_source})")

    with tab2:
        due = metrics["review_due_items"]
        if not due:
            st.success("✅ 当前没有到达复查日期的福利。")
        else:
            for b in due:
                with st.expander(f"🔄 [{b.vendor}] {b.product} - {b.campaign_name} (下次复查: {b.next_review_date})"):
                    st.write(f"**福利详情:** {b.benefit_detail}")
                    st.write(f"**验证状态:** {get_label(VERIFICATION_STATUS_LABELS, b.verification_status)}")
                    st.write(f"**当前状态:** {get_label(STATUS_LABELS, b.status)}")
                    st.write(f"**官方来源:** [{b.official_source}]({b.official_source})")

    with tab3:
        manual_checks = db.query(ManualCheckModel).filter_by(status="OPEN").all()
        if not manual_checks:
            st.success("✅ 当前没有开放的人工检查任务。")
        else:
            for m in manual_checks:
                p_color = "🔴" if m.priority == "HIGH" else ("🟡" if m.priority == "MEDIUM" else "🟢")
                with st.expander(f"{p_color} [{m.vendor}] {m.product} - 渠道: {get_label(MANUAL_CHECK_CHANNEL_LABELS, m.channel)} ({get_label(MANUAL_CHECK_PRIORITY_LABELS, m.priority)}优先级)"):
                    st.write(f"**核查原因:** {m.reason}")
                    st.write(f"**建议操作:** {m.suggested_action}")
finally:
    db.close()
