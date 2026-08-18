import streamlit as st
from ai_benefit_desk.db.database import SessionLocal
from ai_benefit_desk.db.models import LeadModel, BenefitModel
from ai_benefit_desk.utils.enum_labels import (
    VERIFICATION_STATUS_LABELS, LEAD_STATUS_LABELS, SOURCE_LEVEL_LABELS, get_label
)

st.title("🔍 线索队列")
st.caption("管理尚未达到正式已确认标准的福利线索（较大可信、未验证、存在争议）")

db = SessionLocal()
try:
    # Filter by status
    status_filter = st.radio("线索状态过滤", ["仅看待处理 (OPEN)", "全部线索 (含已转福利/已驳回)"], horizontal=True)
    
    query = db.query(LeadModel)
    if "仅看待处理" in status_filter:
        query = query.filter_by(status="OPEN")
    
    leads = query.order_by(LeadModel.id.desc()).all()

    st.write(f"当前共 **{len(leads)}** 条线索：")

    if not leads:
        st.info("线索队列为空，当前没有需要跟进的线索。")
    else:
        for lead in leads:
            verif_str = get_label(VERIFICATION_STATUS_LABELS, lead.verification_status)
            status_str = get_label(LEAD_STATUS_LABELS, lead.status)
            
            exp_title = f"[{lead.lead_id}] {lead.vendor} - {lead.product} | {lead.lead_summary[:40]}... | 状态: {status_str} | 可信度: {verif_str}"
            
            with st.expander(exp_title, expanded=(lead.status == "OPEN")):
                c1, c2 = st.columns([2, 1])
                with c1:
                    st.markdown(f"#### {lead.lead_summary}")
                    st.write(f"**厂商:** `{lead.vendor}` | **产品:** `{lead.product}` | **适用地区:** `{', '.join(lead.regions)}`")
                    st.write(f"**验证级别:** {get_label(SOURCE_LEVEL_LABELS, lead.source_level)} | **当前可信度:** `{verif_str}`")
                    st.write(f"**缺失关键证据:** {lead.missing_evidence or '暂无详细描述'}")
                    st.write(f"**首次发现:** `{lead.first_seen}` | **最近跟进:** `{lead.last_checked}` | **下次复查:** `{lead.next_review_date}`")

                    if lead.status == "RESOLVED":
                        st.success(f"🎉 **已升级为正式福利:** 关联福利 ID: `{lead.resolved_benefit_id}`")
                    elif lead.status == "REJECTED":
                        st.error(f"❌ **已驳回:** 原因: {lead.rejection_reason}")

                with c2:
                    if lead.status == "OPEN":
                        st.markdown("##### ⚙️ 人工操作")
                        reject_reason = st.text_input("驳回原因", key=f"rej_reason_{lead.lead_id}", placeholder="如: 官方已辟谣/不符合福利定义")
                        if st.button("驳回该线索", key=f"rej_btn_{lead.lead_id}"):
                            if not reject_reason.strip():
                                st.warning("请填写驳回原因")
                            else:
                                lead.status = "REJECTED"
                                lead.rejection_reason = reject_reason.strip()
                                db.commit()
                                st.success("已驳回线索！")
                                st.rerun()
finally:
    db.close()
