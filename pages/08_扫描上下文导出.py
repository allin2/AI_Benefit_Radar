import streamlit as st
import json
from ai_benefit_desk.db.database import SessionLocal
from ai_benefit_desk.db.models import BenefitModel, SystemStateModel
from ai_benefit_desk.services.export_service import ExportService
from ai_benefit_desk.utils.json_utils import dumps_json

st.title("📤 扫描上下文导出 (Scan Context Export)")
st.caption("导出符合 AI Benefit Data Exchange Protocol V0.1 标准的轻量扫描上下文 JSON 包，提供给 ChatGPT 开展新一轮调查")

db = SessionLocal()
try:
    sys_state = db.query(SystemStateModel).filter_by(id=1).first()
    rev = sys_state.baseline_revision if sys_state else 0
    state = sys_state.baseline_state if sys_state else "EMPTY"

    st.write(f"**当前系统基线版本:** `Revision {rev}` | **基线状态:** `{'已就绪 (READY)' if state == 'READY' else '未初始化 (EMPTY)'}`")

    with st.form("export_form"):
        c1, c2 = st.columns(2)
        with c1:
            mode = st.selectbox(
                "调研模式 (Scan Mode)",
                ["FULL_SCAN", "DEEP_FULL_SCAN", "VENDOR_DEEP_DIVE", "MISSED_BENEFIT_REVIEW"],
                format_func=lambda x: {
                    "FULL_SCAN": "FULL_SCAN — 普通全量扫描 (增量复查)",
                    "DEEP_FULL_SCAN": "DEEP_FULL_SCAN — 深度全量扫描 (强制刷新基线)",
                    "VENDOR_DEEP_DIVE": "VENDOR_DEEP_DIVE — 单厂商深度调查",
                    "MISSED_BENEFIT_REVIEW": "MISSED_BENEFIT_REVIEW — 漏检复盘调研"
                }.get(x, x)
            )
        with c2:
            all_vendors = sorted(list({b.vendor for b in db.query(BenefitModel).all()}))
            vendor_filter = st.selectbox("厂商范围 (可选，用于专项扫描)", ["全部厂商"] + all_vendors)

        v_filter = None if vendor_filter == "全部厂商" else vendor_filter
        submit_export = st.form_submit_button("📦 生成并导出扫描上下文", type="primary")

    if submit_export:
        context_pkg = ExportService.generate_scan_context(db, requested_mode=mode, vendor_filter=v_filter)
        json_data = context_pkg.model_dump()
        json_str = dumps_json(json_data, indent=2)
        
        scan_id = context_pkg.scan.scan_id
        file_name = f"AI-Benefit-Scan-Context-{scan_id}.json"

        st.success(f"🎉 **成功生成扫描上下文包！** 批次 ID: `{scan_id}`")
        
        c_i1, c_i2, c_i3, c_i4 = st.columns(4)
        with c_i1:
            st.metric("轻量身份索引", len(context_pkg.benefit_index))
        with c_i2:
            st.metric("本轮需复查福利", len(context_pkg.review_items))
        with c_i3:
            st.metric("开放线索", len(context_pkg.open_leads))
        with c_i4:
            st.metric("有效官方入口", len(context_pkg.canonical_sources))

        st.download_button(
            label=f"⬇️ 点击下载 {file_name}",
            data=json_str,
            file_name=file_name,
            mime="application/json",
            use_container_width=True
        )

        with st.expander("查看导出的 JSON 预览", expanded=False):
            st.code(json_str[:2000] + ("\n... [已截断显示]" if len(json_str) > 2000 else ""), language="json")

finally:
    db.close()
