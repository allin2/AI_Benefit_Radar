import streamlit as st
import pandas as pd
from ai_benefit_desk.db.database import SessionLocal
from ai_benefit_desk.db.models import CoverageHistoryModel
from ai_benefit_desk.utils.enum_labels import COVERAGE_STATE_LABELS, get_label

st.title("🌐 覆盖记录 (Coverage Ledger)")
st.caption("展示各厂商、产品、Surface与地区的最新覆盖状态与历史检查事件")

db = SessionLocal()
try:
    all_covs = db.query(CoverageHistoryModel).order_by(CoverageHistoryModel.id.desc()).all()

    tab1, tab2 = st.tabs(["📊 最新覆盖矩阵", "📜 完整历史事件流"])

    with tab1:
        # Aggregate latest coverage per (vendor, product, surface, region)
        seen = set()
        latest_items = []
        for c in all_covs:
            key = (c.vendor, c.product, c.surface, c.region)
            if key not in seen:
                seen.add(key)
                latest_items.append(c)

        if not latest_items:
            st.info("暂无覆盖记录数据。")
        else:
            # Filters
            f1, f2 = st.columns(2)
            with f1:
                vendors = ["全部"] + sorted(list({c.vendor for c in latest_items}))
                sel_v = st.selectbox("筛选厂商", vendors, key="cov_v")
            with f2:
                states = ["全部"] + list(COVERAGE_STATE_LABELS.keys())
                sel_s = st.selectbox("筛选覆盖状态", states, format_func=lambda x: "全部" if x == "全部" else get_label(COVERAGE_STATE_LABELS, x), key="cov_s")

            rows = []
            for c in latest_items:
                if sel_v != "全部" and c.vendor != sel_v:
                    continue
                if sel_s != "全部" and c.coverage_state != sel_s:
                    continue
                
                rows.append({
                    "厂商": c.vendor,
                    "产品": c.product,
                    "Surface 监控面": c.surface,
                    "地区": c.region,
                    "最新覆盖状态": get_label(COVERAGE_STATE_LABELS, c.coverage_state),
                    "实际检查时间": c.actual_checked_at,
                    "最近观察时间": c.scan_observed_at,
                    "下次建议复查": c.next_review_at,
                    "扫描批次": c.scan_id,
                    "备注": c.notes or "-"
                })

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True)

    with tab2:
        if not all_covs:
            st.info("暂无历史记录。")
        else:
            hist_rows = []
            for c in all_covs:
                hist_rows.append({
                    "ID": c.coverage_id,
                    "扫描批次": c.scan_id,
                    "厂商": c.vendor,
                    "产品": c.product,
                    "Surface": c.surface,
                    "地区": c.region,
                    "状态": get_label(COVERAGE_STATE_LABELS, c.coverage_state),
                    "实际检查时间": c.actual_checked_at,
                    "观察时间": c.scan_observed_at,
                    "依据历史ID": c.basis_coverage_id or "-",
                    "记录时间": c.created_at.strftime("%Y-%m-%d %H:%M:%S") if c.created_at else "-"
                })
            st.dataframe(pd.DataFrame(hist_rows), use_container_width=True)
finally:
    db.close()
