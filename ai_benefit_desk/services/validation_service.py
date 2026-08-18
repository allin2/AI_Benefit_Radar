from typing import Dict, Any, List, Tuple
from sqlalchemy.orm import Session
from ai_benefit_desk.config import PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CanonicalSourceModel, ScanModel, SystemStateModel
)
from ai_benefit_desk.schemas.protocol_models import ScanImportPackage, BenefitChangeOperation, LeadChangeOperation

class ValidationResult:
    def __init__(self):
        self.is_valid = True
        self.errors: List[str] = []
        self.warnings: List[str] = []
        self.evidence_gate_failures: List[Dict[str, Any]] = []
        self.coverage_gate_failures: List[Dict[str, Any]] = []
        self.duplicate_candidates: List[Dict[str, Any]] = []

    def add_error(self, msg: str):
        self.is_valid = False
        self.errors.append(msg)

    def add_warning(self, msg: str):
        self.warnings.append(msg)

class ValidationService:
    @staticmethod
    def validate_import_package(db: Session, import_pkg: ScanImportPackage) -> ValidationResult:
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
        if import_pkg.scan_result.context_baseline_revision != current_rev:
            result.add_error(
                f"扫描上下文已经过期，当前数据库基线已发生变化。(导入基线: {import_pkg.scan_result.context_baseline_revision}, 数据库当前基线: {current_rev})"
            )

        # 4. Mode-specific Coverage Gates
        is_deep_scan = (
            import_pkg.scan_result.actual_scan_mode == "DEEP_FULL_SCAN" or 
            import_pkg.scan_result.requested_mode == "DEEP_FULL_SCAN"
        )
        for cov in import_pkg.coverage_events:
            if is_deep_scan and cov.coverage_state == "REVIEW_NOT_DUE":
                msg = f"深度全量扫描 (DEEP_FULL_SCAN) 中禁止使用 REVIEW_NOT_DUE。(Vendor: {cov.vendor}, Product: {cov.product}, Surface: {cov.surface})"
                result.add_error(msg)
                result.coverage_gate_failures.append({"vendor": cov.vendor, "product": cov.product, "surface": cov.surface, "reason": msg})

        # 5. Local Ref Uniqueness within Package
        local_refs = set()
        created_benefit_refs = set()
        for op in import_pkg.benefit_changes:
            if op.operation == "CREATE":
                if not op.local_ref:
                    result.add_error("Benefit CREATE 操作必须包含 local_ref")
                elif op.local_ref in local_refs:
                    result.add_error(f"同一个 Import 内 local_ref 必须唯一: 重复的 local_ref {op.local_ref}")
                else:
                    local_refs.add(op.local_ref)
                    created_benefit_refs.add(op.local_ref)
                
                if op.benefit_id:
                    result.add_error(f"Benefit CREATE 操作的 benefit_id 必须为 null，不能指定为: {op.benefit_id}")
            
            elif op.operation in ("UPDATE", "CONFIRM_NO_CHANGE"):
                if not op.benefit_id:
                    result.add_error(f"Benefit {op.operation} 操作必须指定已有的 benefit_id")
                else:
                    existing = db.query(BenefitModel).filter_by(benefit_id=op.benefit_id).first()
                    if not existing:
                        result.add_error(f"Benefit {op.operation} 指定的 benefit_id 不存在: {op.benefit_id}")

            # Evidence Gate: CONFIRMED requires S or A
            rec = op.benefit_record
            if rec.verification_status == "CONFIRMED" and rec.source_level not in ("S", "A"):
                warn_msg = f"确认级别与证据不匹配: 福利 [{rec.campaign_name}] 标记为 CONFIRMED，但证据等级为 {rec.source_level} (需要 S 或 A 级)"
                result.add_warning(warn_msg)
                result.evidence_gate_failures.append({
                    "campaign_name": rec.campaign_name,
                    "vendor": rec.vendor,
                    "source_level": rec.source_level,
                    "verification_status": rec.verification_status,
                    "message": warn_msg
                })

            # Check Baseline Action: Initial baseline long-term benefits should not be forced NEW
            if import_pkg.scan_result.baseline_action == "BUILD_INITIAL_BASELINE" and rec.change_type == "NEW":
                # Add warning / recommendation
                result.add_warning(f"首次基线导入建议保持 change_type 为 UNKNOWN 或 NO_CHANGE，避免将长期既有福利误标为 NEW: [{rec.campaign_name}]")

        # 6. Lead Operations Validation
        for lop in import_pkg.lead_changes:
            if lop.operation == "CREATE":
                if not lop.local_ref:
                    result.add_error("Lead CREATE 操作必须包含 local_ref")
                elif lop.local_ref in local_refs:
                    result.add_error(f"同一个 Import 内 local_ref 必须唯一: 重复的 local_ref {lop.local_ref}")
                else:
                    local_refs.add(lop.local_ref)
            elif lop.operation == "RESOLVE_TO_BENEFIT":
                if not lop.lead_id:
                    result.add_error("Lead RESOLVE_TO_BENEFIT 必须指定 lead_id")
                else:
                    existing_lead = db.query(LeadModel).filter_by(lead_id=lop.lead_id).first()
                    if not existing_lead:
                        result.add_error(f"Lead RESOLVE_TO_BENEFIT 指定的 lead_id 不存在: {lop.lead_id}")
                
                # Check resolved target
                if not lop.target_benefit_id and not lop.target_benefit_local_ref:
                    result.add_error(f"Lead RESOLVE_TO_BENEFIT 必须指定 target_benefit_id 或 target_benefit_local_ref")
                elif lop.target_benefit_id:
                    b_exist = db.query(BenefitModel).filter_by(benefit_id=lop.target_benefit_id).first()
                    if not b_exist:
                        result.add_error(f"Lead RESOLVE_TO_BENEFIT 引用的 target_benefit_id 不存在: {lop.target_benefit_id}")
                elif lop.target_benefit_local_ref:
                    if lop.target_benefit_local_ref not in created_benefit_refs:
                        result.add_error(f"Lead RESOLVE_TO_BENEFIT 引用的 target_benefit_local_ref 未在当前导入包的 CREATE 中找到: {lop.target_benefit_local_ref}")
            elif lop.operation == "REJECT":
                if not lop.lead_id:
                    result.add_error("Lead REJECT 必须指定 lead_id")
                if not lop.rejection_reason:
                    result.add_error(f"Lead REJECT 必须提供驳回原因 (lead_id: {lop.lead_id})")

        # 7. Source Updates Validation
        for sop in import_pkg.source_updates:
            if sop.operation not in ("ADD", "UPDATE", "DEPRECATE"):
                result.add_error(f"不支持的 Source 操作: {sop.operation} (只允许 ADD, UPDATE, DEPRECATE)")
            if sop.operation == "ADD":
                if sop.local_ref:
                    if sop.local_ref in local_refs:
                        result.add_error(f"同一个 Import 内 local_ref 必须唯一: {sop.local_ref}")
                    local_refs.add(sop.local_ref)
            elif sop.operation in ("UPDATE", "DEPRECATE"):
                if not sop.source_id:
                    result.add_error(f"Source {sop.operation} 必须指定 source_id")
                else:
                    s_exist = db.query(CanonicalSourceModel).filter_by(source_id=sop.source_id).first()
                    if not s_exist:
                        result.add_error(f"Source {sop.operation} 指定的 source_id 不存在: {sop.source_id}")

        return result
