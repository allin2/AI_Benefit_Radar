import pytest
import json
from datetime import date
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CoverageHistoryModel, CanonicalSourceModel,
    UserBenefitStateModel, ScanModel, ImportAuditModel, SystemStateModel
)
from ai_benefit_desk.services.export_service import ExportService
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.services.validation_service import ValidationService
from ai_benefit_desk.services.dedup_service import DedupService
from ai_benefit_desk.utils.enum_labels import (
    VERIFICATION_STATUS_LABELS, STATUS_LABELS, COVERAGE_STATE_LABELS, USER_ACTION_STATE_LABELS
)
from ai_benefit_desk.utils.json_utils import dumps_json

# Helper to create sample import payload
def make_sample_import(scan_id="SCAN-20260818-001", mode="FULL_SCAN", rev=0, baseline_action="UPDATE_EXISTING_BASELINE"):
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
    payload = make_sample_import("SCAN-20260818-001", rev=0)
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
    payload = make_sample_import("SCAN-20260818-002", rev=0)
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
    payload = make_sample_import("SCAN-20260818-003", rev=0)
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
    payload = make_sample_import("SCAN-20260818-004", rev=5)
    raw_json = dumps_json(payload)

    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("扫描上下文已经过期" in err for err in preview["errors"])

# TEST-006: REVIEW_NOT_DUE 不得刷新 actual_checked_at
def test_006_review_not_due_preserves_actual_checked_at(db_session):
    # Setup initial baseline with historical checked_at
    payload1 = make_sample_import("SCAN-20260818-005", rev=0, baseline_action="BUILD_INITIAL_BASELINE")
    payload1["coverage_events"].append({
        "vendor": "Google",
        "product": "Gemini",
        "surface": "Web Pricing",
        "region": "GLOBAL",
        "coverage_state": "CHECKED_FOUND",
        "scan_observed_at": "2026-08-01",
        "actual_checked_at": "2026-08-01",
        "next_review_at": "2026-08-30"
    })
    raw_1 = dumps_json(payload1)
    p1 = ImportService.parse_and_preview(db_session, raw_1)
    ImportService.commit_import(db_session, p1["import_pkg"], raw_1)

    # Next scan: full scan with REVIEW_NOT_DUE
    payload2 = make_sample_import("SCAN-20260818-006", mode="FULL_SCAN", rev=1)
    payload2["coverage_events"].append({
        "vendor": "Google",
        "product": "Gemini",
        "surface": "Web Pricing",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-18",
        "actual_checked_at": "2026-08-18",  # Scan tried to send today's date
        "basis_coverage_id": "COV-000001"
    })
    raw_2 = dumps_json(payload2)
    p2 = ImportService.parse_and_preview(db_session, raw_2)
    assert p2["is_valid"] is True
    ImportService.commit_import(db_session, p2["import_pkg"], raw_2)

    cov_latest = db_session.query(CoverageHistoryModel).filter_by(coverage_id="COV-000002").first()
    assert cov_latest is not None
    # Must preserve basis coverage's historical check time
    assert cov_latest.actual_checked_at == "2026-08-01"

# TEST-007: DEEP_FULL_SCAN 中禁止使用 REVIEW_NOT_DUE
def test_007_deep_scan_prohibits_review_not_due(db_session):
    payload = make_sample_import("SCAN-20260818-007", mode="DEEP_FULL_SCAN", rev=0)
    payload["coverage_events"].append({
        "vendor": "Google",
        "product": "Gemini",
        "surface": "Web Pricing",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-18",
        "actual_checked_at": "2026-08-18",
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

    payload = make_sample_import("SCAN-20260818-008", rev=0)
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
    payload = make_sample_import("SCAN-20260818-009", rev=0)
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
        }
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

    payload = make_sample_import("SCAN-20260818-010", rev=0)
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

    payload = make_sample_import("SCAN-20260818-011", rev=0)
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

    payload = make_sample_import("SCAN-20260818-012", rev=0)
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
    payload = make_sample_import("SCAN-20260818-013", rev=0)
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
    payload = make_sample_import("SCAN-20260818-014", rev=0)
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
    payload = make_sample_import("SCAN-20260818-015", rev=0)
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
    payload = make_sample_import("SCAN-20260818-016", rev=0, baseline_action="BUILD_INITIAL_BASELINE")
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
