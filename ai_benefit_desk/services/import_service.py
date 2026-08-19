import json
from datetime import datetime, date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ai_benefit_desk.config import PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CoverageHistoryModel, CanonicalSourceModel,
    UserBenefitStateModel, ManualCheckModel, ScanModel, ImportAuditModel, SystemStateModel
)
from ai_benefit_desk.schemas.benefit_models import BenefitRecord
from ai_benefit_desk.schemas.protocol_models import (
    ScanImportPackage, WarningItem, LeadRecord, CanonicalSourceItem
)
from ai_benefit_desk.services.validation_service import ValidationService, ValidationResult, validate_merged_patch
from ai_benefit_desk.services.dedup_service import DedupService
from ai_benefit_desk.services.id_service import IdService
from ai_benefit_desk.utils.json_utils import loads_json, dumps_json
from ai_benefit_desk.utils.date_utils import today_str, now_timezone_iso



class ImportService:
    @staticmethod
    def parse_and_preview(
        db: Session,
        raw_json_str: str,
        user_override_evidence: bool = False
    ) -> Dict[str, Any]:
        """Parse JSON, run all validation gates, detect duplicates, and generate preview."""
        try:
            data = loads_json(raw_json_str)
        except Exception as e:
            return {
                "is_valid": False,
                "errors": [f"JSON 解析失败: {str(e)}"],
                "warnings": [],
                "preview": None,
                "import_pkg": None
            }

        try:
            import_pkg = ScanImportPackage.model_validate(data)
        except Exception as e:
            return {
                "is_valid": False,
                "errors": [f"数据结构不符合 Protocol / Schema 规范 (字段或枚举错误): {str(e)}"],
                "warnings": [],
                "preview": None,
                "import_pkg": None
            }

        # Run Validation Service
        val_result: ValidationResult = ValidationService.validate_import_package(
            db, import_pkg, user_override_evidence=user_override_evidence
        )

        # Run Dedup Service
        duplicates = DedupService.detect_candidate_duplicates(db, import_pkg.benefit_changes)
        val_result.duplicate_candidates = duplicates

        # Calculate preview counts
        benefit_creates = [op for op in import_pkg.benefit_changes if op.operation == "CREATE"]
        benefit_updates = [op for op in import_pkg.benefit_changes if op.operation == "UPDATE"]
        benefit_no_changes = [op for op in import_pkg.benefit_changes if op.operation == "CONFIRM_NO_CHANGE"]

        lead_creates = [op for op in import_pkg.lead_changes if op.operation == "CREATE"]
        lead_updates = [op for op in import_pkg.lead_changes if op.operation == "UPDATE"]
        lead_resolves = [op for op in import_pkg.lead_changes if op.operation == "RESOLVE_TO_BENEFIT"]
        lead_rejects = [op for op in import_pkg.lead_changes if op.operation == "REJECT"]

        cov_rechecks = [c for c in import_pkg.coverage_events if c.coverage_state in ("CHECKED_FOUND", "CHECKED_NONE")]
        cov_review_not_due = [c for c in import_pkg.coverage_events if c.coverage_state == "REVIEW_NOT_DUE"]
        cov_blind_spots = [c for c in import_pkg.coverage_events if c.coverage_state == "BLIND_SPOT"]
        cov_not_checked = [c for c in import_pkg.coverage_events if c.coverage_state == "NOT_CHECKED"]

        src_adds = [s for s in import_pkg.source_updates if s.operation == "ADD"]
        src_updates = [s for s in import_pkg.source_updates if s.operation == "UPDATE"]
        src_deprecates = [s for s in import_pkg.source_updates if s.operation == "DEPRECATE"]

        preview_summary = {
            "scan_id": import_pkg.scan_result.scan_id,
            "scan_mode": import_pkg.scan_result.scan_mode,
            "generated_at": import_pkg.scan_result.generated_at,
            "scan_statuses": import_pkg.scan_result.scan_statuses,
            "context_baseline_revision": import_pkg.scan_result.context_baseline_revision,
            "baseline_action": import_pkg.scan_result.baseline_action,
            "summary_notes": getattr(import_pkg.scan_result, "summary_notes", ""),
            
            # Counts
            "benefit_create_count": len(benefit_creates),
            "benefit_update_count": len(benefit_updates),
            "benefit_no_change_count": len(benefit_no_changes),
            "duplicate_candidate_count": len(duplicates),
            
            "lead_create_count": len(lead_creates),
            "lead_update_count": len(lead_updates),
            "lead_resolve_count": len(lead_resolves),
            "lead_reject_count": len(lead_rejects),
            
            "coverage_event_count": len(import_pkg.coverage_events),
            "coverage_recheck_count": len(cov_rechecks),
            "coverage_review_not_due_count": len(cov_review_not_due),
            "coverage_blind_spot_count": len(cov_blind_spots),
            "coverage_not_checked_count": len(cov_not_checked),
            
            "source_add_count": len(src_adds),
            "source_update_count": len(src_updates),
            "source_deprecate_count": len(src_deprecates),
            
            "manual_check_count": len(import_pkg.manual_check_items),
            
            # Detailed Objects
            "benefit_changes": import_pkg.benefit_changes,
            "lead_changes": import_pkg.lead_changes,
            "coverage_events": import_pkg.coverage_events,
            "source_updates": import_pkg.source_updates,
            "manual_check_items": import_pkg.manual_check_items,
            "duplicates": duplicates,
            "evidence_warnings": val_result.evidence_gate_failures,
            "coverage_errors": val_result.coverage_gate_failures,
        }

        # Combine package-level structured warnings and validation warnings
        package_warnings = [
            {"type": w.type, "message_zh": w.message_zh, "related_ref": w.related_ref}
            for w in import_pkg.warnings
        ]
        all_warnings = package_warnings + val_result.warnings

        return {
            "is_valid": val_result.is_valid,
            "errors": val_result.errors,
            "warnings": all_warnings,
            "preview": preview_summary,
            "import_pkg": import_pkg
        }

    @staticmethod
    def commit_import(
        db: Session,
        import_pkg: Any,
        raw_json_str: str = "",
        dedup_resolutions: Optional[Dict[str, str]] = None,
        user_override_evidence: bool = False
    ) -> Dict[str, Any]:
        """Commit import in a single atomic database transaction."""
        if isinstance(import_pkg, str) and not raw_json_str:
            raw_json_str = import_pkg
            import_pkg = None
        if import_pkg is None and raw_json_str:
            data = loads_json(raw_json_str)
            import_pkg = ScanImportPackage.model_validate(data)

        dedup_resolutions = dedup_resolutions or {}
        local_ref_to_id: Dict[str, str] = {}
        now = datetime.utcnow()

        try:
            # Re-validate to get full warnings and validation outcome
            val_res = ValidationService.validate_import_package(
                db, import_pkg, user_override_evidence=user_override_evidence
            )
            if not val_res.is_valid:
                raise ValueError(f"导入校验失败: {'; '.join(val_res.errors)}")

            # 1. Check system state & current revision
            sys_state = db.query(SystemStateModel).filter_by(id=1).with_for_update().first()
            if not sys_state:
                sys_state = SystemStateModel(id=1, baseline_revision=0, baseline_state="EMPTY")
                db.add(sys_state)
                db.flush()

            rev_before = sys_state.baseline_revision
            if import_pkg.scan_result.context_baseline_revision != rev_before:
                raise ValueError(f"基线版本冲突: 上下文基线为 {import_pkg.scan_result.context_baseline_revision}，当前数据库基线为 {rev_before}")

            # 2. Check scan_id existence, status & idempotency
            scan_rec = db.query(ScanModel).filter_by(scan_id=import_pkg.scan_result.scan_id).first()
            if not scan_rec:
                raise ValueError(f"该 scan_id 不对应 Benefit Desk 已导出的扫描上下文。(scan_id: {import_pkg.scan_result.scan_id})")
            if scan_rec.import_status == "COMMITTED":
                raise ValueError(f"该扫描已经导入。(scan_id: {import_pkg.scan_result.scan_id})")
            if scan_rec.import_status != "EXPORTED":
                raise ValueError(f"扫描批次状态非法 ({scan_rec.import_status})，仅允许导入已导出且未提交的扫描。(scan_id: {import_pkg.scan_result.scan_id})")
            if scan_rec.baseline_revision_at_export != import_pkg.scan_result.context_baseline_revision:
                raise ValueError(f"扫描导出时的基线版本 ({scan_rec.baseline_revision_at_export}) 与导入包声明的上下文基线版本 ({import_pkg.scan_result.context_baseline_revision}) 不一致。")

            # 2.5 Validate dedup resolutions (cycle detection & conflict resolution gate)
            DedupService.validate_dedup_resolutions(dedup_resolutions, import_pkg.benefit_changes)

            candidate_dups = DedupService.detect_candidate_duplicates(db, import_pkg.benefit_changes)
            for dup in candidate_dups:
                if dup.get("has_conflict"):
                    lref = dup.get("local_ref")
                    res = dedup_resolutions.get(lref)
                    if not res or (res not in ("KEEP_SEPARATE", "IGNORE") and not res.startswith("MERGE_LOCAL:")):
                        raise ValueError("存在尚未处理的冲突福利，请先选择处理方式。")

            # Handle intra-package candidate merges (MERGE_LOCAL)
            bop_by_ref = {bop.local_ref: bop for bop in import_pkg.benefit_changes if bop.operation == "CREATE" and bop.local_ref}
            for bop in import_pkg.benefit_changes:
                if bop.operation == "CREATE" and bop.local_ref:
                    res = dedup_resolutions.get(bop.local_ref)
                    if res and res.startswith("MERGE_LOCAL:"):
                        target_ref = res.split(":", 1)[1]
                        target_bop = bop_by_ref.get(target_ref)
                        if target_bop and target_bop.record and bop.record:
                            # Merge secondary facts and evidence into target primary candidate
                            target_bop.record = DedupService.merge_intra_package_candidates(target_bop.record, bop.record)
                            target_bop.evidence.extend(bop.evidence)


            # 3. Pre-generate permanent IDs for local_refs
            for bop in import_pkg.benefit_changes:
                if bop.operation == "CREATE" and bop.local_ref:
                    res = dedup_resolutions.get(bop.local_ref)
                    if res == "IGNORE" or (res and res.startswith("MERGE_LOCAL:")):
                        continue
                    elif res and res.startswith("UPDATE:"):
                        local_ref_to_id[bop.local_ref] = res.split(":", 1)[1]
                    else:
                        local_ref_to_id[bop.local_ref] = IdService.generate_benefit_id(db)

            # Map secondaries in MERGE_LOCAL to target's permanent ID
            for bop in import_pkg.benefit_changes:
                if bop.operation == "CREATE" and bop.local_ref:
                    res = dedup_resolutions.get(bop.local_ref)
                    if res and res.startswith("MERGE_LOCAL:"):
                        target_ref = res.split(":", 1)[1]
                        local_ref_to_id[bop.local_ref] = local_ref_to_id.get(target_ref, "")

            for lop in import_pkg.lead_changes:
                if lop.operation == "CREATE" and lop.local_ref:
                    local_ref_to_id[lop.local_ref] = IdService.generate_lead_id(db)

            for sop in import_pkg.source_updates:
                if sop.operation == "ADD" and sop.local_ref:
                    local_ref_to_id[sop.local_ref] = IdService.generate_source_id(db)

            for mop in import_pkg.manual_check_items:
                if mop.local_ref:
                    local_ref_to_id[mop.local_ref] = IdService.generate_manual_check_id(db)

            # 4. Process Benefit Changes
            for bop in import_pkg.benefit_changes:
                lref = getattr(bop, "local_ref", None)
                res = dedup_resolutions.get(lref) if lref else None
                if res == "IGNORE" or (res and res.startswith("MERGE_LOCAL:")):
                    continue

                if bop.operation == "CREATE" and (res and res.startswith("UPDATE:")):
                    target_b_id = res.split(":", 1)[1]
                    existing_b = db.query(BenefitModel).filter_by(benefit_id=target_b_id).first()
                    if not existing_b:
                        raise ValueError(f"要更新的已有福利不存在: {target_b_id}")

                    # Build dedup update patch (UNKNOWN-safe)
                    patch_dict = DedupService.build_dedup_update_patch(existing_b, bop.record)

                    # Merged candidate validation
                    existing_dict = {
                        "benefit_id": existing_b.benefit_id,
                        "vendor": existing_b.vendor,
                        "product": existing_b.product,
                        "linked_vendor": existing_b.linked_vendor or "UNKNOWN",
                        "linked_product": existing_b.linked_product or "UNKNOWN",
                        "campaign_name": existing_b.campaign_name,
                        "benefit_type": existing_b.benefit_type,
                        "benefit_detail": existing_b.benefit_detail,
                        "linked_benefit_detail": existing_b.linked_benefit_detail or "UNKNOWN",
                        "wallet": existing_b.wallet or "UNKNOWN",
                        "amount": existing_b.amount or "UNKNOWN",
                        "unit": existing_b.unit or "UNKNOWN",
                        "reset_policy": existing_b.reset_policy or "UNKNOWN",
                        "grant_method": existing_b.grant_method or "UNKNOWN",
                        "regions": existing_b.regions,
                        "eligibility": existing_b.eligibility or "UNKNOWN",
                        "eligibility_class": existing_b.eligibility_class,
                        "start_date": existing_b.start_date or "UNKNOWN",
                        "end_date": existing_b.end_date or "UNKNOWN",
                        "first_seen": existing_b.first_seen,
                        "last_checked": existing_b.last_checked,
                        "next_review_date": existing_b.next_review_date or "UNKNOWN",
                        "claim_method": existing_b.claim_method or "UNKNOWN",
                        "credit_card_required": existing_b.credit_card_required or "UNKNOWN",
                        "verification_required": existing_b.verification_required or "UNKNOWN",
                        "official_source": existing_b.official_source,
                        "source_level": existing_b.source_level,
                        "verification_status": existing_b.verification_status,
                        "status": existing_b.status,
                        "change_type": existing_b.change_type or "UNKNOWN",
                        "account_risk": existing_b.account_risk or "NONE",
                        "region_risk": existing_b.region_risk or "UNKNOWN",
                        "compliance_risk": existing_b.compliance_risk or "NONE",
                        "notes": existing_b.notes or ""
                    }
                    candidate_dict = existing_dict.copy()
                    candidate_dict.update(patch_dict)

                    BenefitRecord.model_validate(candidate_dict)

                    # Evidence Gate check
                    if candidate_dict.get("verification_status") == "CONFIRMED":
                        eff_src_lvl = candidate_dict.get("source_level")
                        has_sa = (
                            eff_src_lvl in ("S", "A") or
                            any(e.source_level in ("S", "A") for e in bop.evidence)
                        )
                        if not has_sa and not user_override_evidence:
                            raise ValueError(f"确认级别与证据不匹配: 更新福利 [{target_b_id}] 状态为 CONFIRMED，但缺乏 S 或 A 级第一方证据")

                    # Apply patch_dict
                    for k, v in patch_dict.items():
                        if k == "regions":
                            existing_b.regions = v
                        elif k == "eligibility_class":
                            existing_b.eligibility_class = v
                        elif hasattr(existing_b, k) and k not in ("id", "benefit_id", "first_seen", "created_at"):
                            setattr(existing_b, k, v)

                    local_ref_to_id[bop.local_ref] = existing_b.benefit_id
                    db.flush()

                elif bop.operation == "CREATE":
                    rec = bop.record
                    effective_change_type = rec.change_type

                    perm_id = local_ref_to_id[bop.local_ref]
                    b_model = BenefitModel(
                        benefit_id=perm_id,
                        vendor=rec.vendor,
                        product=rec.product,
                        linked_vendor=rec.linked_vendor or "UNKNOWN",
                        linked_product=rec.linked_product or "UNKNOWN",
                        campaign_name=rec.campaign_name,
                        benefit_type=rec.benefit_type,
                        benefit_detail=rec.benefit_detail,
                        linked_benefit_detail=rec.linked_benefit_detail or "UNKNOWN",
                        wallet=rec.wallet or "UNKNOWN",
                        amount=rec.amount or "UNKNOWN",
                        unit=rec.unit or "UNKNOWN",
                        reset_policy=rec.reset_policy or "UNKNOWN",
                        grant_method=rec.grant_method or "UNKNOWN",
                        eligibility=rec.eligibility or "UNKNOWN",
                        start_date=rec.start_date or "UNKNOWN",
                        end_date=rec.end_date or "UNKNOWN",
                        first_seen=rec.first_seen,
                        last_checked=rec.last_checked,
                        next_review_date=rec.next_review_date or "UNKNOWN",
                        claim_method=rec.claim_method or "UNKNOWN",
                        credit_card_required=rec.credit_card_required or "UNKNOWN",
                        verification_required=rec.verification_required or "UNKNOWN",
                        official_source=rec.official_source,
                        source_level=rec.source_level,
                        verification_status=rec.verification_status,
                        status=rec.status,
                        change_type=effective_change_type,
                        account_risk=rec.account_risk or "NONE",
                        region_risk=rec.region_risk or "UNKNOWN",
                        compliance_risk=rec.compliance_risk or "NONE",
                        notes=rec.notes or ""
                    )
                    b_model.regions = rec.regions
                    b_model.eligibility_class = rec.eligibility_class
                    db.add(b_model)

                elif bop.operation == "UPDATE":
                    target_b_id = bop.benefit_id
                    existing_b = db.query(BenefitModel).filter_by(benefit_id=target_b_id).first()
                    if not existing_b:
                        raise ValueError(f"要更新的福利不存在: {target_b_id}")

                    existing_dict = {
                        "benefit_id": existing_b.benefit_id,
                        "vendor": existing_b.vendor,
                        "product": existing_b.product,
                        "linked_vendor": existing_b.linked_vendor or "UNKNOWN",
                        "linked_product": existing_b.linked_product or "UNKNOWN",
                        "campaign_name": existing_b.campaign_name,
                        "benefit_type": existing_b.benefit_type,
                        "benefit_detail": existing_b.benefit_detail,
                        "linked_benefit_detail": existing_b.linked_benefit_detail or "UNKNOWN",
                        "wallet": existing_b.wallet or "UNKNOWN",
                        "amount": existing_b.amount or "UNKNOWN",
                        "unit": existing_b.unit or "UNKNOWN",
                        "reset_policy": existing_b.reset_policy or "UNKNOWN",
                        "grant_method": existing_b.grant_method or "UNKNOWN",
                        "regions": existing_b.regions,
                        "eligibility": existing_b.eligibility or "UNKNOWN",
                        "eligibility_class": existing_b.eligibility_class,
                        "start_date": existing_b.start_date or "UNKNOWN",
                        "end_date": existing_b.end_date or "UNKNOWN",
                        "first_seen": existing_b.first_seen,
                        "last_checked": existing_b.last_checked,
                        "next_review_date": existing_b.next_review_date or "UNKNOWN",
                        "claim_method": existing_b.claim_method or "UNKNOWN",
                        "credit_card_required": existing_b.credit_card_required or "UNKNOWN",
                        "verification_required": existing_b.verification_required or "UNKNOWN",
                        "official_source": existing_b.official_source,
                        "source_level": existing_b.source_level,
                        "verification_status": existing_b.verification_status,
                        "status": existing_b.status,
                        "change_type": existing_b.change_type or "UNKNOWN",
                        "account_risk": existing_b.account_risk or "NONE",
                        "region_risk": existing_b.region_risk or "UNKNOWN",
                        "compliance_risk": existing_b.compliance_risk or "NONE",
                        "notes": existing_b.notes or ""
                    }
                    patch_to_validate = (bop.patch or {}).copy()
                    if bop.change_type:
                        patch_to_validate["change_type"] = bop.change_type

                    validated_candidate, validated_patch = validate_merged_patch(
                        existing_dict, patch_to_validate, BenefitRecord, {"benefit_id"}
                    )

                    # Evidence Gate check
                    if validated_candidate.verification_status == "CONFIRMED":
                        patch_s_level = validated_candidate.source_level
                        has_sa = (
                            patch_s_level in ("S", "A") or
                            any(e.source_level in ("S", "A") for e in bop.evidence)
                        )
                        if not has_sa and not user_override_evidence:
                            raise ValueError(f"确认级别与证据不匹配: 更新福利 [{bop.benefit_id}] 状态为 CONFIRMED，但缺乏 S 或 A 级第一方证据")

                    # Apply normalized validated patch
                    for k, v in validated_patch.items():
                        if k == "regions":
                            existing_b.regions = v
                        elif k == "eligibility_class":
                            existing_b.eligibility_class = v
                        elif hasattr(existing_b, k) and k not in ("id", "benefit_id", "first_seen", "created_at"):
                            setattr(existing_b, k, v)

                    if bop.change_type:
                        existing_b.change_type = bop.change_type

                    db.flush()

                elif bop.operation == "CONFIRM_NO_CHANGE":
                    existing_b = db.query(BenefitModel).filter_by(benefit_id=bop.benefit_id).first()
                    if not existing_b:
                        raise ValueError(f"要复核的福利不存在: {bop.benefit_id}")
                    
                    existing_b.last_checked = bop.last_checked
                    existing_b.next_review_date = bop.next_review_date
                    existing_b.change_type = "NO_CHANGE"
                    db.flush()


            # 5. Process Lead Changes
            for lop in import_pkg.lead_changes:
                if lop.operation == "CREATE":
                    perm_lead_id = local_ref_to_id[lop.local_ref]
                    l_model = LeadModel(
                        lead_id=perm_lead_id,
                        vendor=lop.vendor,
                        product=lop.product,
                        lead_summary=lop.lead_summary,
                        verification_status=lop.verification_status,
                        source_level=lop.source_level,
                        missing_evidence=lop.missing_evidence or "",
                        first_seen=lop.first_seen,
                        last_checked=lop.last_checked,
                        next_review_date=lop.next_review_date or "UNKNOWN",
                        status="OPEN"
                    )
                    l_model.regions = lop.regions or ["UNKNOWN"]
                    db.add(l_model)

                elif lop.operation == "UPDATE":
                    existing_lead = db.query(LeadModel).filter_by(lead_id=lop.lead_id).first()
                    if not existing_lead:
                        raise ValueError(f"要更新的线索不存在: {lop.lead_id}")
                    
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
                    validated_lead, validated_patch = validate_merged_patch(
                        existing_lead_dict, lop.patch or {}, LeadRecord, {"lead_id"}
                    )
                    for k, v in validated_patch.items():
                        if k == "regions":
                            existing_lead.regions = v
                        elif hasattr(existing_lead, k) and k not in ("id", "lead_id", "created_at"):
                            setattr(existing_lead, k, v)

                elif lop.operation == "RESOLVE_TO_BENEFIT":
                    existing_lead = db.query(LeadModel).filter_by(lead_id=lop.lead_id).first()
                    if not existing_lead:
                        raise ValueError(f"要转福利的线索不存在: {lop.lead_id}")
                    
                    target_id = lop.target_benefit_id
                    if not target_id and lop.target_benefit_ref:
                        target_id = local_ref_to_id.get(lop.target_benefit_ref)
                    if not target_id:
                        raise ValueError(f"线索 {lop.lead_id} 转福利目标 ID 无法解析")
                    
                    existing_lead.status = "RESOLVED"
                    existing_lead.resolved_benefit_id = target_id

                elif lop.operation == "REJECT":
                    existing_lead = db.query(LeadModel).filter_by(lead_id=lop.lead_id).first()
                    if not existing_lead:
                        raise ValueError(f"要驳回的线索不存在: {lop.lead_id}")
                    existing_lead.status = "REJECTED"
                    existing_lead.rejection_reason = lop.reason or lop.rejection_reason
                    existing_lead.checked_at = lop.checked_at

            # 6. Process Coverage Events
            for cov in import_pkg.coverage_events:
                cov_id = IdService.generate_coverage_id(db)
                actual_chk_time = cov.actual_checked_at

                # Rule: REVIEW_NOT_DUE must NOT refresh actual_checked_at to scan date
                if cov.coverage_state == "REVIEW_NOT_DUE":
                    if cov.basis_coverage_id:
                        basis = db.query(CoverageHistoryModel).filter_by(coverage_id=cov.basis_coverage_id).first()
                        if basis:
                            actual_chk_time = basis.actual_checked_at
                elif cov.coverage_state in ("NOT_CHECKED", "BLIND_SPOT", "NOT_APPLICABLE"):
                    actual_chk_time = cov.actual_checked_at if (cov.actual_checked_at and cov.actual_checked_at != "UNKNOWN") else None

                cov_model = CoverageHistoryModel(
                    coverage_id=cov_id,
                    scan_id=import_pkg.scan_result.scan_id,
                    vendor=cov.vendor,
                    product=cov.product,
                    wallet=cov.wallet or "UNKNOWN",
                    surface=cov.surface,
                    region=cov.region,
                    coverage_state=cov.coverage_state,
                    scan_observed_at=cov.scan_observed_at,
                    actual_checked_at=actual_chk_time,
                    next_review_at=cov.next_review_at or "UNKNOWN",
                    source_id=cov.source_id,
                    basis_coverage_id=cov.basis_coverage_id,
                    notes=cov.notes or ""
                )
                db.add(cov_model)

            # 7. Process Source Updates
            for sop in import_pkg.source_updates:
                if sop.operation == "ADD":
                    src_id = local_ref_to_id[sop.local_ref]
                    src_model = CanonicalSourceModel(
                        source_id=src_id,
                        vendor=sop.vendor,
                        product=sop.product,
                        surface=sop.surface,
                        source_name=sop.source_name,
                        url=sop.url,
                        source_type=sop.source_type,
                        source_level=sop.source_level,
                        status=sop.status or "ACTIVE",
                        last_verified_at=sop.last_verified_at
                    )
                    db.add(src_model)
                elif sop.operation == "UPDATE":
                    existing_s = db.query(CanonicalSourceModel).filter_by(source_id=sop.source_id).first()
                    if not existing_s:
                        raise ValueError(f"要更新的官方入口不存在: {sop.source_id}")
                    
                    existing_src_dict = {
                        "source_id": existing_s.source_id,
                        "vendor": existing_s.vendor,
                        "product": existing_s.product,
                        "surface": existing_s.surface,
                        "source_name": existing_s.source_name,
                        "url": existing_s.url,
                        "source_type": existing_s.source_type,
                        "source_level": existing_s.source_level,
                        "status": existing_s.status,
                        "last_verified_at": existing_s.last_verified_at
                    }
                    validated_src, validated_patch = validate_merged_patch(
                        existing_src_dict, sop.patch or {}, CanonicalSourceItem, {"source_id"}
                    )
                    for k, v in validated_patch.items():
                        if hasattr(existing_s, k) and k not in ("id", "source_id", "created_at"):
                            setattr(existing_s, k, v)
                elif sop.operation == "DEPRECATE":
                    existing_s = db.query(CanonicalSourceModel).filter_by(source_id=sop.source_id).first()
                    if not existing_s:
                        raise ValueError(f"要废弃的官方入口不存在: {sop.source_id}")
                    existing_s.status = "DEPRECATED"
                    existing_s.deprecation_reason = sop.reason
                    existing_s.last_verified_at = sop.last_verified_at


            # 8. Process Manual Checks
            for mop in import_pkg.manual_check_items:
                m_id = local_ref_to_id[mop.local_ref]
                rel_b_id = mop.related_benefit_id
                if not rel_b_id and mop.local_ref and mop.local_ref in local_ref_to_id:
                    pass

                existing_m = db.query(ManualCheckModel).filter_by(manual_check_id=m_id).first()
                if not existing_m:
                    m_model = ManualCheckModel(
                        manual_check_id=m_id,
                        vendor=mop.vendor,
                        product=mop.product,
                        channel=mop.channel,
                        reason=mop.reason,
                        priority=mop.priority,
                        suggested_action=mop.suggested_action,
                        status="OPEN",
                        related_benefit_id=rel_b_id,
                        related_lead_id=mop.related_lead_id,
                        result_notes=""
                    )
                    db.add(m_model)


            # 9. Record Import Audit
            rev_after = rev_before + 1
            audit_record = ImportAuditModel(
                scan_id=import_pkg.scan_result.scan_id,
                imported_at=now,
                protocol_version=import_pkg.protocol_version,
                benefit_schema_version=import_pkg.benefit_schema_version,
                context_baseline_revision=import_pkg.scan_result.context_baseline_revision,
                database_revision_before=rev_before,
                database_revision_after=rev_after,
                raw_import_json=raw_json_str,
                user_confirmed=True,
                status="SUCCESS"
            )
            pkg_warnings = [
                {"type": w.type, "message_zh": w.message_zh, "related_ref": w.related_ref}
                for w in import_pkg.warnings
            ]
            audit_record.warnings = pkg_warnings + val_res.warnings
            db.add(audit_record)

            # 10. Update Scan Record
            scan_rec.actual_scan_mode = import_pkg.scan_result.scan_mode
            scan_rec.baseline_action = import_pkg.scan_result.baseline_action
            scan_rec.imported_at = now
            scan_rec.scan_statuses = import_pkg.scan_result.scan_statuses
            scan_rec.import_status = "COMMITTED"

            # 11. Increment System Revision & Set State
            sys_state.baseline_revision = rev_after
            sys_state.baseline_state = "READY"
            sys_state.updated_at = now

            db.commit()

            return {
                "success": True,
                "scan_id": import_pkg.scan_result.scan_id,
                "baseline_revision_before": rev_before,
                "baseline_revision_after": rev_after,
                "local_ref_map": local_ref_to_id
            }

        except Exception as e:
            db.rollback()
            raise e
