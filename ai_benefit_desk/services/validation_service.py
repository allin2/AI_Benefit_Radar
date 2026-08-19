from datetime import date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from pydantic import ValidationError
from ai_benefit_desk.config import PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CanonicalSourceModel, CoverageHistoryModel, ScanModel, SystemStateModel
)
from ai_benefit_desk.schemas.benefit_models import BenefitRecord
from ai_benefit_desk.schemas.protocol_models import (
    ScanImportPackage, BenefitChangeOperation, LeadChangeOperation, LeadRecord, CanonicalSourceItem, CoverageEventItem
)
from ai_benefit_desk.services.coverage_planner import CoveragePlanner
from ai_benefit_desk.services.vendor_pool_config import VendorPoolConfig
from ai_benefit_desk.utils.date_utils import is_review_due


class ValidationResult:
    def __init__(self):
        self.is_valid = True
        self.errors: List[str] = []
        self.warnings: List[Dict[str, Any]] = []
        self.evidence_gate_failures: List[Dict[str, Any]] = []
        self.coverage_gate_failures: List[Dict[str, Any]] = []
        self.duplicate_candidates: List[Dict[str, Any]] = []

    def add_error(self, msg: str):
        self.is_valid = False
        self.errors.append(msg)

    def add_warning(self, w_type: str, msg: str, related_ref: Optional[str] = None):
        self.warnings.append({
            "type": w_type,
            "message_zh": msg,
            "related_ref": related_ref
        })

def validate_merged_patch(
    existing_dict: Dict[str, Any],
    patch: Dict[str, Any],
    model_class: Any,
    immutable_fields: Optional[set] = None
) -> Any:
    if immutable_fields:
        for f in immutable_fields:
            if f in patch:
                raise ValueError(f"禁止修改 {f}")
    candidate = existing_dict.copy()
    candidate.update(patch)
    validated = model_class.model_validate(candidate)
    normalized_patch = {}
    for k in patch.keys():
        if hasattr(validated, k):
            normalized_patch[k] = getattr(validated, k)
    return validated, normalized_patch


class ValidationService:
    @staticmethod
    def validate_import_package(
        db: Session,
        import_pkg: ScanImportPackage,
        user_override_evidence: bool = False
    ) -> ValidationResult:
        result = ValidationResult()

        # 1. Protocol & Schema Version Validation
        if import_pkg.protocol_version != PROTOCOL_VERSION:
            result.add_error(f"协议版本不兼容: 导入版本 {import_pkg.protocol_version}，系统版本 {PROTOCOL_VERSION}")
        
        if import_pkg.benefit_schema_version != BENEFIT_SCHEMA_VERSION:
            result.add_error(f"福利Schema版本不兼容: 导入版本 {import_pkg.benefit_schema_version}，系统版本 {BENEFIT_SCHEMA_VERSION}")

        # 2. scan_id Binding & Idempotency Check
        scan_id = import_pkg.scan_result.scan_id
        scan_rec = db.query(ScanModel).filter_by(scan_id=scan_id).first()
        if not scan_rec:
            result.add_error(f"该 scan_id 不对应 Benefit Desk 已导出的扫描上下文。(scan_id: {scan_id})")
        else:
            if scan_rec.import_status == "COMMITTED":
                result.add_error(f"该扫描已经导入。(scan_id: {scan_id})")
            elif scan_rec.import_status != "EXPORTED":
                result.add_error(f"扫描批次状态非法 ({scan_rec.import_status})，仅允许导入已导出且未提交的扫描。(scan_id: {scan_id})")

            # Check baseline_revision_at_export strictly equals context_baseline_revision
            if scan_rec.baseline_revision_at_export != import_pkg.scan_result.context_baseline_revision:
                result.add_error(
                    f"扫描导出时的基线版本 ({scan_rec.baseline_revision_at_export}) 与导入包声明的上下文基线版本 ({import_pkg.scan_result.context_baseline_revision}) 不一致。"
                )

        # 3. Baseline State ↔ Baseline Action Consistency & Current DB Revision Check
        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        current_rev = sys_state.baseline_revision if sys_state else 0
        baseline_state = sys_state.baseline_state if sys_state else "EMPTY"
        
        if import_pkg.scan_result.context_baseline_revision != current_rev:
            result.add_error(
                f"扫描上下文已经过期，当前数据库基线已发生变化。(导入基线: {import_pkg.scan_result.context_baseline_revision}, 数据库当前基线: {current_rev})"
            )

        baseline_action = import_pkg.scan_result.baseline_action
        if baseline_state == "EMPTY" and baseline_action != "BUILD_INITIAL_BASELINE":
            result.add_error("当前系统基线为空 (EMPTY)，扫描动作必须为 BUILD_INITIAL_BASELINE。")
        elif baseline_state == "READY" and baseline_action != "UPDATE_EXISTING_BASELINE":
            result.add_error("当前系统基线已就绪 (READY)，扫描动作必须为 UPDATE_EXISTING_BASELINE。")

        # 4. Coverage & Scan Completion Consistency (Mandatory NOT_CHECKED Gate)
        scan_statuses = set(import_pkg.scan_result.scan_statuses)
        
        mandatory_not_checked = []
        non_mandatory_not_checked = []
        unknown_criticality_not_checked = []

        for c in import_pkg.coverage_events:
            if c.coverage_state == "NOT_CHECKED":
                crit = CoveragePlanner.is_mandatory_surface(c.vendor, c.product, c.surface)
                if crit is True:
                    mandatory_not_checked.append(c)
                elif crit is False:
                    non_mandatory_not_checked.append(c)
                else:
                    unknown_criticality_not_checked.append(c)

        if mandatory_not_checked:
            if "SCAN_INCOMPLETE" not in scan_statuses:
                result.add_error("存在关键待检查 (NOT_CHECKED) 项时，扫描状态必须包含 SCAN_INCOMPLETE")
            if "PUBLIC_COMPLETE" in scan_statuses:
                result.add_error("存在关键待检查 (NOT_CHECKED) 项时，扫描状态不能声明为公开扫描完成 (PUBLIC_COMPLETE)")

        if non_mandatory_not_checked:
            result.add_warning(
                "NON_MANDATORY_NOT_CHECKED",
                f"存在 {len(non_mandatory_not_checked)} 个非必查渠道未检查 (NOT_CHECKED) 项，不阻塞整轮扫描完成状态。"
            )

        if unknown_criticality_not_checked:
            result.add_warning(
                "COVERAGE_CRITICALITY_UNKNOWN",
                f"存在 {len(unknown_criticality_not_checked)} 个关键度未明确定义的渠道未检查 (NOT_CHECKED) 项，建议人工核对。"
            )

        # 5. Mode-specific & REVIEW_NOT_DUE Coverage Gate & Source ID Existence
        is_deep_scan = (import_pkg.scan_result.scan_mode == "DEEP_FULL_SCAN")
        today = date.today()

        for cov in import_pkg.coverage_events:
            # Permanent ID ownership check
            if cov.coverage_id is not None:
                result.add_error(f"Coverage Event 不能由外部指定 coverage_id，由 Benefit Desk 分配。(提供了: {cov.coverage_id})")
            if cov.scan_id and cov.scan_id != import_pkg.scan_result.scan_id:
                result.add_error(f"Coverage Event 的 scan_id ({cov.scan_id}) 与扫描批次 scan_id ({import_pkg.scan_result.scan_id}) 不一致。")


            # Cross-reference check: source_id
            if cov.source_id:
                s_exist = db.query(CanonicalSourceModel).filter_by(source_id=cov.source_id).first()
                if not s_exist:
                    result.add_error(f"Coverage 引用的 source_id 不存在: {cov.source_id}")

            # State-dependent actual_checked_at validation
            if cov.coverage_state in ("CHECKED_FOUND", "CHECKED_NONE"):
                if not cov.actual_checked_at or cov.actual_checked_at == "UNKNOWN":
                    msg = f"覆盖状态为 {cov.coverage_state} 时必须提供实际检查时间戳 (actual_checked_at)。(Vendor: {cov.vendor}, Product: {cov.product}, Surface: {cov.surface})"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})

            elif cov.coverage_state == "REVIEW_NOT_DUE":
                # Condition 1 & 2: Prohibit in DEEP_FULL_SCAN or non-FULL_SCAN
                if is_deep_scan or import_pkg.scan_result.scan_mode != "FULL_SCAN":
                    msg = f"深度全量扫描 (DEEP_FULL_SCAN) 或非普通全量扫描中禁止使用 REVIEW_NOT_DUE。(Vendor: {cov.vendor}, Product: {cov.product}, Surface: {cov.surface})"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                    continue

                # Condition 8: Prohibit on initial empty baseline
                if baseline_state == "EMPTY" or import_pkg.scan_result.baseline_action == "BUILD_INITIAL_BASELINE":
                    msg = f"首次建立基线 (EMPTY) 时禁止使用 REVIEW_NOT_DUE。(Vendor: {cov.vendor}, Product: {cov.product}, Surface: {cov.surface})"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                    continue

                # Condition 3 & 4: basis_coverage_id must exist
                if not cov.basis_coverage_id:
                    msg = f"REVIEW_NOT_DUE 必须指定依据的历史覆盖记录 (basis_coverage_id)。(Vendor: {cov.vendor}, Product: {cov.product}, Surface: {cov.surface})"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                    continue

                basis_cov = db.query(CoverageHistoryModel).filter_by(coverage_id=cov.basis_coverage_id).first()
                if not basis_cov:
                    msg = f"basis_coverage_id 不存在: {cov.basis_coverage_id}"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                    continue

                # Condition 5: basis Coverage must match vendor, product, surface, region
                if (basis_cov.vendor != cov.vendor or basis_cov.product != cov.product or
                    basis_cov.surface != cov.surface or basis_cov.region != cov.region):
                    msg = f"basis_coverage ({basis_cov.coverage_id}) 与当前渠道不匹配: 期望 ({cov.vendor}, {cov.product}, {cov.surface}, {cov.region})，实际 ({basis_cov.vendor}, {basis_cov.product}, {basis_cov.surface}, {basis_cov.region})"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                    continue

                # Condition 6: basis Coverage must prove prior actual check
                if basis_cov.coverage_state not in ("CHECKED_FOUND", "CHECKED_NONE"):
                    msg = f"basis_coverage ({basis_cov.coverage_id}) 状态为 {basis_cov.coverage_state}，未证明此前曾实际检查过"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                    continue

                # Condition 6.5: basis Coverage must have valid actual_checked_at
                if not basis_cov.actual_checked_at or basis_cov.actual_checked_at == "UNKNOWN":
                    msg = f"basis_coverage ({basis_cov.coverage_id}) 缺少有效的 actual_checked_at 时间戳"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                    continue

                # Condition 7: basis Coverage must have concrete next_review_at and must not be UNKNOWN / null
                if not basis_cov.next_review_at or basis_cov.next_review_at == "UNKNOWN":
                    msg = f"REVIEW_NOT_DUE 缺少明确的 next_review_at，无法证明复查尚未到期。(Vendor: {cov.vendor}, Product: {cov.product}, Surface: {cov.surface})"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                    continue

                # Condition 7.6: No forced early review signal
                force_reason = VendorPoolConfig.has_forced_review_signal(
                    cov.vendor, cov.product, cov.surface, cov.region
                )
                if force_reason:
                    msg = f"存在强制提前复查信号 ({force_reason})，禁止使用 REVIEW_NOT_DUE。(Vendor: {cov.vendor}, Product: {cov.product}, Surface: {cov.surface}, Region: {cov.region})"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                    continue

                # Condition 7.5: Current date must be strictly before next_review_at
                if is_review_due(basis_cov.next_review_at, ref_date=today):
                    msg = f"已达到或超过下次复查时间 ({basis_cov.next_review_at})，禁止继续使用 REVIEW_NOT_DUE。(Vendor: {cov.vendor}, Product: {cov.product}, Surface: {cov.surface})"
                    result.add_error(msg)
                    result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                    continue

            elif cov.coverage_state in ("NOT_CHECKED", "BLIND_SPOT", "NOT_APPLICABLE"):
                pass


        # 6. Global Local Ref Uniqueness & Benefit Operations Validation
        global_local_refs = set()
        created_benefit_refs = set()

        def check_local_ref(ref: Optional[str], op_name: str) -> bool:
            if not ref:
                result.add_error(f"{op_name} 操作必须提供 local_ref")
                return False
            if ref in global_local_refs:
                result.add_error(f"同一个 Import 内 local_ref 必须全局唯一: 重复的 local_ref {ref}")
                return False
            global_local_refs.add(ref)
            return True

        for bop in import_pkg.benefit_changes:
            if bop.operation == "CREATE":
                check_local_ref(bop.local_ref, "Benefit CREATE")
                created_benefit_refs.add(bop.local_ref)

                if bop.record:
                    if bop.record.benefit_id is not None:
                        result.add_error(f"新福利记录在 CREATE 时 benefit_id 必须为 null，永久 ID 由 Benefit Desk 分配。(提供了: {bop.record.benefit_id})")

                    # Evidence Gate for CONFIRMED
                    if bop.record.verification_status == "CONFIRMED":
                        s_level = bop.record.source_level
                        has_sa = (
                            s_level in ("S", "A") or
                            any(e.source_level in ("S", "A") for e in bop.evidence)
                        )
                        if not has_sa:
                            gate_msg = f"确认级别与证据不匹配: 福利 [{bop.local_ref}] 状态为 CONFIRMED，但缺乏 S 或 A 级第一方证据"
                            result.evidence_gate_failures.append({
                                "local_ref": bop.local_ref,
                                "message": gate_msg
                            })
                            if not user_override_evidence:
                                result.add_error(gate_msg)
                            else:
                                result.add_warning("EVIDENCE_MISMATCH", f"{gate_msg} (已人工覆盖)", bop.local_ref)

            elif bop.operation == "UPDATE":
                if not bop.benefit_id:
                    result.add_error("Benefit UPDATE 操作必须指定 benefit_id")
                else:
                    existing = db.query(BenefitModel).filter_by(benefit_id=bop.benefit_id).first()
                    if not existing:
                        result.add_error(f"Benefit UPDATE 指定的 benefit_id 不存在: {bop.benefit_id}")
                    else:
                        if bop.patch is None or not isinstance(bop.patch, dict) or not bop.patch:
                            result.add_error(f"Benefit UPDATE 必须提供非空 patch 字典 (benefit_id: {bop.benefit_id})")
                        else:
                            if "benefit_id" in bop.patch:
                                result.add_error(f"Benefit UPDATE patch 禁止修改 benefit_id (benefit_id: {bop.benefit_id})")

                            allowed_benefit_fields = set(BenefitRecord.model_fields.keys()) - {"benefit_id"}
                            for f_key in bop.patch.keys():
                                if f_key not in allowed_benefit_fields:
                                    result.add_error(f"Benefit UPDATE patch 包含非法外来字段: {f_key} (benefit_id: {bop.benefit_id})")

                            existing_dict = {
                                "benefit_id": existing.benefit_id,
                                "vendor": existing.vendor,
                                "product": existing.product,
                                "linked_vendor": existing.linked_vendor or "UNKNOWN",
                                "linked_product": existing.linked_product or "UNKNOWN",
                                "campaign_name": existing.campaign_name,
                                "benefit_type": existing.benefit_type,
                                "benefit_detail": existing.benefit_detail,
                                "linked_benefit_detail": existing.linked_benefit_detail or "UNKNOWN",
                                "wallet": existing.wallet or "UNKNOWN",
                                "amount": existing.amount or "UNKNOWN",
                                "unit": existing.unit or "UNKNOWN",
                                "reset_policy": existing.reset_policy or "UNKNOWN",
                                "grant_method": existing.grant_method or "UNKNOWN",
                                "regions": existing.regions,
                                "eligibility": existing.eligibility or "UNKNOWN",
                                "eligibility_class": existing.eligibility_class,
                                "start_date": existing.start_date or "UNKNOWN",
                                "end_date": existing.end_date or "UNKNOWN",
                                "first_seen": existing.first_seen,
                                "last_checked": existing.last_checked,
                                "next_review_date": existing.next_review_date or "UNKNOWN",
                                "claim_method": existing.claim_method or "UNKNOWN",
                                "credit_card_required": existing.credit_card_required or "UNKNOWN",
                                "verification_required": existing.verification_required or "UNKNOWN",
                                "official_source": existing.official_source,
                                "source_level": existing.source_level,
                                "verification_status": existing.verification_status,
                                "status": existing.status,
                                "change_type": existing.change_type or "UNKNOWN",
                                "account_risk": existing.account_risk or "NONE",
                                "region_risk": existing.region_risk or "UNKNOWN",
                                "compliance_risk": existing.compliance_risk or "NONE",
                                "notes": existing.notes or ""
                            }
                            patch_to_validate = bop.patch.copy()
                            if bop.change_type:
                                patch_to_validate["change_type"] = bop.change_type

                            validated_candidate = None
                            try:
                                validated_candidate, _ = validate_merged_patch(
                                    existing_dict, patch_to_validate, BenefitRecord, {"benefit_id"}
                                )
                            except ValidationError as ve:
                                for err in ve.errors():
                                    loc = ".".join(str(l) for l in err.get("loc", []))
                                    result.add_error(f"Benefit UPDATE patch 导致记录不符合 Schema 规范 ({loc}): {err.get('msg')} (benefit_id: {bop.benefit_id})")
                            except Exception as e:
                                result.add_error(f"Benefit UPDATE patch 校验失败: {str(e)} (benefit_id: {bop.benefit_id})")

                            # If patch changes or sets status to CONFIRMED
                            if validated_candidate and validated_candidate.verification_status == "CONFIRMED":
                                patch_s_level = validated_candidate.source_level
                                has_sa = (
                                    patch_s_level in ("S", "A") or
                                    any(e.source_level in ("S", "A") for e in bop.evidence)
                                )
                                if not has_sa:
                                    gate_msg = f"确认级别与证据不匹配: 更新福利 [{bop.benefit_id}] 状态为 CONFIRMED，但缺乏 S 或 A 级第一方证据"
                                    result.evidence_gate_failures.append({
                                        "benefit_id": bop.benefit_id,
                                        "message": gate_msg
                                    })
                                    if not user_override_evidence:
                                        result.add_error(gate_msg)
                                    else:
                                        result.add_warning("EVIDENCE_MISMATCH", f"{gate_msg} (已人工覆盖)", bop.benefit_id)

            elif bop.operation == "CONFIRM_NO_CHANGE":
                if not bop.benefit_id:
                    result.add_error("Benefit CONFIRM_NO_CHANGE 操作必须指定 benefit_id")
                else:
                    existing = db.query(BenefitModel).filter_by(benefit_id=bop.benefit_id).first()
                    if not existing:
                        result.add_error(f"Benefit CONFIRM_NO_CHANGE 指定的 benefit_id 不存在: {bop.benefit_id}")
                    if not bop.last_checked:
                        result.add_error(f"Benefit CONFIRM_NO_CHANGE 必须提供复核日期 (last_checked): {bop.benefit_id}")
                    if not bop.next_review_date:
                        result.add_error(f"Benefit CONFIRM_NO_CHANGE 必须提供下次复查日期 (next_review_date): {bop.benefit_id}")

        # 7. Lead Operations Validation
        for lop in import_pkg.lead_changes:
            if lop.operation == "CREATE":
                check_local_ref(lop.local_ref, "Lead CREATE")
                if getattr(lop, "lead_id", None) is not None:
                    result.add_error(f"新线索必须使用 local_ref，lead_id 由 Benefit Desk 分配。(提供了: {lop.lead_id})")
                if lop.verification_status == "CONFIRMED":
                    result.add_error("已确认线索必须通过 RESOLVE_TO_BENEFIT 转为正式福利，不能继续保留为 CONFIRMED Lead。")
                if not lop.vendor or not lop.lead_summary:
                    result.add_error(f"Lead CREATE 操作必须包含 vendor 和 lead_summary: {lop.local_ref}")
                if not lop.first_seen or not lop.last_checked:
                    result.add_error(f"Lead CREATE 必须提供 first_seen 和 last_checked 日期: {lop.local_ref}")

            elif lop.operation == "UPDATE":
                if not lop.lead_id:
                    result.add_error("Lead UPDATE 操作必须指定 lead_id")
                else:
                    existing_lead = db.query(LeadModel).filter_by(lead_id=lop.lead_id).first()
                    if not existing_lead:
                        result.add_error(f"Lead UPDATE 指定的 lead_id 不存在: {lop.lead_id}")
                    else:
                        if lop.patch is None or not isinstance(lop.patch, dict) or not lop.patch:
                            result.add_error(f"Lead UPDATE 必须提供非空 patch 字典 (lead_id: {lop.lead_id})")
                        else:
                            if "lead_id" in lop.patch:
                                result.add_error(f"Lead UPDATE patch 禁止修改 lead_id (lead_id: {lop.lead_id})")
                            existing_lead_dict = {
                                "lead_id": existing_lead.lead_id,
                                "vendor": existing_lead.vendor,
                                "product": existing_lead.product,
                                "lead_summary": existing_lead.lead_summary,
                                "verification_status": existing_lead.verification_status,
                                "source_level": existing_lead.source_level,
                                "regions": existing_lead.regions,
                                "missing_evidence": existing_lead.missing_evidence or "",
                                "first_seen": existing_lead.first_seen,
                                "last_checked": existing_lead.last_checked,
                                "next_review_date": existing_lead.next_review_date or "UNKNOWN",
                                "status": existing_lead.status,
                                "resolved_benefit_id": existing_lead.resolved_benefit_id,
                                "rejection_reason": existing_lead.rejection_reason
                            }

                            try:
                                validate_merged_patch(
                                    existing_lead_dict, lop.patch, LeadRecord, {"lead_id"}
                                )
                            except ValidationError as ve:
                                for err in ve.errors():
                                    loc = ".".join(str(l) for l in err.get("loc", []))
                                    result.add_error(f"Lead UPDATE patch 导致记录不符合 Schema 规范 ({loc}): {err.get('msg')} (lead_id: {lop.lead_id})")
                            except Exception as e:
                                result.add_error(f"Lead UPDATE patch 校验失败: {str(e)} (lead_id: {lop.lead_id})")

            elif lop.operation == "RESOLVE_TO_BENEFIT":
                if not lop.lead_id:
                    result.add_error("Lead RESOLVE_TO_BENEFIT 必须指定 lead_id")
                else:
                    existing_lead = db.query(LeadModel).filter_by(lead_id=lop.lead_id).first()
                    if not existing_lead:
                        result.add_error(f"Lead RESOLVE_TO_BENEFIT 指定的 lead_id 不存在: {lop.lead_id}")

                # target_benefit_ref and target_benefit_id must be mutually exclusive
                if lop.target_benefit_ref and lop.target_benefit_id:
                    result.add_error(f"Lead RESOLVE_TO_BENEFIT 中 target_benefit_ref 与 target_benefit_id 只能二选一 (lead_id: {lop.lead_id})")
                elif not lop.target_benefit_ref and not lop.target_benefit_id:
                    result.add_error(f"Lead RESOLVE_TO_BENEFIT 必须指定 target_benefit_ref 或 target_benefit_id (lead_id: {lop.lead_id})")
                elif lop.target_benefit_id:
                    b_exist = db.query(BenefitModel).filter_by(benefit_id=lop.target_benefit_id).first()
                    if not b_exist:
                        result.add_error(f"Lead RESOLVE_TO_BENEFIT 引用的 target_benefit_id 不存在: {lop.target_benefit_id}")
                elif lop.target_benefit_ref:
                    if lop.target_benefit_ref not in created_benefit_refs:
                        result.add_error(f"Lead RESOLVE_TO_BENEFIT 引用的 target_benefit_ref 未在当前导入包的 CREATE 中找到: {lop.target_benefit_ref}")

            elif lop.operation == "REJECT":
                if not lop.lead_id:
                    result.add_error("Lead REJECT 必须指定 lead_id")
                else:
                    existing_lead = db.query(LeadModel).filter_by(lead_id=lop.lead_id).first()
                    if not existing_lead:
                        result.add_error(f"Lead REJECT 指定的 lead_id 不存在: {lop.lead_id}")
                reason = lop.reason
                if not reason:
                    result.add_error(f"Lead REJECT 必须提供驳回原因 (lead_id: {lop.lead_id})")
                if not lop.checked_at:
                    result.add_error(f"Lead REJECT 必须提供检查时间戳 (checked_at) (lead_id: {lop.lead_id})")

        # 8. Source Updates Validation
        for sop in import_pkg.source_updates:
            if sop.operation == "ADD":
                check_local_ref(sop.local_ref, "Source ADD")
                if getattr(sop, "source_id", None) is not None:
                    result.add_error(f"新官方入口必须使用 local_ref，source_id 由 Benefit Desk 分配。(提供了: {sop.source_id})")
                if not sop.vendor or not sop.url or not sop.product or not sop.surface or not sop.source_name:
                    result.add_error(f"Source ADD 必须提供完整入口元数据 (vendor, product, surface, source_name, url): {sop.local_ref}")
                if not sop.last_verified_at:
                    result.add_error(f"Source ADD 必须提供 last_verified_at 时间戳: {sop.local_ref}")
            elif sop.operation == "UPDATE":
                if not sop.source_id:
                    result.add_error("Source UPDATE 必须指定 source_id")
                else:
                    s_exist = db.query(CanonicalSourceModel).filter_by(source_id=sop.source_id).first()
                    if not s_exist:
                        result.add_error(f"Source UPDATE 指定的 source_id 不存在: {sop.source_id}")
                    else:
                        if sop.patch is None or not isinstance(sop.patch, dict) or not sop.patch:
                            result.add_error(f"Source UPDATE 必须提供非空 patch 字典 (source_id: {sop.source_id})")
                        else:
                            if "source_id" in sop.patch:
                                result.add_error(f"Source UPDATE patch 禁止修改 source_id (source_id: {sop.source_id})")
                            existing_src_dict = {
                                "source_id": s_exist.source_id,
                                "vendor": s_exist.vendor,
                                "product": s_exist.product,
                                "surface": s_exist.surface,
                                "source_name": s_exist.source_name,
                                "url": s_exist.url,
                                "source_type": s_exist.source_type,
                                "source_level": s_exist.source_level,
                                "status": s_exist.status,
                                "last_verified_at": s_exist.last_verified_at
                            }

                            try:
                                validate_merged_patch(
                                    existing_src_dict, sop.patch, CanonicalSourceItem, {"source_id"}
                                )
                            except ValidationError as ve:
                                for err in ve.errors():
                                    loc = ".".join(str(l) for l in err.get("loc", []))
                                    result.add_error(f"Source UPDATE patch 导致记录不符合规范 ({loc}): {err.get('msg')} (source_id: {sop.source_id})")
                            except Exception as e:
                                result.add_error(f"Source UPDATE patch 校验失败: {str(e)} (source_id: {sop.source_id})")

            elif sop.operation == "DEPRECATE":
                if not sop.source_id:
                    result.add_error("Source DEPRECATE 必须指定 source_id")
                else:
                    s_exist = db.query(CanonicalSourceModel).filter_by(source_id=sop.source_id).first()
                    if not s_exist:
                        result.add_error(f"Source DEPRECATE 指定的 source_id 不存在: {sop.source_id}")
                if not sop.reason:
                    result.add_error(f"Source DEPRECATE 必须提供废弃原因 (reason) (source_id: {sop.source_id})")
                if not sop.last_verified_at:
                    result.add_error(f"Source DEPRECATE 必须提供 last_verified_at 时间戳 (source_id: {sop.source_id})")

        # 9. Manual Check Items Validation
        for mop in import_pkg.manual_check_items:

            if getattr(mop, "manual_check_id", None) is not None:
                result.add_error("新人工检查项必须使用 local_ref，manual_check_id 由 Benefit Desk 分配。")
            if not mop.local_ref:
                result.add_error("新人工检查项必须提供 local_ref。")
            else:
                if mop.local_ref in global_local_refs:
                    result.add_error(f"同一个 Import 内 local_ref 必须全局唯一: 重复的 local_ref {mop.local_ref}")
                else:
                    global_local_refs.add(mop.local_ref)

            if mop.related_benefit_id:
                b_exist = db.query(BenefitModel).filter_by(benefit_id=mop.related_benefit_id).first()
                if not b_exist:
                    result.add_error(f"Manual Check 引用的 related_benefit_id 不存在: {mop.related_benefit_id}")

            if mop.related_lead_id:
                l_exist = db.query(LeadModel).filter_by(lead_id=mop.related_lead_id).first()
                if not l_exist:
                    result.add_error(f"Manual Check 引用的 related_lead_id 不存在: {mop.related_lead_id}")


        return result
