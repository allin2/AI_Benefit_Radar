import pytest
import json
from datetime import date
from pydantic import ValidationError
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CoverageHistoryModel, CanonicalSourceModel,
    UserBenefitStateModel, ManualCheckModel, ScanModel, ImportAuditModel, SystemStateModel
)
from ai_benefit_desk.services.export_service import ExportService
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.services.validation_service import ValidationService
from ai_benefit_desk.services.dedup_service import DedupService
from ai_benefit_desk.schemas.benefit_models import BenefitRecord
from ai_benefit_desk.schemas.protocol_models import (
    ScanContextPackage, ScanImportPackage, CoverageEventItem, ManualCheckItem, EvidenceItem
)
from ai_benefit_desk.utils.enum_labels import (
    VERIFICATION_STATUS_LABELS, STATUS_LABELS, COVERAGE_STATE_LABELS, USER_ACTION_STATE_LABELS
)
from ai_benefit_desk.utils.json_utils import dumps_json
from ai_benefit_desk.utils.date_utils import is_valid_timezone_iso8601, today_str


# Helper to create sample import payload
def make_sample_import(db_session, scan_id="SCAN-20260818-001", mode="FULL_SCAN", rev=0, baseline_action=None):
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    state = sys_state.baseline_state if sys_state else "EMPTY"
    if baseline_action is None:
        baseline_action = "BUILD_INITIAL_BASELINE" if state == "EMPTY" else "UPDATE_EXISTING_BASELINE"

    # Pre-register scan record in EXPORTED state if not exists
    existing = db_session.query(ScanModel).filter_by(scan_id=scan_id).first()
    if not existing:
        scan_rec = ScanModel(
            scan_id=scan_id,
            requested_mode=mode,
            baseline_revision_at_export=rev,
            import_status="EXPORTED"
        )
        db_session.add(scan_rec)
        db_session.commit()

    return {
        "protocol_version": "0.1",
        "benefit_schema_version": "1.2.1",
        "package_type": "SCAN_IMPORT",
        "scan_result": {
            "scan_id": scan_id,
            "scan_mode": mode,
            "context_baseline_revision": rev,
            "generated_at": "2026-08-18T18:00:00+08:00",
            "scan_statuses": ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"],
            "baseline_action": baseline_action,
            "summary_notes": "测试扫描"
        },
        "benefit_changes": [],
        "lead_changes": [],
        "coverage_events": [],
        "source_updates": [],
        "manual_check_items": [],
        "warnings": []
    }

# TEST-001: 首次 EMPTY Context 可以正常导出
def test_001_empty_context_export(db_session):
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    assert sys_state.baseline_state == "EMPTY"
    assert sys_state.baseline_revision == 0

    pkg = ExportService.generate_scan_context(db_session, requested_mode="FULL_SCAN")
    assert pkg.package_type == "SCAN_CONTEXT"
    assert pkg.scan.baseline_revision == 0
    assert pkg.scan.baseline_state == "EMPTY"
    assert pkg.scan.scan_id.startswith("SCAN-")
    assert len(pkg.benefit_index) == 0
    assert len(pkg.review_items) == 0

# TEST-002: CREATE Benefit 入库后生成永久 benefit_id
def test_002_create_benefit_generates_id(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-001", rev=0)
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-001",
        "record": {
            "benefit_id": None,
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "campaign_name": "Plus Free Trial",
            "benefit_type": "FREE_ACCESS",
            "benefit_detail": "新用户首月免费试用",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://openai.com/chatgpt",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE",
            "change_type": "NEW"
        }
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True
    assert preview["preview"]["benefit_create_count"] == 1

    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw_json)
    assert commit_res["success"] is True

    # Verify in DB
    b = db_session.query(BenefitModel).filter_by(vendor="OpenAI").first()
    assert b is not None
    assert b.benefit_id == "BEN-000001"
    assert b.campaign_name == "Plus Free Trial"
    
    # Check baseline revision incremented
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    assert sys_state.baseline_revision == 1
    assert sys_state.baseline_state == "READY"

# TEST-003: UPDATE 不存在 benefit_id → FAIL
def test_003_update_nonexistent_benefit_fails(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-002", rev=0)
    payload["benefit_changes"].append({
        "operation": "UPDATE",
        "benefit_id": "BEN-999999",
        "patch": {
            "end_date": "2026-09-30"
        }
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("BEN-999999" in err for err in preview["errors"])

# TEST-004: 同一个 scan_id 再次导入被幂等拦截
def test_004_idempotent_scan_import_blocked(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-003", rev=0)
    raw_json = dumps_json(payload)

    # First import
    preview1 = ImportService.parse_and_preview(db_session, raw_json)
    assert preview1["is_valid"] is True
    commit_res1 = ImportService.commit_import(db_session, preview1["import_pkg"], raw_json)
    assert commit_res1["success"] is True

    # Second import with same scan_id
    preview2 = ImportService.parse_and_preview(db_session, raw_json)
    assert preview2["is_valid"] is False
    assert any("该扫描已经导入" in err for err in preview2["errors"])

# TEST-005: baseline_revision 不匹配产生 BASELINE_CONFLICT
def test_005_baseline_revision_conflict(db_session):
    # DB current rev is 0, payload context_baseline_revision is 5
    payload = make_sample_import(db_session, "SCAN-20260818-004", rev=5)
    raw_json = dumps_json(payload)

    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("扫描上下文已经过期" in err for err in preview["errors"])

# TEST-006: REVIEW_NOT_DUE 不得刷新 actual_checked_at
def test_006_review_not_due_preserves_actual_checked_at(db_session):
    # Setup initial baseline with historical checked_at
    payload1 = make_sample_import(db_session, "SCAN-20260818-005", rev=0, baseline_action="BUILD_INITIAL_BASELINE")
    payload1["coverage_events"].append({
        "vendor": "Google",
        "product": "Gemini",
        "surface": "Web Pricing",
        "region": "GLOBAL",
        "coverage_state": "CHECKED_FOUND",
        "scan_observed_at": "2026-08-01T10:00:00+08:00",
        "actual_checked_at": "2026-08-01T10:00:00+08:00",
        "next_review_at": "2026-08-30"
    })
    raw_1 = dumps_json(payload1)
    p1 = ImportService.parse_and_preview(db_session, raw_1)
    ImportService.commit_import(db_session, p1["import_pkg"], raw_1)

    # Next scan: full scan with REVIEW_NOT_DUE
    payload2 = make_sample_import(db_session, "SCAN-20260818-006", mode="FULL_SCAN", rev=1)
    payload2["coverage_events"].append({
        "vendor": "Google",
        "product": "Gemini",
        "surface": "Web Pricing",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-18T18:00:00+08:00",
        "actual_checked_at": "2026-08-18T18:00:00+08:00",  # Scan tried to send today's date
        "basis_coverage_id": "COV-000001"
    })
    raw_2 = dumps_json(payload2)
    p2 = ImportService.parse_and_preview(db_session, raw_2)
    assert p2["is_valid"] is True
    ImportService.commit_import(db_session, p2["import_pkg"], raw_2)

    cov_latest = db_session.query(CoverageHistoryModel).filter_by(coverage_id="COV-000002").first()
    assert cov_latest is not None
    # Must preserve basis coverage's historical check time
    assert cov_latest.actual_checked_at == "2026-08-01T10:00:00+08:00"

# TEST-007: DEEP_FULL_SCAN 中禁止使用 REVIEW_NOT_DUE
def test_007_deep_scan_prohibits_review_not_due(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-007", mode="DEEP_FULL_SCAN", rev=0)
    payload["coverage_events"].append({
        "vendor": "Google",
        "product": "Gemini",
        "surface": "Web Pricing",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-18T18:00:00+08:00",
        "actual_checked_at": "2026-08-18T18:00:00+08:00",
        "basis_coverage_id": "COV-000001"
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("DEEP_FULL_SCAN" in err for err in preview["errors"])

# TEST-008: CONFIRM_NO_CHANGE 正确更新 last_checked
def test_008_confirm_no_change_validation(db_session):
    # Create benefit first
    b = BenefitModel(
        benefit_id="BEN-000001",
        vendor="Anthropic",
        product="Claude",
        campaign_name="Claude Pro Free Trial",
        benefit_type="FREE_ACCESS",
        benefit_detail="Pro trial",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://anthropic.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    db_session.add(b)
    db_session.commit()

    payload = make_sample_import(db_session, "SCAN-20260818-008", rev=0)
    payload["benefit_changes"].append({
        "operation": "CONFIRM_NO_CHANGE",
        "benefit_id": "BEN-000001",
        "last_checked": "2026-08-18",
        "next_review_date": "2026-09-01"
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True

    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)
    b_updated = db_session.query(BenefitModel).filter_by(benefit_id="BEN-000001").first()
    assert b_updated.last_checked == "2026-08-18"
    assert b_updated.next_review_date == "2026-09-01"
    assert b_updated.change_type == "NO_CHANGE"

# TEST-009: Evidence Gate 拦截无 S/A 证据的 CONFIRMED
def test_009_evidence_gate_warning(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-009", rev=0)
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-001",
        "record": {
            "benefit_id": None,
            "vendor": "Mistral",
            "product": "Le Chat",
            "campaign_name": "Free Credits",
            "benefit_type": "GENERAL_CREDITS",
            "benefit_detail": "赠送额度",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://reddit.com/r/ai",
            "source_level": "C",  # Level C, but marked CONFIRMED!
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        },
        "evidence": [
            {
                "url": "https://reddit.com/r/ai",
                "source_level": "C",
                "source_role": "PRIMARY",
                "checked_at": "2026-08-18T17:20:00+08:00",
                "supports_fields": ["status"]
            }
        ]
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert len(preview["preview"]["evidence_warnings"]) == 1

# TEST-010: Lead RESOLVE_TO_BENEFIT (指向同批次新福利)
def test_010_lead_resolve_to_new_benefit(db_session):
    # Setup existing open lead
    lead = LeadModel(
        lead_id="LEAD-000001",
        vendor="Anthropic",
        product="Claude Code",
        lead_summary="疑似新用户赠送 20 美金 API Credits",
        verification_status="LIKELY",
        source_level="B",
        first_seen="2026-08-10",
        last_checked="2026-08-10",
        status="OPEN"
    )
    db_session.add(lead)
    db_session.commit()

    payload = make_sample_import(db_session, "SCAN-20260818-010", rev=0)
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-001",
        "record": {
            "benefit_id": None,
            "vendor": "Anthropic",
            "product": "Claude Code",
            "campaign_name": "Claude Code Early Access Credits",
            "benefit_type": "API_CREDITS",
            "benefit_detail": "新用户赠送 20 美金",
            "wallet": "API Credits",
            "amount": "20",
            "unit": "USD",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://anthropic.com/claude-code",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        }
    })
    payload["lead_changes"].append({
        "operation": "RESOLVE_TO_BENEFIT",
        "lead_id": "LEAD-000001",
        "target_benefit_ref": "BNEW-001"
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True

    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)

    # Lead should be RESOLVED with resolved_benefit_id set to new permanent ID
    l_updated = db_session.query(LeadModel).filter_by(lead_id="LEAD-000001").first()
    assert l_updated.status == "RESOLVED"
    assert l_updated.resolved_benefit_id == "BEN-000001"

# TEST-011: Lead RESOLVE_TO_BENEFIT (指向历史已有福利)
def test_011_lead_resolve_to_existing_benefit(db_session):
    b = BenefitModel(
        benefit_id="BEN-000050",
        vendor="MiniMax",
        product="Hailuo",
        campaign_name="Free Video Tokens",
        benefit_type="TOKENS",
        benefit_detail="免费视频点数",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://minimaxi.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    lead = LeadModel(
        lead_id="LEAD-000002",
        vendor="MiniMax",
        product="Hailuo",
        lead_summary="海螺视频点数线索",
        verification_status="LIKELY",
        source_level="B",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        status="OPEN"
    )
    db_session.add(b)
    db_session.add(lead)
    db_session.commit()

    payload = make_sample_import(db_session, "SCAN-20260818-011", rev=0)
    payload["lead_changes"].append({
        "operation": "RESOLVE_TO_BENEFIT",
        "lead_id": "LEAD-000002",
        "target_benefit_id": "BEN-000050"
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True

    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)
    l_updated = db_session.query(LeadModel).filter_by(lead_id="LEAD-000002").first()
    assert l_updated.status == "RESOLVED"
    assert l_updated.resolved_benefit_id == "BEN-000050"

# TEST-012: Source DEPRECATE 保留历史记录
def test_012_source_deprecate_retains_record(db_session):
    src = CanonicalSourceModel(
        source_id="SRC-000001",
        vendor="OpenAI",
        product="ChatGPT",
        surface="Pricing",
        source_name="Old Pricing Page",
        url="https://openai.com/old-pricing",
        source_type="PRICING",
        source_level="S",
        status="ACTIVE"
    )
    db_session.add(src)
    db_session.commit()

    payload = make_sample_import(db_session, "SCAN-20260818-012", rev=0)
    payload["source_updates"].append({
        "operation": "DEPRECATE",
        "source_id": "SRC-000001"
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True

    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)
    src_updated = db_session.query(CanonicalSourceModel).filter_by(source_id="SRC-000001").first()
    assert src_updated is not None
    assert src_updated.status == "DEPRECATED"

# TEST-013: User Benefit State 绝对不受 Scan Import 影响
def test_013_user_benefit_state_protected(db_session):
    # Setup benefit & user state
    b = BenefitModel(
        benefit_id="BEN-000001",
        vendor="TRAE",
        product="TRAE CN",
        campaign_name="Checkin",
        benefit_type="CHECKIN",
        benefit_detail="签到",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://trae.cn",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    db_session.add(b)
    db_session.flush()

    u_state = UserBenefitStateModel(
        benefit_id="BEN-000001",
        action_state="CLAIMED",
        notes="用户已经领取"
    )
    db_session.add(u_state)
    db_session.commit()

    # Scan reports benefit status is now ENDED
    payload = make_sample_import(db_session, "SCAN-20260818-013", rev=0)
    payload["benefit_changes"].append({
        "operation": "UPDATE",
        "benefit_id": "BEN-000001",
        "change_type": "ENDED",
        "patch": {
            "status": "ENDED",
            "end_date": "2026-08-18"
        }
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True

    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)

    # Benefit status is ENDED, but user state must REMAIN CLAIMED
    b_updated = db_session.query(BenefitModel).filter_by(benefit_id="BEN-000001").first()
    assert b_updated.status == "ENDED"

    u_check = db_session.query(UserBenefitStateModel).filter_by(benefit_id="BEN-000001").first()
    assert u_check.action_state == "CLAIMED"
    assert u_check.notes == "用户已经领取"

# TEST-014: CREATE 疑似重复检测 (Candidate Duplicates)
def test_014_create_candidate_duplicate_detection(db_session):
    b = BenefitModel(
        benefit_id="BEN-000001",
        vendor="TRAE",
        product="TRAE CN",
        campaign_name="TRAE Daily Checkin",
        benefit_type="CHECKIN",
        benefit_detail="签到得通用积分",
        wallet="通用积分",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://trae.cn/activity",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    db_session.add(b)
    db_session.commit()

    # Import proposes CREATE for identical vendor + product + campaign
    payload = make_sample_import(db_session, "SCAN-20260818-014", rev=0)
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-DUP",
        "record": {
            "benefit_id": None,
            "vendor": "TRAE",
            "product": "TRAE CN",
            "campaign_name": "TRAE Daily Checkin",
            "benefit_type": "CHECKIN",
            "benefit_detail": "每日签到",
            "wallet": "通用积分",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://trae.cn/activity",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        }
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True
    assert preview["preview"]["duplicate_candidate_count"] == 1
    assert preview["preview"]["duplicates"][0]["existing_benefit_id"] == "BEN-000001"

# TEST-015: 事务原子性 (出异常全量 Rollback)
def test_015_atomic_transaction_rollback(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-015", rev=0)
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-001",
        "record": {
            "benefit_id": None,
            "vendor": "ByteDance",
            "product": "Coze",
            "campaign_name": "Coze Free Quota",
            "benefit_type": "FREE_QUOTA",
            "benefit_detail": "每日免费",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://coze.cn",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        }
    })
    # Add a broken operation that will raise ValueError during commit
    payload["lead_changes"].append({
        "operation": "RESOLVE_TO_BENEFIT",
        "lead_id": "LEAD-NONEXISTENT",
        "target_benefit_ref": "BNEW-001"
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    
    with pytest.raises(Exception):
        ImportService.commit_import(db_session, preview["import_pkg"], raw_json)

    # Benefit should NOT be in DB
    b = db_session.query(BenefitModel).filter_by(vendor="ByteDance").first()
    assert b is None
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    assert sys_state.baseline_revision == 0

# TEST-016: 首次 BUILD_INITIAL_BASELINE 自动将 NEW 转为 UNKNOWN
def test_016_initial_baseline_change_type(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-016", rev=0, baseline_action="BUILD_INITIAL_BASELINE")
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-001",
        "record": {
            "benefit_id": None,
            "vendor": "Zhipu",
            "product": "GLM",
            "campaign_name": "GLM Free API",
            "benefit_type": "API_CREDITS",
            "benefit_detail": "免费额度",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://zhipuai.cn",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE",
            "change_type": "NEW"  # Claimed NEW during initial baseline
        }
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)

    b = db_session.query(BenefitModel).filter_by(vendor="Zhipu").first()
    assert b.change_type == "UNKNOWN"

# TEST-017: 中文枚举映射完整性
def test_017_chinese_status_labels():
    assert VERIFICATION_STATUS_LABELS["CONFIRMED"] == "已确认"
    assert STATUS_LABELS["ACTIVE"] == "有效"
    assert COVERAGE_STATE_LABELS["REVIEW_NOT_DUE"] == "复查未到期"
    assert USER_ACTION_STATE_LABELS["CLAIMED"] == "已领取"

# TEST-018: 未导出的未知 scan_id → FAIL
def test_018_unknown_scan_id_rejected(db_session):
    payload = {
        "protocol_version": "0.1",
        "benefit_schema_version": "1.2.1",
        "package_type": "SCAN_IMPORT",
        "scan_result": {
            "scan_id": "SCAN-UNKNOWN-999",
            "scan_mode": "FULL_SCAN",
            "context_baseline_revision": 0,
            "generated_at": "2026-08-18T18:00:00+08:00",
            "scan_statuses": ["PUBLIC_COMPLETE"],
            "baseline_action": "BUILD_INITIAL_BASELINE"
        },
        "benefit_changes": [],
        "lead_changes": [],
        "coverage_events": [],
        "source_updates": [],
        "manual_check_items": [],
        "warnings": []
    }
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("该 scan_id 不对应 Benefit Desk 已导出的扫描上下文" in e for e in preview["errors"])

# TEST-019: EMPTY Baseline 要求 BUILD_INITIAL_BASELINE
def test_019_empty_baseline_requires_build_initial_baseline(db_session):
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    assert sys_state.baseline_state == "EMPTY"

    payload = make_sample_import(db_session, "SCAN-20260818-019", rev=0, baseline_action="UPDATE_EXISTING_BASELINE")
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("当前系统基线为空" in e for e in preview["errors"])

# TEST-020: READY Baseline 拒绝 BUILD_INITIAL_BASELINE
def test_020_ready_baseline_rejects_build_initial_baseline(db_session):
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    payload = make_sample_import(db_session, "SCAN-20260818-020", rev=1, baseline_action="BUILD_INITIAL_BASELINE")
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("当前系统基线已就绪" in e for e in preview["errors"])


# TEST-021: 非法 package_type 被严格拒绝
def test_021_invalid_package_type_rejected(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-021", rev=0)
    payload["package_type"] = "INVALID_PACKAGE_TYPE"
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("package_type" in e or "数据结构不符合" in e for e in preview["errors"])

# TEST-022: 非法 Protocol 枚举值 Schema 级别阻断
def test_022_invalid_protocol_enums_rejected(db_session):
    # Invalid coverage state
    with pytest.raises(ValidationError):
        CoverageEventItem(
            vendor="Test",
            product="Test",
            surface="Test",
            region="GLOBAL",
            coverage_state="BANANA",  # Invalid enum
            scan_observed_at="2026-08-18T18:00:00+08:00",
            actual_checked_at="2026-08-18T18:00:00+08:00"
        )

    # Invalid manual check priority
    with pytest.raises(ValidationError):
        ManualCheckItem(
            vendor="Test",
            product="Test",
            channel="WEB",
            reason="Test reason",
            priority="SUPER_HIGH",  # Invalid enum
            suggested_action="Test action",
            status="OPEN"
        )

# TEST-023: Protocol 事件时间强制要求带时区 ISO8601
def test_023_protocol_timestamp_requires_timezone():
    # Plain date rejected
    with pytest.raises(ValidationError):
        EvidenceItem(
            url="https://test.com",
            source_level="S",
            source_role="PRIMARY",
            checked_at="2026-08-18",  # Plain date without time and timezone
            supports_fields=["status"]
        )

    # Naive timestamp without timezone offset rejected
    with pytest.raises(ValidationError):
        EvidenceItem(
            url="https://test.com",
            source_level="S",
            source_role="PRIMARY",
            checked_at="2026-08-18T18:00:00",  # No timezone offset
            supports_fields=["status"]
        )

    # Valid timezone-aware timestamp accepted
    ev = EvidenceItem(
        url="https://test.com",
        source_level="S",
        source_role="PRIMARY",
        checked_at="2026-08-18T18:00:00+08:00",
        supports_fields=["status"]
    )
    assert ev.checked_at == "2026-08-18T18:00:00+08:00"

# TEST-024: 存在 NOT_CHECKED 必然要求包含 SCAN_INCOMPLETE 且禁止 PUBLIC_COMPLETE
def test_024_not_checked_requires_scan_incomplete(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-024", rev=0)
    payload["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"]
    payload["coverage_events"].append({
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "Pricing",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-18T18:00:00+08:00"
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("存在关键待检查 (NOT_CHECKED) 项时，扫描状态不能声明为公开扫描完成" in e for e in preview["errors"])

    # When marked with SCAN_INCOMPLETE and without PUBLIC_COMPLETE -> should pass gate
    payload2 = make_sample_import(db_session, "SCAN-20260818-024B", rev=0)
    payload2["scan_result"]["scan_statuses"] = ["SCAN_INCOMPLETE", "OVERALL_PARTIAL"]
    payload2["coverage_events"].append({
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "Pricing",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-18T18:00:00+08:00"
    })
    preview2 = ImportService.parse_and_preview(db_session, dumps_json(payload2))
    assert preview2["is_valid"] is True

# TEST-025: Scan Context 导出包含完整 benefit_index 身份字段
def test_025_benefit_index_identity_fields(db_session):
    b = BenefitModel(
        benefit_id="BEN-000100",
        vendor="DeepSeek",
        product="Coder",
        campaign_name="Free API Quota",
        benefit_type="API_CREDITS",
        benefit_detail="免费点数",
        linked_vendor="Volcengine",
        linked_product="Ark",
        wallet="API Credits",
        regions=["CN", "GLOBAL"],
        start_date="2026-01-01",
        end_date="2026-12-31",
        first_seen="2026-01-01",
        last_checked="2026-08-01",
        next_review_date="2026-09-01",
        official_source="https://deepseek.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    db_session.add(b)
    db_session.commit()

    context = ExportService.generate_scan_context(db_session)
    assert len(context.benefit_index) == 1
    idx = context.benefit_index[0]
    assert idx.benefit_id == "BEN-000100"
    assert idx.vendor == "DeepSeek"
    assert idx.product == "Coder"
    assert idx.campaign_name == "Free API Quota"
    assert idx.benefit_type == "API_CREDITS"
    assert idx.linked_vendor == "Volcengine"
    assert idx.linked_product == "Ark"
    assert idx.regions == ["CN", "GLOBAL"]
    assert idx.status == "ACTIVE"
    assert idx.start_date == "2026-01-01"
    assert idx.end_date == "2026-12-31"
    assert idx.last_checked == "2026-08-01"
    assert idx.next_review_date == "2026-09-01"

# TEST-026: Vendor Deep Dive 正确裁剪 User Benefit State
def test_026_vendor_deep_dive_user_state_pruning(db_session):
    b1 = BenefitModel(
        benefit_id="BEN-000101",
        vendor="OpenAI",
        product="ChatGPT",
        campaign_name="Plus",
        benefit_type="FREE_ACCESS",
        benefit_detail="Detail",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://openai.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    b2 = BenefitModel(
        benefit_id="BEN-000102",
        vendor="Anthropic",
        product="Claude",
        campaign_name="Pro",
        benefit_type="FREE_ACCESS",
        benefit_detail="Detail",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://anthropic.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    db_session.add_all([b1, b2])
    db_session.flush()

    u1 = UserBenefitStateModel(benefit_id="BEN-000101", action_state="CLAIMED")
    u2 = UserBenefitStateModel(benefit_id="BEN-000102", action_state="INTERESTED")
    db_session.add_all([u1, u2])
    db_session.commit()

    # Vendor Deep Dive on OpenAI only
    context = ExportService.generate_scan_context(db_session, requested_mode="VENDOR_DEEP_DIVE", vendor_filter="OpenAI")
    assert len(context.benefit_index) == 1
    assert context.benefit_index[0].vendor == "OpenAI"
    assert len(context.user_benefit_states) == 1
    assert context.user_benefit_states[0].benefit_id == "BEN-000101"

# TEST-027: 同一 Import 内 local_ref 全局唯一性校验 (跨类型)
def test_027_local_ref_global_uniqueness(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-027", rev=0)
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "REF-DUPLICATE",
        "record": {
            "benefit_id": None,
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "campaign_name": "Plus",
            "benefit_type": "FREE_ACCESS",
            "benefit_detail": "Detail",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://openai.com",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        }
    })
    payload["manual_check_items"].append({
        "local_ref": "REF-DUPLICATE",  # Duplicate local_ref across Benefit and ManualCheck
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "channel": "IDE",
        "reason": "Check something",
        "priority": "LOW",
        "suggested_action": "Check IDE",
        "status": "OPEN"
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("必须全局唯一" in e for e in preview["errors"])

# TEST-028: Manual Check 引用不存在的 Benefit/Lead 校验阻断
def test_028_invalid_manual_check_reference(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-028", rev=0)
    payload["manual_check_items"].append({
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "channel": "IDE",
        "reason": "Check benefit",
        "priority": "LOW",
        "suggested_action": "Check",
        "status": "OPEN",
        "related_benefit_id": "BEN-999999"  # Non-existent
    })
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("related_benefit_id 不存在" in e for e in preview["errors"])

# TEST-029: BenefitRecord 包含多余字段 (extra=forbid) 阻断
def test_029_benefit_record_extra_fields_rejected():
    with pytest.raises(ValidationError):
        BenefitRecord(
            vendor="OpenAI",
            product="ChatGPT",
            campaign_name="Plus",
            benefit_type="FREE_ACCESS",
            benefit_detail="Detail",
            first_seen="2026-08-18",
            last_checked="2026-08-18",
            official_source="https://openai.com",
            source_level="S",
            verification_status="CONFIRMED",
            status="ACTIVE",
            coverage_state="CHECKED_FOUND"  # Forbidden extra field!
        )

# TEST-030: scan_id 与 baseline_revision_at_export 强绑定校验
def test_030_scan_id_revision_binding(db_session):
    # Pre-register scan exported at revision 10
    scan_rec = ScanModel(
        scan_id="SCAN-20260818-030",
        requested_mode="FULL_SCAN",
        baseline_revision_at_export=10,
        import_status="EXPORTED"
    )
    db_session.add(scan_rec)
    db_session.commit()

    # Import package claims context_baseline_revision = 9
    payload = {
        "protocol_version": "0.1",
        "benefit_schema_version": "1.2.1",
        "package_type": "SCAN_IMPORT",
        "scan_result": {
            "scan_id": "SCAN-20260818-030",
            "scan_mode": "FULL_SCAN",
            "context_baseline_revision": 9,  # Mismatch with export revision 10!
            "generated_at": "2026-08-18T18:00:00+08:00",
            "scan_statuses": ["PUBLIC_COMPLETE"],
            "baseline_action": "UPDATE_EXISTING_BASELINE"
        },
        "benefit_changes": [],
        "lead_changes": [],
        "coverage_events": [],
        "source_updates": [],
        "manual_check_items": [],
        "warnings": []
    }
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("导出时的基线版本" in e for e in preview["errors"])

# TEST-031: 初始基线全生命周期测试 (EMPTY -> Export -> Import -> READY -> rev+1 -> 幂等阻断)
def test_031_initial_baseline_lifecycle(db_session):
    # 1. Start from clean EMPTY state
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    assert sys_state.baseline_state == "EMPTY"
    assert sys_state.baseline_revision == 0

    # 2. Desk generates Scan Context
    context_pkg = ExportService.generate_scan_context(db_session, requested_mode="DEEP_FULL_SCAN")
    assert context_pkg.scan.baseline_state == "EMPTY"
    assert context_pkg.scan.baseline_revision == 0
    scan_id = context_pkg.scan.scan_id

    # 3. ChatGPT returns Scan Import
    import_payload = {
        "protocol_version": "0.1",
        "benefit_schema_version": "1.2.1",
        "package_type": "SCAN_IMPORT",
        "scan_result": {
            "scan_id": scan_id,
            "scan_mode": "DEEP_FULL_SCAN",
            "context_baseline_revision": 0,
            "generated_at": "2026-08-18T18:25:00+08:00",
            "scan_statuses": ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"],
            "baseline_action": "BUILD_INITIAL_BASELINE",
            "summary_notes": "初始全量基线扫描"
        },
        "benefit_changes": [
            {
                "operation": "CREATE",
                "local_ref": "BNEW-001",
                "record": {
                    "benefit_id": None,
                    "vendor": "OpenAI",
                    "product": "ChatGPT",
                    "campaign_name": "Free Tier",
                    "benefit_type": "FREE_ACCESS",
                    "benefit_detail": "免费使用",
                    "first_seen": "2026-08-18",
                    "last_checked": "2026-08-18",
                    "official_source": "https://openai.com",
                    "source_level": "S",
                    "verification_status": "CONFIRMED",
                    "status": "ACTIVE",
                    "change_type": "NEW"
                }
            }
        ],
        "lead_changes": [],
        "coverage_events": [
            {
                "vendor": "OpenAI",
                "product": "ChatGPT",
                "surface": "Web Pricing",
                "region": "GLOBAL",
                "coverage_state": "CHECKED_FOUND",
                "scan_observed_at": "2026-08-18T18:20:00+08:00",
                "actual_checked_at": "2026-08-18T18:20:00+08:00"
            }
        ],
        "source_updates": [],
        "manual_check_items": [],
        "warnings": []
    }
    raw_import_json = dumps_json(import_payload)

    # 4. Preview and commit
    preview = ImportService.parse_and_preview(db_session, raw_import_json)
    assert preview["is_valid"] is True
    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw_import_json)
    assert commit_res["success"] is True

    # 5. System State is now READY and rev is 1
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    assert sys_state.baseline_state == "READY"
    assert sys_state.baseline_revision == 1

    # 6. Re-import of same scan_id blocked
    preview_dup = ImportService.parse_and_preview(db_session, raw_import_json)
    assert preview_dup["is_valid"] is False
    assert any("该扫描已经导入" in e for e in preview_dup["errors"])

# TEST-032: REVIEW_NOT_DUE requires concrete next_review_at
def test_032_review_not_due_requires_concrete_next_review_at(db_session):
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    basis_cov = CoverageHistoryModel(
        coverage_id="COV-000032",
        scan_id="SCAN-HISTORICAL",
        vendor="OpenAI",
        product="ChatGPT",
        wallet="UNKNOWN",
        surface="Pricing",
        region="GLOBAL",
        coverage_state="CHECKED_NONE",
        scan_observed_at="2026-08-10T10:00:00+08:00",
        actual_checked_at="2026-08-10T10:00:00+08:00",
        next_review_at="UNKNOWN"
    )
    db_session.add(basis_cov)
    db_session.commit()

    # Case A: next_review_at = null in basis
    basis_cov.next_review_at = None
    db_session.commit()

    payload_a = make_sample_import(db_session, "SCAN-20260818-032A", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    payload_a["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "Pricing",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "basis_coverage_id": "COV-000032",
        "scan_observed_at": "2026-08-18T18:00:00+08:00",
        "actual_checked_at": "2026-08-10T10:00:00+08:00"
    }]
    preview_a = ImportService.parse_and_preview(db_session, dumps_json(payload_a))
    assert preview_a["is_valid"] is False
    assert any("缺少明确的 next_review_at" in e for e in preview_a["errors"])

    # Case B: next_review_at = "UNKNOWN" in basis
    basis_cov.next_review_at = "UNKNOWN"
    db_session.commit()

    payload_b = make_sample_import(db_session, "SCAN-20260818-032B", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    payload_b["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "Pricing",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "basis_coverage_id": "COV-000032",
        "scan_observed_at": "2026-08-18T18:00:00+08:00",
        "actual_checked_at": "2026-08-10T10:00:00+08:00"
    }]
    preview_b = ImportService.parse_and_preview(db_session, dumps_json(payload_b))
    assert preview_b["is_valid"] is False
    assert any("缺少明确的 next_review_at" in e for e in preview_b["errors"])

    # Case C: next_review_at = future concrete date -> PASS
    basis_cov.next_review_at = "2099-01-01"
    db_session.commit()

    payload_c = make_sample_import(db_session, "SCAN-20260818-032C", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    payload_c["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "Pricing",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "basis_coverage_id": "COV-000032",
        "scan_observed_at": "2026-08-18T18:00:00+08:00",
        "actual_checked_at": "2026-08-10T10:00:00+08:00"
    }]
    preview_c = ImportService.parse_and_preview(db_session, dumps_json(payload_c))
    assert preview_c["is_valid"] is True
    commit_c = ImportService.commit_import(db_session, preview_c["import_pkg"], dumps_json(payload_c))
    assert commit_c["success"] is True

    # Case D: next_review_at = past date -> FAIL
    basis_cov.next_review_at = "2020-01-01"
    db_session.commit()

    payload_d = make_sample_import(db_session, "SCAN-20260818-032D", rev=2, baseline_action="UPDATE_EXISTING_BASELINE")
    payload_d["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "Pricing",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "basis_coverage_id": "COV-000032",
        "scan_observed_at": "2026-08-18T18:00:00+08:00",
        "actual_checked_at": "2026-08-10T10:00:00+08:00"
    }]
    preview_d = ImportService.parse_and_preview(db_session, dumps_json(payload_d))
    assert preview_d["is_valid"] is False
    assert any("已达到或超过下次复查时间" in e for e in preview_d["errors"])

# TEST-033: NOT_CHECKED and BLIND_SPOT commit persists null actual_checked_at
def test_033_not_checked_commit_persists_null_actual_checked_at(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-033", rev=0)
    payload["scan_result"]["scan_statuses"] = ["SCAN_INCOMPLETE", "OVERALL_PARTIAL"]
    payload["coverage_events"] = [
        {
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "Pricing",
            "region": "GLOBAL",
            "coverage_state": "NOT_CHECKED",
            "scan_observed_at": "2026-08-18T18:00:00+08:00",
            "actual_checked_at": None
        },
        {
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "Hidden Features",
            "region": "GLOBAL",
            "coverage_state": "BLIND_SPOT",
            "scan_observed_at": "2026-08-18T18:00:00+08:00",
            "actual_checked_at": None
        }
    ]
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True
    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw_json)
    assert commit_res["success"] is True

    # Verify DB rows
    not_checked_cov = db_session.query(CoverageHistoryModel).filter_by(surface="Pricing").first()
    assert not_checked_cov is not None
    assert not_checked_cov.actual_checked_at is None
    assert not_checked_cov.scan_observed_at == "2026-08-18T18:00:00+08:00"

    blind_spot_cov = db_session.query(CoverageHistoryModel).filter_by(surface="Hidden Features").first()
    assert blind_spot_cov is not None
    assert blind_spot_cov.actual_checked_at is None

    # Verify CHECKED_NONE with actual_checked_at=None fails
    payload_invalid = make_sample_import(db_session, "SCAN-20260818-033-INV", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    payload_invalid["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "Pricing",
        "region": "GLOBAL",
        "coverage_state": "CHECKED_NONE",
        "scan_observed_at": "2026-08-18T18:00:00+08:00",
        "actual_checked_at": None
    }]
    preview_inv = ImportService.parse_and_preview(db_session, dumps_json(payload_invalid))
    assert preview_inv["is_valid"] is False
    assert any("必须提供实际检查时间戳" in e for e in preview_inv["errors"])

# TEST-034: Source ADD remains exportable with timezone-aware fallback timestamp
def test_034_source_add_remains_exportable(db_session):
    payload = make_sample_import(db_session, "SCAN-20260818-034", rev=0)
    payload["source_updates"] = [
        {
            "operation": "ADD",
            "local_ref": "SNEW-001",
            "record": {
                "source_id": None,
                "vendor": "OpenAI",
                "product": "ChatGPT",
                "surface": "Docs",
                "source_name": "OpenAI Developer Platform",
                "url": "https://platform.openai.com/docs",
                "source_type": "OFFICIAL_DOCS",
                "source_level": "S",
                "status": "ACTIVE",
                "last_verified_at": None  # Trigger fallback
            }
        }
    ]
    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True
    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw_json)
    assert commit_res["success"] is True

    # Verify DB CanonicalSourceModel timestamp is timezone-aware
    src = db_session.query(CanonicalSourceModel).filter_by(source_name="OpenAI Developer Platform").first()
    assert src is not None
    assert src.last_verified_at is not None
    assert is_valid_timezone_iso8601(src.last_verified_at)
    assert src.last_verified_at != today_str()

    # Re-export Scan Context and verify Pydantic serialization
    context_pkg = ExportService.generate_scan_context(db_session, requested_mode="FULL_SCAN")
    assert len(context_pkg.canonical_sources) >= 1
    exported_src = next(s for s in context_pkg.canonical_sources if s.source_name == "OpenAI Developer Platform")
    assert exported_src.last_verified_at == src.last_verified_at
    assert is_valid_timezone_iso8601(exported_src.last_verified_at)

# TEST-035: Manual Check cannot supply permanent ID
def test_035_manual_check_cannot_supply_permanent_id(db_session):
    # Case A: manual_check_id set, local_ref null -> FAIL
    payload_a = make_sample_import(db_session, "SCAN-20260818-035A", rev=0)
    payload_a["manual_check_items"] = [{
        "manual_check_id": "MCHK-999999",
        "local_ref": None,
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "channel": "IDE",
        "reason": "Test check",
        "priority": "LOW",
        "suggested_action": "Check IDE",
        "status": "OPEN"
    }]
    preview_a = ImportService.parse_and_preview(db_session, dumps_json(payload_a))
    assert preview_a["is_valid"] is False
    assert any("新人工检查项必须使用 local_ref" in e for e in preview_a["errors"])

    # Case B: manual_check_id set, local_ref set -> FAIL
    payload_b = make_sample_import(db_session, "SCAN-20260818-035B", rev=0)
    payload_b["manual_check_items"] = [{
        "manual_check_id": "MCHK-999999",
        "local_ref": "MNEW-001",
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "channel": "IDE",
        "reason": "Test check",
        "priority": "LOW",
        "suggested_action": "Check IDE",
        "status": "OPEN"
    }]
    preview_b = ImportService.parse_and_preview(db_session, dumps_json(payload_b))
    assert preview_b["is_valid"] is False
    assert any("新人工检查项必须使用 local_ref" in e for e in preview_b["errors"])

    # Case C: manual_check_id null, local_ref set -> PASS and commits permanent ID
    payload_c = make_sample_import(db_session, "SCAN-20260818-035C", rev=0)
    payload_c["manual_check_items"] = [{
        "manual_check_id": None,
        "local_ref": "MNEW-001",
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "channel": "IDE",
        "reason": "Test check",
        "priority": "LOW",
        "suggested_action": "Check IDE",
        "status": "OPEN"
    }]
    raw_c = dumps_json(payload_c)
    preview_c = ImportService.parse_and_preview(db_session, raw_c)
    assert preview_c["is_valid"] is True
    commit_c = ImportService.commit_import(db_session, preview_c["import_pkg"], raw_c)
    assert commit_c["success"] is True

    m_rec = db_session.query(ManualCheckModel).filter_by(vendor="OpenAI").first()
    assert m_rec is not None
    assert m_rec.manual_check_id.startswith("MCHK-")
    assert m_rec.manual_check_id != "MCHK-999999"

# TEST-036: Benefit UPDATE merged schema validation
def test_036_benefit_update_merged_schema_validation(db_session):
    # Setup initial benefit
    b = BenefitModel(
        benefit_id="BEN-000123",
        vendor="Anthropic",
        product="Claude",
        campaign_name="Claude Pro Promo",
        benefit_type="FREE_ACCESS",
        benefit_detail="Pro trial",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://anthropic.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    b.regions = ["US", "GLOBAL"]
    b.eligibility_class = ["NEW_USERS"]
    db_session.add(b)
    db_session.commit()

    # Case A: status = "BANANA" -> FAIL
    p_a = make_sample_import(db_session, "SCAN-20260818-036A", rev=0)
    p_a["benefit_changes"].append({
        "operation": "UPDATE",
        "benefit_id": "BEN-000123",
        "change_type": "STATUS_CHANGED",
        "patch": {"status": "BANANA"}
    })
    prev_a = ImportService.parse_and_preview(db_session, dumps_json(p_a))
    assert prev_a["is_valid"] is False
    assert any("Schema 规范" in e or "Invalid status" in e for e in prev_a["errors"])

    # Case B: end_date = "tomorrow" -> FAIL
    p_b = make_sample_import(db_session, "SCAN-20260818-036B", rev=0)
    p_b["benefit_changes"].append({
        "operation": "UPDATE",
        "benefit_id": "BEN-000123",
        "change_type": "STATUS_CHANGED",
        "patch": {"end_date": "tomorrow"}
    })
    prev_b = ImportService.parse_and_preview(db_session, dumps_json(p_b))
    assert prev_b["is_valid"] is False
    assert any("Invalid date format" in e for e in prev_b["errors"])

    # Case C: regions = ["MARS"] -> FAIL
    p_c = make_sample_import(db_session, "SCAN-20260818-036C", rev=0)
    p_c["benefit_changes"].append({
        "operation": "UPDATE",
        "benefit_id": "BEN-000123",
        "change_type": "STATUS_CHANGED",
        "patch": {"regions": ["MARS"]}
    })
    prev_c = ImportService.parse_and_preview(db_session, dumps_json(p_c))
    assert prev_c["is_valid"] is False
    assert any("Invalid region" in e for e in prev_c["errors"])

    # Case D: coverage_state = "CHECKED_FOUND" in patch -> FAIL
    p_d = make_sample_import(db_session, "SCAN-20260818-036D", rev=0)
    p_d["benefit_changes"].append({
        "operation": "UPDATE",
        "benefit_id": "BEN-000123",
        "change_type": "STATUS_CHANGED",
        "patch": {"coverage_state": "CHECKED_FOUND"}
    })
    prev_d = ImportService.parse_and_preview(db_session, dumps_json(p_d))
    assert prev_d["is_valid"] is False
    assert any("非法外来字段" in e or "extra fields not permitted" in e for e in prev_d["errors"])

    # Case E: Valid patch status = ENDED, end_date = 2026-08-31 -> PASS
    p_e = make_sample_import(db_session, "SCAN-20260818-036E", rev=0)
    p_e["benefit_changes"].append({
        "operation": "UPDATE",
        "benefit_id": "BEN-000123",
        "change_type": "ENDED",
        "patch": {"status": "ENDED", "end_date": "2026-08-31"}
    })
    raw_e = dumps_json(p_e)
    prev_e = ImportService.parse_and_preview(db_session, raw_e)
    assert prev_e["is_valid"] is True
    commit_e = ImportService.commit_import(db_session, prev_e["import_pkg"], raw_e)
    assert commit_e["success"] is True

    # Verify updated fields and unmodified fields in DB
    updated_b = db_session.query(BenefitModel).filter_by(benefit_id="BEN-000123").first()
    assert updated_b.status == "ENDED"
    assert updated_b.end_date == "2026-08-31"
    assert updated_b.campaign_name == "Claude Pro Promo"
    assert updated_b.vendor == "Anthropic"
    assert updated_b.regions == ["US", "GLOBAL"]

# TEST-037: Lead UPDATE validation
def test_037_lead_update_validation(db_session):
    lead = LeadModel(
        lead_id="LEAD-000123",
        vendor="Mistral",
        product="Le Chat",
        lead_summary="Mistral Free trial",
        verification_status="UNVERIFIED",
        source_level="B",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        status="OPEN"
    )
    lead.regions = ["GLOBAL"]
    db_session.add(lead)
    db_session.commit()

    # Case A: verification_status = "CONFIRMED" -> FAIL
    p_a = make_sample_import(db_session, "SCAN-20260818-037A", rev=0)
    p_a["lead_changes"].append({
        "operation": "UPDATE",
        "lead_id": "LEAD-000123",
        "patch": {"verification_status": "CONFIRMED"}
    })
    prev_a = ImportService.parse_and_preview(db_session, dumps_json(p_a))
    assert prev_a["is_valid"] is False
    assert any("RESOLVE_TO_BENEFIT" in e for e in prev_a["errors"])

    # Case B: invalid region in patch -> FAIL
    p_b = make_sample_import(db_session, "SCAN-20260818-037B", rev=0)
    p_b["lead_changes"].append({
        "operation": "UPDATE",
        "lead_id": "LEAD-000123",
        "patch": {"regions": ["MARS"]}
    })
    prev_b = ImportService.parse_and_preview(db_session, dumps_json(p_b))
    assert prev_b["is_valid"] is False
    assert any("Invalid region" in e for e in prev_b["errors"])

    # Case C: unknown field -> FAIL
    p_c = make_sample_import(db_session, "SCAN-20260818-037C", rev=0)
    p_c["lead_changes"].append({
        "operation": "UPDATE",
        "lead_id": "LEAD-000123",
        "patch": {"extra_invalid_field": "123"}
    })
    prev_c = ImportService.parse_and_preview(db_session, dumps_json(p_c))
    assert prev_c["is_valid"] is False

    # Case D: attempt to patch lead_id -> FAIL
    p_d = make_sample_import(db_session, "SCAN-20260818-037D", rev=0)
    p_d["lead_changes"].append({
        "operation": "UPDATE",
        "lead_id": "LEAD-000123",
        "patch": {"lead_id": "LEAD-999999"}
    })
    prev_d = ImportService.parse_and_preview(db_session, dumps_json(p_d))
    assert prev_d["is_valid"] is False
    assert any("禁止修改 lead_id" in e for e in prev_d["errors"])

    # Case E: Valid LIKELY -> DISPUTED update -> PASS
    p_e = make_sample_import(db_session, "SCAN-20260818-037E", rev=0)
    p_e["lead_changes"].append({
        "operation": "UPDATE",
        "lead_id": "LEAD-000123",
        "patch": {"verification_status": "DISPUTED", "lead_summary": "Disputed deal"}
    })
    raw_e = dumps_json(p_e)
    prev_e = ImportService.parse_and_preview(db_session, raw_e)
    assert prev_e["is_valid"] is True
    commit_e = ImportService.commit_import(db_session, prev_e["import_pkg"], raw_e)
    assert commit_e["success"] is True
    updated_lead = db_session.query(LeadModel).filter_by(lead_id="LEAD-000123").first()
    assert updated_lead.verification_status == "DISPUTED"
    assert updated_lead.lead_summary == "Disputed deal"

# TEST-038: Source UPDATE validation
def test_038_source_update_validation(db_session):
    src = CanonicalSourceModel(
        source_id="SRC-000123",
        vendor="Anthropic",
        product="Claude",
        surface="PRICING",
        source_name="Anthropic Pricing Page",
        url="https://anthropic.com/pricing",
        source_type="OFFICIAL_PAGE",
        source_level="S",
        status="ACTIVE",
        last_verified_at="2026-08-01T10:00:00+08:00"
    )
    db_session.add(src)
    db_session.commit()

    # Case A: source_level = "Z" -> FAIL
    p_a = make_sample_import(db_session, "SCAN-20260818-038A", rev=0)
    p_a["source_updates"].append({
        "operation": "UPDATE",
        "source_id": "SRC-000123",
        "patch": {"source_level": "Z"}
    })
    prev_a = ImportService.parse_and_preview(db_session, dumps_json(p_a))
    assert prev_a["is_valid"] is False
    assert any("Invalid source_level" in e for e in prev_a["errors"])

    # Case B: non-timezone last_verified_at -> FAIL
    p_b = make_sample_import(db_session, "SCAN-20260818-038B", rev=0)
    p_b["source_updates"].append({
        "operation": "UPDATE",
        "source_id": "SRC-000123",
        "patch": {"last_verified_at": "2026-08-18"}
    })
    prev_b = ImportService.parse_and_preview(db_session, dumps_json(p_b))
    assert prev_b["is_valid"] is False
    assert any("timezone-aware" in e for e in prev_b["errors"])

    # Case C: unknown field -> FAIL
    p_c = make_sample_import(db_session, "SCAN-20260818-038C", rev=0)
    p_c["source_updates"].append({
        "operation": "UPDATE",
        "source_id": "SRC-000123",
        "patch": {"unknown_prop": "test"}
    })
    prev_c = ImportService.parse_and_preview(db_session, dumps_json(p_c))
    assert prev_c["is_valid"] is False

    # Case D: source_id patch -> FAIL
    p_d = make_sample_import(db_session, "SCAN-20260818-038D", rev=0)
    p_d["source_updates"].append({
        "operation": "UPDATE",
        "source_id": "SRC-000123",
        "patch": {"source_id": "SRC-999999"}
    })
    prev_d = ImportService.parse_and_preview(db_session, dumps_json(p_d))
    assert prev_d["is_valid"] is False
    assert any("禁止修改 source_id" in e for e in prev_d["errors"])

    # Case E: Valid timezone-aware update -> PASS
    p_e = make_sample_import(db_session, "SCAN-20260818-038E", rev=0)
    p_e["source_updates"].append({
        "operation": "UPDATE",
        "source_id": "SRC-000123",
        "patch": {"last_verified_at": "2026-08-18T19:30:00+08:00"}
    })
    raw_e = dumps_json(p_e)
    prev_e = ImportService.parse_and_preview(db_session, raw_e)
    assert prev_e["is_valid"] is True
    commit_e = ImportService.commit_import(db_session, prev_e["import_pkg"], raw_e)
    assert commit_e["success"] is True
    updated_src = db_session.query(CanonicalSourceModel).filter_by(source_id="SRC-000123").first()
    assert updated_src.last_verified_at == "2026-08-18T19:30:00+08:00"

# TEST-039: Lead cannot remain CONFIRMED
def test_039_lead_cannot_remain_confirmed(db_session):
    # Case A: Lead CREATE with CONFIRMED -> FAIL
    p_a = make_sample_import(db_session, "SCAN-20260818-039A", rev=0)
    p_a["lead_changes"].append({
        "operation": "CREATE",
        "local_ref": "LNEW-001",
        "record": {
            "vendor": "Meta",
            "product": "Llama",
            "lead_summary": "Meta Free Credits",
            "verification_status": "CONFIRMED",
            "source_level": "S",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "status": "OPEN"
        }
    })
    prev_a = ImportService.parse_and_preview(db_session, dumps_json(p_a))
    assert prev_a["is_valid"] is False
    assert any("RESOLVE_TO_BENEFIT" in e for e in prev_a["errors"])

    # Case B: Lead UPDATE with CONFIRMED -> FAIL
    lead = LeadModel(
        lead_id="LEAD-00039",
        vendor="Meta",
        product="Llama",
        lead_summary="Meta Free Credits",
        verification_status="UNVERIFIED",
        source_level="B",
        first_seen="2026-08-18",
        last_checked="2026-08-18",
        status="OPEN"
    )
    lead.regions = ["GLOBAL"]
    db_session.add(lead)
    db_session.commit()

    p_b = make_sample_import(db_session, "SCAN-20260818-039B", rev=0)
    p_b["lead_changes"].append({
        "operation": "UPDATE",
        "lead_id": "LEAD-00039",
        "patch": {"verification_status": "CONFIRMED"}
    })
    prev_b = ImportService.parse_and_preview(db_session, dumps_json(p_b))
    assert prev_b["is_valid"] is False
    assert any("RESOLVE_TO_BENEFIT" in e for e in prev_b["errors"])

    # Case C: UNVERIFIED Lead + Benefit CREATE + RESOLVE_TO_BENEFIT -> PASS
    p_c = make_sample_import(db_session, "SCAN-20260818-039C", rev=0)
    p_c["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-039",
        "record": {
            "vendor": "Meta",
            "product": "Llama",
            "campaign_name": "Llama API Credits",
            "benefit_type": "API_CREDITS",
            "benefit_detail": "$50 Credits",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://meta.com/llama",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        }
    })
    p_c["lead_changes"].append({
        "operation": "RESOLVE_TO_BENEFIT",
        "lead_id": "LEAD-00039",
        "target_benefit_ref": "BNEW-039"
    })
    raw_c = dumps_json(p_c)
    prev_c = ImportService.parse_and_preview(db_session, raw_c)
    assert prev_c["is_valid"] is True
    commit_c = ImportService.commit_import(db_session, prev_c["import_pkg"], raw_c)
    assert commit_c["success"] is True

    resolved_lead = db_session.query(LeadModel).filter_by(lead_id="LEAD-00039").first()
    assert resolved_lead.status == "RESOLVED"
    assert resolved_lead.resolved_benefit_id.startswith("BEN-")

# TEST-040: Permanent ID ownership
def test_040_permanent_id_ownership(db_session):
    # Case A: Lead CREATE with permanent lead_id -> FAIL
    p_a = make_sample_import(db_session, "SCAN-20260818-040A", rev=0)
    p_a["lead_changes"].append({
        "operation": "CREATE",
        "local_ref": "LNEW-001",
        "record": {
            "lead_id": "LEAD-999999",
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "lead_summary": "Test Lead",
            "verification_status": "LIKELY",
            "source_level": "A",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "status": "OPEN"
        }
    })
    prev_a = ImportService.parse_and_preview(db_session, dumps_json(p_a))
    assert prev_a["is_valid"] is False
    assert any("lead_id 由 Benefit Desk 分配" in e for e in prev_a["errors"])

    # Case B: Source ADD with permanent source_id -> FAIL
    p_b = make_sample_import(db_session, "SCAN-20260818-040B", rev=0)
    p_b["source_updates"].append({
        "operation": "ADD",
        "local_ref": "SNEW-001",
        "record": {
            "source_id": "SRC-999999",
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PRICING",
            "source_name": "OpenAI Pricing",
            "url": "https://openai.com/pricing",
            "source_type": "OFFICIAL_PAGE",
            "source_level": "S",
            "status": "ACTIVE"
        }
    })
    prev_b = ImportService.parse_and_preview(db_session, dumps_json(p_b))
    assert prev_b["is_valid"] is False
    assert any("source_id 由 Benefit Desk 分配" in e for e in prev_b["errors"])

    # Case C: Coverage Event with coverage_id -> FAIL
    p_c = make_sample_import(db_session, "SCAN-20260818-040C", rev=0)
    p_c["coverage_events"].append({
        "coverage_id": "COV-999999",
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "PRICING",
        "region": "GLOBAL",
        "coverage_state": "CHECKED_NONE",
        "scan_observed_at": "2026-08-18T18:00:00+08:00",
        "actual_checked_at": "2026-08-18T18:00:00+08:00"
    })
    prev_c = ImportService.parse_and_preview(db_session, dumps_json(p_c))
    assert prev_c["is_valid"] is False
    assert any("Coverage Event 不能由外部指定 coverage_id" in e for e in prev_c["errors"])



    # Case D: Coverage Event with mismatched scan_id -> FAIL
    p_d = make_sample_import(db_session, "SCAN-20260818-040D", rev=0)
    p_d["coverage_events"].append({
        "scan_id": "SCAN-OTHER-123",
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "PRICING",
        "region": "GLOBAL",
        "coverage_state": "CHECKED_NONE",
        "scan_observed_at": "2026-08-18T18:00:00+08:00",
        "actual_checked_at": "2026-08-18T18:00:00+08:00"
    })
    prev_d = ImportService.parse_and_preview(db_session, dumps_json(p_d))
    assert prev_d["is_valid"] is False
    assert any("与扫描批次 scan_id" in e for e in prev_d["errors"])

    # Case E: Valid local_ref Lead CREATE and Source ADD -> Desk generates permanent IDs
    p_e = make_sample_import(db_session, "SCAN-20260818-040E", rev=0)
    p_e["lead_changes"].append({
        "operation": "CREATE",
        "local_ref": "LNEW-040",
        "record": {
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "lead_summary": "Test Valid Lead",
            "verification_status": "LIKELY",
            "source_level": "A",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "status": "OPEN"
        }
    })
    p_e["source_updates"].append({
        "operation": "ADD",
        "local_ref": "SNEW-040",
        "record": {
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PRICING",
            "source_name": "OpenAI Pricing Valid",
            "url": "https://openai.com/pricing",
            "source_type": "OFFICIAL_PAGE",
            "source_level": "S",
            "status": "ACTIVE"
        }
    })
    raw_e = dumps_json(p_e)
    prev_e = ImportService.parse_and_preview(db_session, raw_e)
    assert prev_e["is_valid"] is True
    commit_e = ImportService.commit_import(db_session, prev_e["import_pkg"], raw_e)
    assert commit_e["success"] is True
    created_lead = db_session.query(LeadModel).filter_by(lead_summary="Test Valid Lead").first()
    assert created_lead.lead_id.startswith("LEAD-")
    created_src = db_session.query(CanonicalSourceModel).filter_by(source_name="OpenAI Pricing Valid").first()
    assert created_src.source_id.startswith("SRC-")

# TEST-041: UNKNOWN date review planning
def test_041_unknown_date_review_planning(db_session):
    # Benefit A: ACTIVE + UNKNOWN end_date + UNKNOWN next_review_date
    ba = BenefitModel(
        benefit_id="BEN-041A",
        vendor="VendorA",
        product="ProductA",
        campaign_name="Campaign A (Active Unknown)",
        benefit_type="FREE_MODEL",
        benefit_detail="detail",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://example.com/a",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE",
        end_date="UNKNOWN",
        next_review_date="UNKNOWN"
    )
    ba.regions = ["GLOBAL"]
    ba.eligibility_class = ["ALL_USERS"]

    # Benefit B: ACTIVE + future next_review_date + future end_date
    bb = BenefitModel(
        benefit_id="BEN-041B",
        vendor="VendorB",
        product="ProductB",
        campaign_name="Campaign B (Active Future)",
        benefit_type="FREE_MODEL",
        benefit_detail="detail",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://example.com/b",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE",
        end_date="2099-01-01",
        next_review_date="2099-01-01"
    )
    bb.regions = ["GLOBAL"]
    bb.eligibility_class = ["ALL_USERS"]

    # Benefit C: ENDED in past
    bc = BenefitModel(
        benefit_id="BEN-041C",
        vendor="VendorC",
        product="ProductC",
        campaign_name="Campaign C (Ended)",
        benefit_type="FREE_MODEL",
        benefit_detail="detail",
        first_seen="2020-01-01",
        last_checked="2020-01-01",
        official_source="https://example.com/c",
        source_level="S",
        verification_status="CONFIRMED",
        status="ENDED",
        end_date="2020-01-01",
        next_review_date="UNKNOWN"
    )
    bc.regions = ["GLOBAL"]
    bc.eligibility_class = ["ALL_USERS"]

    db_session.add_all([ba, bb, bc])
    db_session.commit()

    context_pkg = ExportService.generate_scan_context(db_session, requested_mode="FULL_SCAN")
    review_ids = {r.benefit_id for r in context_pkg.review_items}

    # Benefit A must be in review_items
    assert "BEN-041A" in review_ids
    # Benefit B and C must not be in review_items
    assert "BEN-041B" not in review_ids
    assert "BEN-041C" not in review_ids

# TEST-042: Old SQLite schema migration
def test_042_old_sqlite_schema_migration():
    from sqlalchemy import create_engine, text
    from ai_benefit_desk.db.init_db import init_db
    
    # Create temporary SQLite in-memory database with raw old schema (actual_checked_at NOT NULL)
    test_engine = create_engine("sqlite:///:memory:")
    with test_engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE coverage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coverage_id VARCHAR(32) NOT NULL UNIQUE,
                scan_id VARCHAR(64) NOT NULL,
                vendor VARCHAR(128) NOT NULL,
                product VARCHAR(128) NOT NULL,
                wallet VARCHAR(128) DEFAULT 'UNKNOWN',
                surface VARCHAR(64) NOT NULL,
                region VARCHAR(32) NOT NULL,
                coverage_state VARCHAR(32) NOT NULL,
                scan_observed_at VARCHAR(64) NOT NULL,
                actual_checked_at VARCHAR(64) NOT NULL,
                next_review_at VARCHAR(32) DEFAULT 'UNKNOWN',
                source_id VARCHAR(32),
                basis_coverage_id VARCHAR(32),
                notes TEXT DEFAULT '',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            INSERT INTO coverage_history (
                coverage_id, scan_id, vendor, product, surface, region, coverage_state,
                scan_observed_at, actual_checked_at, next_review_at
            ) VALUES (
                'COV-OLD-001', 'SCAN-OLD-001', 'OpenAI', 'ChatGPT', 'PRICING', 'GLOBAL',
                'CHECKED_FOUND', '2026-08-01T10:00:00+08:00', '2026-08-01T10:00:00+08:00', '2026-09-01'
            )
        """))
        conn.commit()

    # Run init_db / migration on test_engine
    init_db(bind=test_engine)

    with test_engine.connect() as conn:
        # Check historical data preserved
        row = conn.execute(text("SELECT coverage_id, actual_checked_at FROM coverage_history WHERE coverage_id='COV-OLD-001'")).fetchone()
        assert row is not None
        assert row[0] == "COV-OLD-001"
        assert row[1] == "2026-08-01T10:00:00+08:00"

        # Check table schema allows NULL
        cols = conn.execute(text("PRAGMA table_info(coverage_history)")).fetchall()
        for col in cols:
            if col[1] == "actual_checked_at":
                assert col[3] == 0  # notnull is 0 (nullable)

        # Test inserting record with NULL actual_checked_at
        conn.execute(text("""
            INSERT INTO coverage_history (
                coverage_id, scan_id, vendor, product, surface, region, coverage_state,
                scan_observed_at, actual_checked_at
            ) VALUES (
                'COV-NEW-002', 'SCAN-NEW-002', 'Anthropic', 'Claude', 'PORTAL', 'GLOBAL',
                'NOT_CHECKED', '2026-08-18T18:00:00+08:00', NULL
            )
        """))
        conn.commit()
        
        count = conn.execute(text("SELECT count(*) FROM coverage_history")).scalar()
        assert count == 2

    # Re-run init_db to test idempotency
    init_db(bind=test_engine)
    with test_engine.connect() as conn:
        count = conn.execute(text("SELECT count(*) FROM coverage_history")).scalar()
        assert count == 2

# TEST-043: amount semantics
def test_043_amount_semantics():
    # Case A: integer amount 1000 -> stored as "1000"
    r_a = BenefitRecord(
        vendor="OpenAI",
        campaign_name="Test Amount Int",
        benefit_type="API_CREDITS",
        benefit_detail="1000 credits",
        amount=1000,
        first_seen="2026-08-18",
        last_checked="2026-08-18",
        official_source="https://openai.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    assert r_a.amount == "1000"

    # Case B: float amount 12.5 -> stored as "12.5"
    r_b = BenefitRecord(
        vendor="OpenAI",
        campaign_name="Test Amount Float",
        benefit_type="API_CREDITS",
        benefit_detail="12.5 USD",
        amount=12.5,
        first_seen="2026-08-18",
        last_checked="2026-08-18",
        official_source="https://openai.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    assert r_b.amount == "12.5"

    # Case C: amount = "UNKNOWN"
    r_c = BenefitRecord(
        vendor="OpenAI",
        campaign_name="Test Amount UNKNOWN",
        benefit_type="FREE_MODEL",
        benefit_detail="detail",
        amount="UNKNOWN",
        first_seen="2026-08-18",
        last_checked="2026-08-18",
        official_source="https://openai.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    assert r_c.amount == "UNKNOWN"

    # Case D: amount = "many credits" -> FAIL
    with pytest.raises(Exception):
        BenefitRecord(
            vendor="OpenAI",
            campaign_name="Test Amount Text",
            benefit_type="API_CREDITS",
            benefit_detail="detail",
            amount="many credits",
            first_seen="2026-08-18",
            last_checked="2026-08-18",
            official_source="https://openai.com",
            source_level="S",
            verification_status="CONFIRMED",
            status="ACTIVE"
        )

    # Case E: amount = "unlimited" -> FAIL
    with pytest.raises(Exception):
        BenefitRecord(
            vendor="OpenAI",
            campaign_name="Test Amount Unlimited",
            benefit_type="API_CREDITS",
            benefit_detail="detail",
            amount="unlimited",
            first_seen="2026-08-18",
            last_checked="2026-08-18",
            official_source="https://openai.com",
            source_level="S",
            verification_status="CONFIRMED",
            status="ACTIVE"
        )


