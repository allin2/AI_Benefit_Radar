from datetime import date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ai_benefit_desk.config import PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CanonicalSourceModel, CoverageHistoryModel, ScanModel, SystemStateModel
)
from ai_benefit_desk.schemas.protocol_models import ScanImportPackage, BenefitChangeOperation, LeadChangeOperation
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

        # 2. Idempotency Check (scan_id)
        scan_id = import_pkg.scan_result.scan_id
        existing_scan = db.query(ScanModel).filter_by(scan_id=scan_id, import_status="COMMITTED").first()
        if existing_scan:
            result.add_error(f"该扫描已经导入。(scan_id: {scan_id})")

        # 3. Baseline Revision Concurrency Check
        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        current_rev = sys_state.baseline_revision if sys_state else 0
        baseline_state = sys_state.baseline_state if sys_state else "EMPTY"
        if import_pkg.scan_result.context_baseline_revision != current_rev:
            result.add_error(
                f"扫描上下文已经过期，当前数据库基线已发生变化。(导入基线: {import_pkg.scan_result.context_baseline_revision}, 数据库当前基线: {current_rev})"
            )

        # 4. Coverage & Scan Completion Consistency
        scan_statuses = set(import_pkg.scan_result.scan_statuses)
        has_not_checked = any(c.coverage_state == "NOT_CHECKED" for c in import_pkg.coverage_events)
        if has_not_checked and "PUBLIC_COMPLETE" in scan_statuses:
            result.add_error("存在关键待检查 (NOT_CHECKED) 项时，扫描状态不能声明为公开扫描完成 (PUBLIC_COMPLETE)")

        # 5. Mode-specific & REVIEW_NOT_DUE Coverage Gate
        is_deep_scan = (import_pkg.scan_result.scan_mode == "DEEP_FULL_SCAN")
        today = date.today()

        for cov in import_pkg.coverage_events:
            if cov.coverage_state == "REVIEW_NOT_DUE":
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

                # Condition 7: Current date must not have reached or passed next_review_at
                if basis_cov.next_review_at and basis_cov.next_review_at != "UNKNOWN":
                    if is_review_due(basis_cov.next_review_at, ref_date=today):
                        msg = f"已达到或超过下次复查时间 ({basis_cov.next_review_at})，禁止继续使用 REVIEW_NOT_DUE"
                        result.add_error(msg)
                        result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})
                        continue

        # 6. Local Ref Uniqueness & Benefit Operations Validation
        local_refs = set()
        created_benefit_refs = set()

        for bop in import_pkg.benefit_changes:
            if bop.operation == "CREATE":
                if not bop.local_ref:
                    result.add_error("Benefit CREATE 操作必须包含 local_ref")
                elif bop.local_ref in local_refs:
                    result.add_error(f"同一个 Import 内 local_ref 必须唯一: 重复的 local_ref {bop.local_ref}")
                else:
                    local_refs.add(bop.local_ref)
                    created_benefit_refs.add(bop.local_ref)

                if not bop.record:
                    result.add_error(f"Benefit CREATE 操作必须包含 record 对象: {bop.local_ref}")
                else:
                    if bop.record.benefit_id is not None:
                        result.add_error(f"Benefit CREATE 操作的 record.benefit_id 必须为 null，不能指定为: {bop.record.benefit_id}")
                    
                    # Evidence Gate check
                    rec = bop.record
                    if rec.verification_status == "CONFIRMED":
                        has_sa_evidence = (
                            rec.source_level in ("S", "A") or
                            any(e.source_level in ("S", "A") for e in bop.evidence)
                        )
                        if not has_sa_evidence:
                            gate_msg = f"确认级别与证据不匹配: 福利 [{rec.campaign_name}] 标记为 CONFIRMED，但缺乏 S 或 A 级第一方证据"
                            result.evidence_gate_failures.append({
                                "campaign_name": rec.campaign_name,
                                "vendor": rec.vendor,
                                "source_level": rec.source_level,
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
                    
                if bop.patch is None or not isinstance(bop.patch, dict):
                    result.add_error(f"Benefit UPDATE 操作必须提供 patch 字典 (benefit_id: {bop.benefit_id})")
                else:
                    if "benefit_id" in bop.patch:
                        result.add_error("Benefit UPDATE patch 禁止修改 benefit_id")
                    
                    # If patch changes status to CONFIRMED
                    if bop.patch.get("verification_status") == "CONFIRMED":
                        patch_s_level = bop.patch.get("source_level")
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

        # 7. Lead Operations Validation
        for lop in import_pkg.lead_changes:
            if lop.operation == "CREATE":
                if not lop.local_ref:
                    result.add_error("Lead CREATE 操作必须包含 local_ref")
                elif lop.local_ref in local_refs:
                    result.add_error(f"同一个 Import 内 local_ref 必须唯一: 重复的 local_ref {lop.local_ref}")
                else:
                    local_refs.add(lop.local_ref)
                if not lop.record:
                    result.add_error(f"Lead CREATE 操作必须包含 record 对象: {lop.local_ref}")

            elif lop.operation == "UPDATE":
                if not lop.lead_id:
                    result.add_error("Lead UPDATE 操作必须指定 lead_id")
                else:
                    existing_lead = db.query(LeadModel).filter_by(lead_id=lop.lead_id).first()
                    if not existing_lead:
                        result.add_error(f"Lead UPDATE 指定的 lead_id 不存在: {lop.lead_id}")
                if lop.patch is None or not isinstance(lop.patch, dict):
                    result.add_error(f"Lead UPDATE 必须提供 patch 字典 (lead_id: {lop.lead_id})")

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
                if not lop.rejection_reason:
                    result.add_error(f"Lead REJECT 必须提供驳回原因 (lead_id: {lop.lead_id})")

        # 8. Source Updates Validation
        for sop in import_pkg.source_updates:
            if sop.operation == "ADD":
                if not sop.local_ref:
                    result.add_error("Source ADD 操作必须包含 local_ref")
                elif sop.local_ref in local_refs:
                    result.add_error(f"同一个 Import 内 local_ref 必须唯一: {sop.local_ref}")
                else:
                    local_refs.add(sop.local_ref)
                if not sop.record:
                    result.add_error(f"Source ADD 必须提供 record 对象: {sop.local_ref}")
            elif sop.operation == "UPDATE":
                if not sop.source_id:
                    result.add_error("Source UPDATE 必须指定 source_id")
                else:
                    s_exist = db.query(CanonicalSourceModel).filter_by(source_id=sop.source_id).first()
                    if not s_exist:
                        result.add_error(f"Source UPDATE 指定的 source_id 不存在: {sop.source_id}")
                if sop.patch is None or not isinstance(sop.patch, dict):
                    result.add_error(f"Source UPDATE 必须提供 patch 字典 (source_id: {sop.source_id})")
            elif sop.operation == "DEPRECATE":
                if not sop.source_id:
                    result.add_error("Source DEPRECATE 必须指定 source_id")
                else:
                    s_exist = db.query(CanonicalSourceModel).filter_by(source_id=sop.source_id).first()
                    if not s_exist:
                        result.add_error(f"Source DEPRECATE 指定的 source_id 不存在: {sop.source_id}")

        return result
