import pytest
import os
import json
from pathlib import Path
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CoverageHistoryModel, CanonicalSourceModel,
    UserBenefitStateModel, ScanModel, ImportAuditModel, SystemStateModel
)
from ai_benefit_desk.services.export_service import ExportService
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.services.validation_service import ValidationService
from ai_benefit_desk.schemas.protocol_models import (
    ScanContextPackage, ScanImportPackage, WarningItem
)
from ai_benefit_desk.utils.json_utils import loads_json, dumps_json

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def load_fixture(filename: str) -> str:
    with open(FIXTURES_DIR / filename, "r", encoding="utf-8") as f:
        return f.read()

# COMPLIANCE-001: canonical SCAN_CONTEXT 最小 JSON 能够成功 parse，Export 再生成字段和 canonical 一致
def test_compliance_001_scan_context_golden(db_session):
    raw = load_fixture("canonical_scan_context_v0_1.json")
    pkg = ScanContextPackage.model_validate_json(raw)
    assert pkg.package_type == "SCAN_CONTEXT"
    assert pkg.scan.requested_mode == "FULL_SCAN"
    assert "GLOBAL" in pkg.scan.regions

    exported = ExportService.generate_scan_context(db_session, requested_mode="FULL_SCAN")
    assert exported.package_type == "SCAN_CONTEXT"
    assert exported.scan.protocol_version == "0.1"
    assert exported.scan.benefit_schema_version == "1.2.1"
    assert exported.scan.regions == ["CN", "TW", "US", "GLOBAL"]

# COMPLIANCE-002: canonical SCAN_IMPORT 最小 JSON 能够成功 parse
def test_compliance_002_scan_import_golden(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is True
    assert preview["preview"]["benefit_create_count"] == 1
    assert preview["preview"]["source_add_count"] == 1
    assert preview["preview"]["coverage_recheck_count"] == 1

# COMPLIANCE-003: SCAN_IMPORT 使用旧/错误字段必须失败
def test_compliance_003_invalid_legacy_scan_import_fails(db_session):
    raw = load_fixture("invalid_legacy_scan_import.json")
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is False
    assert any("数据结构不符合 Protocol / Schema 规范" in e for e in preview["errors"])

# COMPLIANCE-004: UPDATE 只 patch end_date，数据库其他 Benefit 字段保持不变
def test_compliance_004_update_patch_semantics(db_session):
    # Setup initial benefit
    raw_init = load_fixture("canonical_scan_import_v0_1.json")
    p_init = ImportService.parse_and_preview(db_session, raw_init)
    ImportService.commit_import(db_session, p_init["import_pkg"], raw_init)

    b_before = db_session.query(BenefitModel).filter_by(benefit_id="BEN-000001").first()
    orig_amount = b_before.amount
    orig_wallet = b_before.wallet
    orig_detail = b_before.benefit_detail
    orig_status = b_before.status

    # Apply patch
    raw_patch = load_fixture("canonical_scan_import_update_patch_v0_1.json")
    p_patch = ImportService.parse_and_preview(db_session, raw_patch)
    assert p_patch["is_valid"] is True
    ImportService.commit_import(db_session, p_patch["import_pkg"], raw_patch)

    b_after = db_session.query(BenefitModel).filter_by(benefit_id="BEN-000001").first()
    assert b_after.end_date == "2026-09-30"
    assert b_after.next_review_date == "2026-09-15"
    assert b_after.change_type == "EXTENDED"
    # Unpatched fields untouched!
    assert b_after.amount == orig_amount
    assert b_after.wallet == orig_wallet
    assert b_after.benefit_detail == orig_detail
    assert b_after.status == orig_status

# COMPLIANCE-005: UPDATE 不存在 benefit_id → FAIL
def test_compliance_005_update_nonexistent_fails(db_session):
    payload = {
        "protocol_version": "0.1",
        "benefit_schema_version": "1.2.1",
        "package_type": "SCAN_IMPORT",
        "scan_result": {
            "scan_id": "SCAN-20260818-005",
            "scan_mode": "FULL_SCAN",
            "context_baseline_revision": 0,
            "generated_at": "2026-08-18T18:00:00+08:00",
            "scan_statuses": ["PUBLIC_COMPLETE"],
            "baseline_action": "UPDATE_EXISTING_BASELINE"
        },
        "benefit_changes": [
            {
                "operation": "UPDATE",
                "benefit_id": "BEN-999999",
                "patch": {"end_date": "2026-10-01"}
            }
        ],
        "lead_changes": [],
        "coverage_events": [],
        "source_updates": [],
        "manual_check_items": [],
        "warnings": []
    }
    preview = ImportService.parse_and_preview(db_session, dumps_json(payload))
    assert preview["is_valid"] is False
    assert any("BEN-999999" in e for e in preview["errors"])

# COMPLIANCE-006: CREATE benefit_id != null → FAIL
def test_compliance_006_create_with_non_null_id_fails(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    data = loads_json(raw)
    data["benefit_changes"][0]["record"]["benefit_id"] = "BEN-000001"
    preview = ImportService.parse_and_preview(db_session, dumps_json(data))
    assert preview["is_valid"] is False
    assert any("benefit_id 必须为 null" in e for e in preview["errors"])

# COMPLIANCE-007: CONFIRMED + 只有 C evidence → 默认 Evidence Gate 阻止确认导入
def test_compliance_007_evidence_gate_blocking(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    data = loads_json(raw)
    data["benefit_changes"][0]["record"]["source_level"] = "C"
    data["benefit_changes"][0]["evidence"] = [
        {
            "url": "https://reddit.com/r/ai",
            "source_level": "C",
            "source_role": "PRIMARY",
            "checked_at": "2026-08-18T17:20:00+08:00",
            "supports_fields": ["status"]
        }
    ]
    preview = ImportService.parse_and_preview(db_session, dumps_json(data))
    assert preview["is_valid"] is False
    assert any("确认级别与证据不匹配" in e for e in preview["errors"])

# COMPLIANCE-008: CONFIRMED + S evidence → 通过 Evidence Gate
def test_compliance_008_evidence_gate_passes_with_s(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is True

# COMPLIANCE-009: 人工 Evidence Override 只有明确用户操作才能继续并保存 Audit
def test_compliance_009_evidence_override_audited(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    data = loads_json(raw)
    data["benefit_changes"][0]["record"]["source_level"] = "C"
    data["benefit_changes"][0]["evidence"] = [
        {
            "url": "https://reddit.com/r/ai",
            "source_level": "C",
            "source_role": "PRIMARY",
            "checked_at": "2026-08-18T17:20:00+08:00",
            "supports_fields": ["status"]
        }
    ]
    raw_override = dumps_json(data)
    preview = ImportService.parse_and_preview(db_session, raw_override, user_override_evidence=True)
    assert preview["is_valid"] is True
    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw_override, user_override_evidence=True)
    assert commit_res["success"] is True

    audit = db_session.query(ImportAuditModel).filter_by(scan_id="SCAN-20260818-001").first()
    assert audit is not None
    assert any(w["type"] == "EVIDENCE_MISMATCH" for w in audit.warnings)

# COMPLIANCE-010: FULL_SCAN + 合法 REVIEW_NOT_DUE 通过，actual_checked_at 保持旧值
def test_compliance_010_review_not_due_passes(db_session):
    # 1. Setup initial import with basis coverage COV-000001 (actual_checked_at = 2026-08-15)
    raw_init = load_fixture("canonical_scan_import_v0_1.json")
    data_init = loads_json(raw_init)
    data_init["coverage_events"][0]["actual_checked_at"] = "2026-08-15"
    data_init["coverage_events"][0]["next_review_at"] = "2026-09-30"
    raw_i = dumps_json(data_init)
    p_init = ImportService.parse_and_preview(db_session, raw_i)
    ImportService.commit_import(db_session, p_init["import_pkg"], raw_i)

    # 2. Re-import with REVIEW_NOT_DUE referencing COV-000001
    raw_rnd = load_fixture("canonical_scan_import_review_not_due_v0_1.json")
    data_rnd = loads_json(raw_rnd)
    data_rnd["scan_result"]["context_baseline_revision"] = 1
    raw_rnd_json = dumps_json(data_rnd)
    p_rnd = ImportService.parse_and_preview(db_session, raw_rnd_json)
    assert p_rnd["is_valid"] is True
    ImportService.commit_import(db_session, p_rnd["import_pkg"], raw_rnd_json)

    cov2 = db_session.query(CoverageHistoryModel).filter_by(coverage_state="REVIEW_NOT_DUE").first()
    assert cov2 is not None
    assert cov2.actual_checked_at == "2026-08-15"  # Preserved!

# COMPLIANCE-011: DEEP_FULL_SCAN + REVIEW_NOT_DUE → FAIL
def test_compliance_011_deep_scan_prohibits_review_not_due(db_session):
    # Setup baseline ready first
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 2
    db_session.commit()

    raw_rnd = load_fixture("canonical_scan_import_review_not_due_v0_1.json")
    data_rnd = loads_json(raw_rnd)
    data_rnd["scan_result"]["scan_mode"] = "DEEP_FULL_SCAN"
    preview = ImportService.parse_and_preview(db_session, dumps_json(data_rnd))
    assert preview["is_valid"] is False
    assert any("DEEP_FULL_SCAN" in e for e in preview["errors"])

# COMPLIANCE-012: REVIEW_NOT_DUE 无 basis_coverage_id → FAIL
def test_compliance_012_review_not_due_no_basis_fails(db_session):
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 2
    db_session.commit()

    raw_rnd = load_fixture("canonical_scan_import_review_not_due_v0_1.json")
    data_rnd = loads_json(raw_rnd)
    data_rnd["coverage_events"][0]["basis_coverage_id"] = None
    preview = ImportService.parse_and_preview(db_session, dumps_json(data_rnd))
    assert preview["is_valid"] is False
    assert any("必须指定依据的历史覆盖记录" in e for e in preview["errors"])

# COMPLIANCE-013: basis coverage planning key 不匹配 → FAIL
def test_compliance_013_basis_coverage_mismatch_fails(db_session):
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 2
    db_session.commit()

    # Insert coverage for Gemini
    c = CoverageHistoryModel(
        coverage_id="COV-000099",
        scan_id="SCAN-PREV",
        vendor="Google",
        product="Gemini",
        surface="Free / Signup",
        region="GLOBAL",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01",
        actual_checked_at="2026-08-01"
    )
    db_session.add(c)
    db_session.commit()

    raw_rnd = load_fixture("canonical_scan_import_review_not_due_v0_1.json")
    data_rnd = loads_json(raw_rnd)
    # Basis coverage points to Google Gemini, but event is OpenAI ChatGPT
    data_rnd["coverage_events"][0]["basis_coverage_id"] = "COV-000099"
    preview = ImportService.parse_and_preview(db_session, dumps_json(data_rnd))
    assert preview["is_valid"] is False
    assert any("与当前渠道不匹配" in e for e in preview["errors"])

# COMPLIANCE-014: 已达到 next_review_at 仍使用 REVIEW_NOT_DUE → FAIL
def test_compliance_014_review_not_due_overdue_fails(db_session):
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 2
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-000088",
        scan_id="SCAN-PREV",
        vendor="OpenAI",
        product="ChatGPT",
        surface="Free / Signup",
        region="GLOBAL",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01",
        actual_checked_at="2026-08-01",
        next_review_at="2026-08-10"  # Expired/overdue!
    )
    db_session.add(c)
    db_session.commit()

    raw_rnd = load_fixture("canonical_scan_import_review_not_due_v0_1.json")
    data_rnd = loads_json(raw_rnd)
    data_rnd["coverage_events"][0]["basis_coverage_id"] = "COV-000088"
    preview = ImportService.parse_and_preview(db_session, dumps_json(data_rnd))
    assert preview["is_valid"] is False
    assert any("已达到或超过下次复查时间" in e for e in preview["errors"])

# COMPLIANCE-015: baseline_state = EMPTY + REVIEW_NOT_DUE → FAIL
def test_compliance_015_empty_baseline_prohibits_review_not_due(db_session):
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    assert sys_state.baseline_state == "EMPTY"

    raw_rnd = load_fixture("canonical_scan_import_review_not_due_v0_1.json")
    preview = ImportService.parse_and_preview(db_session, raw_rnd)
    assert preview["is_valid"] is False
    assert any("首次建立基线 (EMPTY) 时禁止使用 REVIEW_NOT_DUE" in e for e in preview["errors"])

# COMPLIANCE-016: 关键 NOT_CHECKED + PUBLIC_COMPLETE 产生阻塞错误
def test_compliance_016_not_checked_public_complete_fails(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    data = loads_json(raw)
    data["coverage_events"].append({
        "vendor": "OpenAI",
        "product": "API",
        "wallet": "UNKNOWN",
        "surface": "API Credits",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-18",
        "actual_checked_at": "UNKNOWN"
    })
    preview = ImportService.parse_and_preview(db_session, dumps_json(data))
    assert preview["is_valid"] is False
    assert any("存在关键待检查 (NOT_CHECKED) 项时，扫描状态不能声明为公开扫描完成" in e for e in preview["errors"])

# COMPLIANCE-017: PUBLIC_COMPLETE + OVERALL_PARTIAL + BLIND_SPOT 合法
def test_compliance_017_blind_spot_partial_valid(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    data = loads_json(raw)
    data["coverage_events"].append({
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "wallet": "UNKNOWN",
        "surface": "Hidden Account",
        "region": "GLOBAL",
        "coverage_state": "BLIND_SPOT",
        "scan_observed_at": "2026-08-18",
        "actual_checked_at": "2026-08-18"
    })
    preview = ImportService.parse_and_preview(db_session, dumps_json(data))
    assert preview["is_valid"] is True

# COMPLIANCE-018: Lead 使用 target_benefit_ref 正确 resolve 到同 Import 新 Benefit
def test_compliance_018_lead_resolve_to_new_benefit(db_session):
    lead = LeadModel(
        lead_id="LEAD-000001",
        vendor="Anthropic",
        product="Claude Code",
        lead_summary="传言新额度",
        verification_status="LIKELY",
        source_level="B",
        first_seen="2026-08-10",
        last_checked="2026-08-10",
        status="OPEN"
    )
    db_session.add(lead)
    db_session.commit()

    raw = load_fixture("canonical_scan_import_lead_resolve_v0_1.json")
    data = loads_json(raw)
    data["scan_result"]["context_baseline_revision"] = 0
    raw_json = dumps_json(data)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True
    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)

    updated_lead = db_session.query(LeadModel).filter_by(lead_id="LEAD-000001").first()
    assert updated_lead.status == "RESOLVED"
    assert updated_lead.resolved_benefit_id == "BEN-000001"

# COMPLIANCE-019: Lead target_benefit_id 正确 resolve 到历史 Benefit
def test_compliance_019_lead_resolve_to_existing_benefit(db_session):
    b = BenefitModel(
        benefit_id="BEN-000077",
        vendor="Google",
        product="Gemini",
        campaign_name="Gemini Trial",
        benefit_type="FREE_ACCESS",
        benefit_detail="试用",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://gemini.google.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    lead = LeadModel(
        lead_id="LEAD-000002",
        vendor="Google",
        product="Gemini",
        lead_summary="线索",
        verification_status="LIKELY",
        source_level="B",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        status="OPEN"
    )
    db_session.add(b)
    db_session.add(lead)
    db_session.commit()

    payload = {
        "protocol_version": "0.1",
        "benefit_schema_version": "1.2.1",
        "package_type": "SCAN_IMPORT",
        "scan_result": {
            "scan_id": "SCAN-20260818-019",
            "scan_mode": "FULL_SCAN",
            "context_baseline_revision": 0,
            "generated_at": "2026-08-18T18:00:00+08:00",
            "scan_statuses": ["PUBLIC_COMPLETE"],
            "baseline_action": "UPDATE_EXISTING_BASELINE"
        },
        "benefit_changes": [],
        "lead_changes": [
            {
                "operation": "RESOLVE_TO_BENEFIT",
                "lead_id": "LEAD-000002",
                "target_benefit_id": "BEN-000077"
            }
        ],
        "coverage_events": [],
        "source_updates": [],
        "manual_check_items": [],
        "warnings": []
    }
    preview = ImportService.parse_and_preview(db_session, dumps_json(payload))
    assert preview["is_valid"] is True
    ImportService.commit_import(db_session, preview["import_pkg"], dumps_json(payload))

    updated_lead = db_session.query(LeadModel).filter_by(lead_id="LEAD-000002").first()
    assert updated_lead.status == "RESOLVED"
    assert updated_lead.resolved_benefit_id == "BEN-000077"

# COMPLIANCE-020: target_benefit_ref + target_benefit_id 同时出现 → FAIL
def test_compliance_020_lead_resolve_conflict_fails(db_session):
    payload = {
        "protocol_version": "0.1",
        "benefit_schema_version": "1.2.1",
        "package_type": "SCAN_IMPORT",
        "scan_result": {
            "scan_id": "SCAN-20260818-020",
            "scan_mode": "FULL_SCAN",
            "context_baseline_revision": 0,
            "generated_at": "2026-08-18T18:00:00+08:00",
            "scan_statuses": ["PUBLIC_COMPLETE"],
            "baseline_action": "UPDATE_EXISTING_BASELINE"
        },
        "benefit_changes": [],
        "lead_changes": [
            {
                "operation": "RESOLVE_TO_BENEFIT",
                "lead_id": "LEAD-000001",
                "target_benefit_ref": "BNEW-001",
                "target_benefit_id": "BEN-000001"
            }
        ],
        "coverage_events": [],
        "source_updates": [],
        "manual_check_items": [],
        "warnings": []
    }
    preview = ImportService.parse_and_preview(db_session, dumps_json(payload))
    assert preview["is_valid"] is False
    assert any("只能二选一" in e for e in preview["errors"])

# COMPLIANCE-021: warnings 输出为结构化对象，不是 string list
def test_compliance_021_structured_warnings(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    data = loads_json(raw)
    data["warnings"] = [
        {
            "type": "REGION_UNCERTAIN",
            "message_zh": "该福利官方页面没有明确地区范围。",
            "related_ref": "BNEW-001"
        }
    ]
    preview = ImportService.parse_and_preview(db_session, dumps_json(data))
    assert preview["is_valid"] is True
    assert len(preview["warnings"]) >= 1
    w = preview["warnings"][0]
    assert isinstance(w, dict)
    assert w["type"] == "REGION_UNCERTAIN"
    assert w["related_ref"] == "BNEW-001"

# COMPLIANCE-022: 重复 scan_id 第二次导入失败
def test_compliance_022_duplicate_scan_id_blocked(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    preview1 = ImportService.parse_and_preview(db_session, raw)
    ImportService.commit_import(db_session, preview1["import_pkg"], raw)

    preview2 = ImportService.parse_and_preview(db_session, raw)
    assert preview2["is_valid"] is False
    assert any("该扫描已经导入" in e for e in preview2["errors"])

# COMPLIANCE-023: baseline_revision mismatch 检测冲突
def test_compliance_023_baseline_mismatch_detected(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    data = loads_json(raw)
    data["scan_result"]["context_baseline_revision"] = 99  # Mismatch!
    preview = ImportService.parse_and_preview(db_session, dumps_json(data))
    assert preview["is_valid"] is False
    assert any("扫描上下文已经过期" in e for e in preview["errors"])

# COMPLIANCE-024: Import 不修改 CLAIMED (User Benefit State)
def test_compliance_024_user_benefit_state_isolation(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    p1 = ImportService.parse_and_preview(db_session, raw)
    ImportService.commit_import(db_session, p1["import_pkg"], raw)

    # User marks CLAIMED
    u = UserBenefitStateModel(benefit_id="BEN-000001", action_state="CLAIMED", notes="已领")
    db_session.add(u)
    db_session.commit()

    # Import patch that updates status to EXPIRED
    raw_patch = load_fixture("canonical_scan_import_update_patch_v0_1.json")
    p_patch = ImportService.parse_and_preview(db_session, raw_patch)
    ImportService.commit_import(db_session, p_patch["import_pkg"], raw_patch)

    u_after = db_session.query(UserBenefitStateModel).filter_by(benefit_id="BEN-000001").first()
    assert u_after.action_state == "CLAIMED"
    assert u_after.notes == "已领"

# COMPLIANCE-025: 事务中途异常整体 rollback
def test_compliance_025_atomic_rollback(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    data = loads_json(raw)
    data["source_updates"].append({
        "operation": "UPDATE",
        "source_id": "SRC-NONEXISTENT",
        "patch": {"url": "https://bad.com"}
    })
    raw_broken = dumps_json(data)
    preview = ImportService.parse_and_preview(db_session, raw_broken)
    
    with pytest.raises(Exception):
        ImportService.commit_import(db_session, preview["import_pkg"], raw_broken)

    b = db_session.query(BenefitModel).filter_by(vendor="OpenAI").first()
    assert b is None
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    assert sys_state.baseline_revision == 0

# COMPLIANCE-026: 首次 BUILD_INITIAL_BASELINE 长期既有 Benefit 不被自动强改成 NEW
def test_compliance_026_initial_baseline_change_type(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    data = loads_json(raw)
    data["benefit_changes"][0]["record"]["change_type"] = "NEW"
    data["scan_result"]["baseline_action"] = "BUILD_INITIAL_BASELINE"
    raw_json = dumps_json(data)
    p = ImportService.parse_and_preview(db_session, raw_json)
    ImportService.commit_import(db_session, p["import_pkg"], raw_json)

    b = db_session.query(BenefitModel).filter_by(vendor="OpenAI").first()
    assert b.change_type == "UNKNOWN"

# COMPLIANCE-027: Unknown Benefit fact 使用 "UNKNOWN", 新对象永久 ID 使用 null
def test_compliance_027_unknown_fact_vs_null_id(db_session):
    raw = load_fixture("canonical_scan_import_v0_1.json")
    data = loads_json(raw)
    rec = data["benefit_changes"][0]["record"]
    assert rec["benefit_id"] is None
    assert rec["wallet"] == "UNKNOWN"
    assert rec["start_date"] == "UNKNOWN"

# COMPLIANCE-028: 正式 Export 只产生 protocol_version = "0.1", benefit_schema_version = "1.2.1"
def test_compliance_028_export_versions(db_session):
    exported = ExportService.generate_scan_context(db_session, requested_mode="FULL_SCAN")
    assert exported.protocol_version == "0.1"
    assert exported.benefit_schema_version == "1.2.1"
    assert exported.scan.protocol_version == "0.1"
    assert exported.scan.benefit_schema_version == "1.2.1"
