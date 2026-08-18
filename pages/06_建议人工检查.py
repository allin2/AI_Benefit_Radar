import streamlit as st
from datetime import datetime
from ai_benefit_desk.db.database import SessionLocal
from ai_benefit_desk.db.models import ManualCheckModel
from ai_benefit_desk.utils.enum_labels import (
    MANUAL_CHECK_CHANNEL_LABELS, MANUAL_CHECK_PRIORITY_LABELS,
    MANUAL_CHECK_STATUS_LABELS, get_label
)

st.title("📝 建议人工检查 (Manual Checks)")
st.caption("跟踪公开 Web 无法观察的账号态、客户端、IDE及邮件等盲区核查任务")

db = SessionLocal()
try:
    filter_status = st.radio("任务状态过滤", ["仅看待检查 (OPEN)", "全部任务"], horizontal=True)
    
    query = db.query(ManualCheckModel)
    if "仅看待检查" in filter_status:
        query = query.filter_by(status="OPEN")
        
    checks = query.order_by(ManualCheckModel.id.desc()).all()

    st.write(f"当前共 **{len(checks)}** 项人工核查任务：")

    if not checks:
        st.info("当前没有需要人工核查的任务。")
    else:
        for m in checks:
            p_label = get_label(MANUAL_CHECK_PRIORITY_LABELS, m.priority)
            ch_label = get_label(MANUAL_CHECK_CHANNEL_LABELS, m.channel)
            st_label = get_label(MANUAL_CHECK_STATUS_LABELS, m.status)
            
            p_icon = "🔴" if m.priority == "HIGH" else ("🟡" if m.priority == "MEDIUM" else "🟢")
            
            exp_title = f"{p_icon} [{m.manual_check_id}] {m.vendor} - {m.product} | {m.reason[:35]}... | 渠道: {ch_label} | 优先级: {p_label} | 状态: {st_label}"
            
            with st.expander(exp_title, expanded=(m.status == "OPEN")):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"#### 核查原因: {m.reason}")
                    st.write(f"**建议操作:** {m.suggested_action}")
                    st.write(f"**厂商/产品:** `{m.vendor}` / `{m.product}` | **核查渠道:** `{ch_label}`")
                    if m.related_benefit_id:
                        st.write(f"**关联福利:** `{m.related_benefit_id}`")
                    if m.related_lead_id:
                        st.write(f"**关联线索:** `{m.related_lead_id}`")
                    if m.result_notes:
                        st.info(f"📋 **核查结果记录:** {m.result_notes}")

                with c2:
                    if m.status == "OPEN":
                        st.markdown("##### ✍️ 录入检查结果")
                        res_notes = st.text_area("检查结果笔记", key=f"res_{m.manual_check_id}", placeholder="如: 登录客户端发现确实赠送了 1000 积分")
                        
                        btn_c1, btn_c2 = st.columns(2)
                        with btn_c1:
                            if st.button("标记完成", key=f"done_{m.manual_check_id}"):
                                m.status = "COMPLETED"
                                m.result_notes = res_notes.strip()
                                m.completed_at = datetime.utcnow()
                                db.commit()
                                st.success("已标记完成！")
                                st.rerun()
                        with btn_c2:
                            if st.button("忽略任务", key=f"dsm_{m.manual_check_id}"):
                                m.status = "DISMISSED"
                                db.commit()
                                st.success("已忽略！")
                                st.rerun()
finally:
    db.close()
