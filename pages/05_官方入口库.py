import streamlit as st
import pandas as pd
from datetime import date
from ai_benefit_desk.db.database import SessionLocal
from ai_benefit_desk.db.models import CanonicalSourceModel
from ai_benefit_desk.services.id_service import IdService
from ai_benefit_desk.utils.enum_labels import (
    SOURCE_LEVEL_LABELS, SOURCE_STATUS_LABELS, get_label
)
from ai_benefit_desk.utils.date_utils import today_str

st.title("🏛️ 官方入口库 (Canonical Source Registry)")
st.caption("管理经过验证的官方入口（Pricing、Docs、Help、活动中心等），支持增/改/停用，不物理删除")

db = SessionLocal()
try:
    sources = db.query(CanonicalSourceModel).order_by(CanonicalSourceModel.id.desc()).all()

    # Add Source Form in Expander
    with st.expander("➕ 新增官方入口", expanded=False):
        with st.form("add_source_form"):
            c1, c2, c3 = st.columns(3)
            with c1:
                vendor_in = st.text_input("厂商 *", placeholder="如: OpenAI")
                surface_in = st.text_input("Surface *", placeholder="如: Free / Signup")
            with c2:
                product_in = st.text_input("产品 *", placeholder="如: ChatGPT")
                source_type_in = st.selectbox("入口类型", ["PRICING", "HELP_FAQ", "ACTIVITY_CENTER", "DOCS", "BLOG", "OTHER"])
            with c3:
                source_name_in = st.text_input("入口名称 *", placeholder="如: ChatGPT Pricing Page")
                source_level_in = st.selectbox("来源等级", ["S", "A", "B"], format_func=lambda x: get_label(SOURCE_LEVEL_LABELS, x))

            url_in = st.text_input("URL 网址 *", placeholder="https://...")
            
            submit_add = st.form_submit_button("添加官方入口")
            if submit_add:
                if not (vendor_in and product_in and surface_in and source_name_in and url_in):
                    st.warning("请填写所有必填字段 (*)")
                else:
                    new_id = IdService.generate_source_id(db)
                    new_src = CanonicalSourceModel(
                        source_id=new_id,
                        vendor=vendor_in.strip(),
                        product=product_in.strip(),
                        surface=surface_in.strip(),
                        source_name=source_name_in.strip(),
                        url=url_in.strip(),
                        source_type=source_type_in,
                        source_level=source_level_in,
                        status="ACTIVE",
                        last_verified_at=today_str()
                    )
                    db.add(new_src)
                    db.commit()
                    st.success(f"已成功添加入口: {new_id}")
                    st.rerun()

    # Source List
    st.write(f"当前共 **{len(sources)}** 个官方入口：")
    
    if not sources:
        st.info("入口库为空，请点击上方添加官方入口。")
    else:
        for s in sources:
            status_label = get_label(SOURCE_STATUS_LABELS, s.status)
            is_active = (s.status == "ACTIVE")
            
            exp_title = f"[{s.source_id}] {s.vendor} - {s.product} | {s.source_name} ({s.surface}) | 状态: {status_label}"
            
            with st.expander(exp_title, expanded=False):
                col_info, col_action = st.columns([3, 1])
                with col_info:
                    st.write(f"**URL:** [{s.url}]({s.url})")
                    st.write(f"**类型:** `{s.source_type}` | **来源等级:** {get_label(SOURCE_LEVEL_LABELS, s.source_level)}")
                    st.write(f"**最近验证时间:** `{s.last_verified_at or '-'}`")

                with col_action:
                    if is_active:
                        if st.button("停用该入口", key=f"dep_{s.source_id}"):
                            s.status = "DEPRECATED"
                            db.commit()
                            st.success("已停用该入口！")
                            st.rerun()
                    else:
                        if st.button("重新启用", key=f"act_{s.source_id}"):
                            s.status = "ACTIVE"
                            s.last_verified_at = today_str()
                            db.commit()
                            st.success("已重新启用！")
                            st.rerun()
finally:
    db.close()
