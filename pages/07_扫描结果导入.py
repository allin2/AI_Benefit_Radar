import streamlit as st
import json
from ai_benefit_desk.db.database import SessionLocal
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.utils.enum_labels import (
    VERIFICATION_STATUS_LABELS, STATUS_LABELS, CHANGE_TYPE_LABELS,
    COVERAGE_STATE_LABELS, SCAN_COMPLETION_LABELS, get_label
)

st.title("📥 扫描结果导入 (Scan Import)")
st.caption("上传 ChatGPT 生成的 AI-Benefit-Scan-Import-<scan_id>.json 文件，进行完整门禁校验与单事务入库")

uploaded_file = st.file_uploader("选择或拖拽扫描导入 JSON 文件", type=["json"])

if uploaded_file is not None:
    raw_content = uploaded_file.getvalue().decode("utf-8")
    
    # Store parsed preview in session_state
    db = SessionLocal()
    try:
        # Check override evidence toggle in session_state
        override_ev = st.checkbox("⚠️ 人工覆盖证据门禁 (仅在确认福利真实但暂时无法取得S/A证据时使用，将记录审计)", key="override_ev_toggle")

        preview_data = ImportService.parse_and_preview(db, raw_content, user_override_evidence=override_ev)
        
        if not preview_data["is_valid"]:
            st.error("❌ **校验失败，禁止导入！** 发现以下阻塞性错误：")
            for err in preview_data["errors"]:
                st.error(f"- {err}")
        else:
            p = preview_data["preview"]
            pkg = preview_data["import_pkg"]
            
            st.success("✅ **校验通过！** 已生成导入预览，请核对后确认提交入库。")

            # 1. 扫描结果总览
            st.markdown("### 📊 扫描结果")
            sc1, sc2, sc3, sc4 = st.columns(4)
            with sc1:
                st.write(f"**扫描批次 ID:** `{p['scan_id']}`")
                st.write(f"**扫描模式:** `{p['scan_mode']}`")
            with sc2:
                status_labels = [get_label(SCAN_COMPLETION_LABELS, s) for s in p['scan_statuses']]
                st.write(f"**扫描完成状态:** `{', '.join(status_labels)}`")
                st.write(f"**生成时间:** `{p['generated_at']}`")
            with sc3:
                st.write(f"**基线版本 (Revision):** `{p['context_baseline_revision']}`")
                st.write(f"**基线动作:** `{p['baseline_action']}`")
            with sc4:
                st.write(f"**扫描说明:** {p['summary_notes'] or '-'}")

            st.markdown("---")

            # 2. 已确认福利预览
            st.markdown(f"### 🎁 福利事实 (新增: {p['benefit_create_count']} | 更新: {p['benefit_update_count']} | 复核无变化: {p['benefit_no_change_count']})")
            
            # Dedup resolutions dictionary
            dedup_resolutions = {}
            if p["duplicates"]:
                st.warning(f"⚠️ 发现 **{len(p['duplicates'])}** 个疑似重复的 CREATE 候选项：")
                for dup in p["duplicates"]:
                    if dup.get("is_intra_package"):
                        target_ref = dup.get("target_local_ref")
                        st.markdown(f"**候选 local_ref:** `{dup['local_ref']}` 与本次导入中的另一条候选福利 `[{target_ref}] {dup.get('existing_campaign_name')}` 可能重复")
                        st.caption(f"匹配原因: {dup['reason']}")
                        if dup.get("has_conflict"):
                            st.warning(f"⚠️ **存在明确事实冲突:** `{dup.get('conflicts')}`，请核对后再选择处理方式！")
                            choice = st.radio(
                                f"处理策略 ({dup['local_ref']})",
                                ["请选择处理方式...", "保持独立 (分别创建)", f"合并到主候选福利 ({target_ref})", "忽略该项"],
                                key=f"dedup_choice_{dup['local_ref']}"
                            )
                            if "合并到主候选福利" in choice:
                                dedup_resolutions[dup["local_ref"]] = f"MERGE_LOCAL:{target_ref}"
                            elif "保持独立" in choice:
                                dedup_resolutions[dup["local_ref"]] = "KEEP_SEPARATE"
                            elif "忽略该项" in choice:
                                dedup_resolutions[dup["local_ref"]] = "IGNORE"
                        else:
                            choice = st.radio(
                                f"处理策略 ({dup['local_ref']})",
                                [f"合并到主候选福利 ({target_ref})", "仍然分别创建", "忽略该项"],
                                key=f"dedup_choice_{dup['local_ref']}"
                            )
                            if "合并到主候选福利" in choice:
                                dedup_resolutions[dup["local_ref"]] = f"MERGE_LOCAL:{target_ref}"
                            elif "忽略该项" in choice:
                                dedup_resolutions[dup["local_ref"]] = "IGNORE"

                    else:
                        st.markdown(f"**候选 local_ref:** `{dup['local_ref']}` 与已有福利 `[{dup['existing_benefit_id']}] {dup['existing_campaign_name']}` 可能重复")
                        st.caption(f"匹配原因: {dup['reason']}")
                        choice = st.radio(
                            f"处理策略 ({dup['local_ref']})",
                            [f"更新已有福利 ({dup['existing_benefit_id']})", "仍然创建为新福利", "忽略该项"],
                            key=f"dedup_choice_{dup['local_ref']}"
                        )
                        if "更新已有福利" in choice:
                            dedup_resolutions[dup["local_ref"]] = f"UPDATE:{dup['existing_benefit_id']}"
                        elif "忽略该项" in choice:
                            dedup_resolutions[dup["local_ref"]] = "IGNORE"


            if p["evidence_warnings"]:
                st.warning(f"⚠️ 发现 **{len(p['evidence_warnings'])}** 个证据级别异常项：")
                for ew in p["evidence_warnings"]:
                    st.write(f"- {ew['message']}")

            with st.expander("查看福利变更明细", expanded=True):
                for bop in p["benefit_changes"]:
                    op_tag = f"[{bop.operation}]"
                    if bop.operation == "CREATE" and bop.record:
                        rec = bop.record
                        st.markdown(f"**{op_tag}** [{bop.local_ref}] {rec.vendor} - {rec.product} | {rec.campaign_name}")
                        st.caption(f"内容: {rec.benefit_detail} | 类型: {rec.benefit_type} | 状态: {rec.status} | 来源等级: {rec.source_level}")
                    elif bop.operation == "UPDATE":
                        st.markdown(f"**{op_tag}** [{bop.benefit_id}] 字段变更: `{json.dumps(bop.patch, ensure_ascii=False)}`")
                    elif bop.operation == "CONFIRM_NO_CHANGE":
                        st.markdown(f"**{op_tag}** [{bop.benefit_id}] 复核日期: `{bop.last_checked}` | 下次复查: `{bop.next_review_date}`")

            st.markdown("---")

            # 3. 线索队列预览
            st.markdown(f"### 🔍 线索队列 (新增: {p['lead_create_count']} | 更新: {p['lead_update_count']} | 转福利: {p['lead_resolve_count']} | 驳回: {p['lead_reject_count']})")
            if p["lead_changes"]:
                with st.expander("查看线索变更明细", expanded=False):
                    for lop in p["lead_changes"]:
                        if lop.operation == "CREATE" and lop.record:
                            st.write(f"- **[CREATE]** [{lop.local_ref}] {lop.record.lead_summary}")
                        elif lop.operation == "RESOLVE_TO_BENEFIT":
                            st.write(f"- **[RESOLVE_TO_BENEFIT]** [{lop.lead_id}] -> `{lop.target_benefit_ref or lop.target_benefit_id}`")
                        elif lop.operation == "REJECT":
                            st.write(f"- **[REJECT]** [{lop.lead_id}] 原因: {lop.rejection_reason}")
                        else:
                            st.write(f"- **[{lop.operation}]** [{lop.lead_id}]")

            st.markdown("---")

            # 4. 覆盖记录与入口预览
            st.markdown(f"### 🌐 覆盖记录 (实际重检: {p['coverage_recheck_count']} | 复查未到期: {p['coverage_review_not_due_count']} | 盲区: {p['coverage_blind_spot_count']})")
            st.markdown(f"### 🏛️ 官方入口 (新增: {p['source_add_count']} | 更新: {p['source_update_count']} | 停用: {p['source_deprecate_count']})")
            st.markdown(f"### 📝 建议人工检查 ({p['manual_check_count']} 项)")

            # Warnings section
            if preview_data["warnings"]:
                st.markdown("---")
                st.markdown("### ⚠️ 结构化警告提示")
                for w in preview_data["warnings"]:
                    w_type = w.get("type", "OTHER")
                    w_msg = w.get("message_zh", "")
                    w_ref = f" (关联: {w.get('related_ref')})" if w.get('related_ref') else ""
                    st.warning(f"**[{w_type}]** {w_msg}{w_ref}")

            st.markdown("---")

            # Actions
            col_act1, col_act2 = st.columns([1, 4])
            with col_act1:
                if st.button("🚀 确认导入 (单事务入库)", type="primary", use_container_width=True):
                    try:
                        commit_res = ImportService.commit_import(
                            db, pkg, raw_content,
                            dedup_resolutions=dedup_resolutions,
                            user_override_evidence=override_ev
                        )
                        st.balloons()
                        st.success(f"🎉 **导入成功！** 扫描批次 `{commit_res['scan_id']}` 已完成入库，系统基线已由 Revision `{commit_res['baseline_revision_before']}` 升级为 `{commit_res['baseline_revision_after']}`！")
                    except Exception as ex:
                        st.error(f"❌ 导入过程中发生异常，事务已全量回滚：{str(ex)}")

            with col_act2:
                if st.button("❌ 取消导入", use_container_width=False):
                    st.info("已取消导入。")
                    st.rerun()

    finally:
        db.close()
