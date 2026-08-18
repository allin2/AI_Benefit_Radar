import streamlit as st
from datetime import date
from ai_benefit_desk.db.database import SessionLocal
from ai_benefit_desk.db.models import BenefitModel, UserBenefitStateModel
from ai_benefit_desk.utils.enum_labels import (
    VERIFICATION_STATUS_LABELS, STATUS_LABELS, CHANGE_TYPE_LABELS,
    USER_ACTION_STATE_LABELS, SOURCE_LEVEL_LABELS, RISK_LEVEL_LABELS, get_label
)
from ai_benefit_desk.utils.date_utils import is_expiring_soon, is_review_due

st.title("🎁 福利库")
st.caption("长期存储的正式 AI 福利库，支持多维筛选与个人处理状态管理")

db = SessionLocal()
try:
    # Query all benefits
    benefits = db.query(BenefitModel).all()
    user_states = {s.benefit_id: s for s in db.query(UserBenefitStateModel).all()}

    # Filters in Expander
    with st.expander("🔍 筛选与检索", expanded=True):
        f_col1, f_col2, f_col3, f_col4 = st.columns(4)
        
        vendors = sorted(list({b.vendor for b in benefits}))
        with f_col1:
            sel_vendor = st.selectbox("厂商", ["全部"] + vendors)
            
        status_options = ["全部"] + list(STATUS_LABELS.keys())
        with f_col2:
            sel_status = st.selectbox("福利状态", status_options, format_func=lambda x: "全部" if x == "全部" else get_label(STATUS_LABELS, x))

        verif_options = ["全部"] + list(VERIFICATION_STATUS_LABELS.keys())
        with f_col3:
            # Default to CONFIRMED or 全部
            sel_verif = st.selectbox("验证状态 (默认已确认)", verif_options, index=1 if "CONFIRMED" in verif_options else 0, format_func=lambda x: "全部" if x == "全部" else get_label(VERIFICATION_STATUS_LABELS, x))

        action_options = ["全部"] + list(USER_ACTION_STATE_LABELS.keys())
        with f_col4:
            sel_action = st.selectbox("我的处理状态", action_options, format_func=lambda x: "全部" if x == "全部" else get_label(USER_ACTION_STATE_LABELS, x))

        fc5, fc6, fc7 = st.columns([1, 1, 2])
        with fc5:
            only_expiring = st.checkbox("仅看待过期 (7天内)")
        with fc6:
            only_review_due = st.checkbox("仅看待复查")
        with fc7:
            search_query = st.text_input("关键词搜索 (福利名称 / 描述 / Wallet / 来源)", "")

    # Apply Filters
    filtered = []
    today = date.today()
    for b in benefits:
        u_state = user_states.get(b.benefit_id)
        u_act = u_state.action_state if u_state else "NOT_REVIEWED"

        if sel_vendor != "全部" and b.vendor != sel_vendor:
            continue
        if sel_status != "全部" and b.status != sel_status:
            continue
        if sel_verif != "全部" and b.verification_status != sel_verif:
            continue
        if sel_action != "全部" and u_act != sel_action:
            continue
        if only_expiring and not is_expiring_soon(b.end_date, days=7, ref_date=today):
            continue
        if only_review_due and not is_review_due(b.next_review_date, ref_date=today):
            continue
        if search_query:
            q = search_query.lower()
            match_txt = f"{b.campaign_name} {b.benefit_detail} {b.vendor} {b.product} {b.wallet} {b.official_source}".lower()
            if q not in match_txt:
                continue

        filtered.append((b, u_state))

    st.write(f"共找到 **{len(filtered)}** 条符合条件的福利记录：")

    if not filtered:
        st.info("暂无符合条件的福利数据。")
    else:
        for b, u_state in filtered:
            current_action = u_state.action_state if u_state else "NOT_REVIEWED"
            current_notes = u_state.notes if u_state else ""
            
            # Badge summary title
            verif_str = get_label(VERIFICATION_STATUS_LABELS, b.verification_status)
            status_str = get_label(STATUS_LABELS, b.status)
            action_str = get_label(USER_ACTION_STATE_LABELS, current_action)
            
            expander_title = f"[{b.benefit_id}] 【{b.vendor} - {b.product}】 {b.campaign_name} | {status_str} | 我的状态: {action_str}"
            
            with st.expander(expander_title):
                c_left, c_right = st.columns([2, 1])
                with c_left:
                    st.markdown(f"#### {b.campaign_name}")
                    st.write(f"**福利内容:** {b.benefit_detail}")
                    if b.benefit_type == "BUNDLED_SUBSCRIPTION" or b.linked_vendor != "UNKNOWN":
                        st.info(f"🔗 **跨产品/跨厂商权益 (Bundle):** 获赠目标: [{b.linked_vendor}] {b.linked_product} | 详情: {b.linked_benefit_detail}")
                    
                    regions_str = ", ".join(b.regions)
                    elig_classes_str = ", ".join(b.eligibility_class)
                    st.write(f"**福利类型:** `{b.benefit_type}` | **Wallet / 资源:** `{b.wallet}` | **额度:** `{b.amount} {b.unit}`")
                    st.write(f"**适用地区:** `{regions_str}` | **资格要求:** {b.eligibility} (`{elig_classes_str}`)")
                    st.write(f"**领取方式:** {b.claim_method} (重置周期: `{b.reset_policy}` | 发放方式: `{b.grant_method}`)")
                    st.write(f"**条件限制:** 需信用卡: `{b.credit_card_required}` | 需认证: `{b.verification_required}`")
                    st.write(f"**起止时间:** `{b.start_date}` ~ `{b.end_date}` | **首次发现:** `{b.first_seen}` | **最近核对:** `{b.last_checked}` | **下次复查:** `{b.next_review_date}`")
                    st.write(f"**官方来源:** [{b.official_source}]({b.official_source}) (等级: {get_label(SOURCE_LEVEL_LABELS, b.source_level)})")
                    if b.notes:
                        st.caption(f"📝 **备注:** {b.notes}")

                with c_right:
                    st.markdown("##### 👤 我的操作状态")
                    st.caption("注意: Scan Import 绝不会覆盖此处的个人状态")
                    
                    new_action = st.selectbox(
                        "更新我的处理状态",
                        list(USER_ACTION_STATE_LABELS.keys()),
                        index=list(USER_ACTION_STATE_LABELS.keys()).index(current_action),
                        format_func=lambda x: get_label(USER_ACTION_STATE_LABELS, x),
                        key=f"act_{b.benefit_id}"
                    )
                    new_notes = st.text_area("个人笔记", current_notes, key=f"note_{b.benefit_id}", height=80)
                    
                    if st.button("保存我的状态", key=f"save_{b.benefit_id}"):
                        if not u_state:
                            u_state = UserBenefitStateModel(benefit_id=b.benefit_id, action_state=new_action, notes=new_notes)
                            db.add(u_state)
                        else:
                            u_state.action_state = new_action
                            u_state.notes = new_notes
                        db.commit()
                        st.success("已更新个人状态！")
                        st.rerun()

finally:
    db.close()
