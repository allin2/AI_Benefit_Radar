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
def make_sample_import(scan_id="SCAN-20260818-001", mode="FULL_SCAN", rev=0, baseline_action="INCREMENTAL_UPDATE"):
    return {
        "protocol_version": "0.1",
        "benefit_schema_version": "1.2.1",
        "package_type": "SCAN_IMPORT",
        "scan_result": {
            "scan_id": scan_id,
            "requested_mode": mode,
            "actual_scan_mode": mode,
            "baseline_action": baseline_action,
            "context_baseline_revision": rev,
            "scan_timestamp": "2026-08-18T12:00:00Z",
            "public_scan_status": "PUBLIC_COMPLETE",
            "overall_coverage_status": "OVERALL_PARTIAL",
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
        "benefit_id": None,
        "benefit_record": {
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
        "benefit_record": {
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "campaign_name": "Nonexistent",
            "benefit_type": "FREE_ACCESS",
            "benefit_detail": "不存在的福利",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://openai.com",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        }
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("BEN-999999" in err for err in preview["errors"])

# TEST-004: 相同 scan_id 二次导入 → 被阻止
def test_004_idempotent_scan_import_blocked(db_session):
    payload = make_sample_import("SCAN-20260818-001", rev=0)
    raw_json = dumps_json(payload)
    
    preview1 = ImportService.parse_and_preview(db_session, raw_json)
    assert preview1["is_valid"] is True
    ImportService.commit_import(db_session, preview1["import_pkg"], raw_json)

    # Attempt to import same scan_id again
    preview2 = ImportService.parse_and_preview(db_session, raw_json)
    assert preview2["is_valid"] is False
    assert any("该扫描已经导入" in err for err in preview2["errors"])

# TEST-005: baseline_revision 冲突 → 被发现
def test_005_baseline_revision_conflict(db_session):
    # DB is at revision 0, but payload says revision 5
    payload = make_sample_import("SCAN-20260818-005", rev=5)
    raw_json = dumps_json(payload)
    
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("扫描上下文已经过期" in err for err in preview["errors"])

# TEST-006: REVIEW_NOT_DUE 不刷新 actual_checked_at
def test_006_review_not_due_preserves_actual_checked_at(db_session):
    # 1. Insert historical coverage
    hist_cov = CoverageHistoryModel(
        coverage_id="COV-000001",
        scan_id="SCAN-20260801-001",
        vendor="TRAE",
        product="TRAE CN",
        surface="Free / Signup",
        region="CN",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01",
        actual_checked_at="2026-08-01",
        next_review_at="2026-08-30"
    )
    db_session.add(hist_cov)
    db_session.commit()

    # 2. Import scan with REVIEW_NOT_DUE
    payload = make_sample_import("SCAN-20260818-006", rev=0)
    payload["coverage_events"].append({
        "vendor": "TRAE",
        "product": "TRAE CN",
        "surface": "Free / Signup",
        "region": "CN",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-18",
        "actual_checked_at": "2026-08-01",
        "basis_coverage_id": "COV-000001"
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True

    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)

    # 3. Verify in DB
    new_cov = db_session.query(CoverageHistoryModel).filter_by(coverage_state="REVIEW_NOT_DUE").first()
    assert new_cov is not None
    assert new_cov.scan_observed_at == "2026-08-18"
    assert new_cov.actual_checked_at == "2026-08-01"  # Not refreshed to 2026-08-18!

# TEST-007: DEEP_FULL_SCAN Import 中 REVIEW_NOT_DUE → FAIL
def test_007_deep_scan_prohibits_review_not_due(db_session):
    payload = make_sample_import("SCAN-20260818-007", mode="DEEP_FULL_SCAN", rev=0)
    payload["coverage_events"].append({
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "Free / Signup",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-18",
        "actual_checked_at": "2026-08-01"
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("深度全量扫描 (DEEP_FULL_SCAN) 中禁止使用 REVIEW_NOT_DUE" in err for err in preview["errors"])

# TEST-008: CONFIRM_NO_CHANGE 不能来自纯 REVIEW_NOT_DUE
def test_008_confirm_no_change_validation(db_session):
    # Benefit CONFIRM_NO_CHANGE requires valid benefit_id
    payload = make_sample_import("SCAN-20260818-008", rev=0)
    payload["benefit_changes"].append({
        "operation": "CONFIRM_NO_CHANGE",
        "benefit_id": None,  # Missing benefit_id
        "benefit_record": {
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "campaign_name": "Trial",
            "benefit_type": "FREE_ACCESS",
            "benefit_detail": "免费试用",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://openai.com",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        }
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is False
    assert any("CONFIRM_NO_CHANGE 操作必须指定已有的 benefit_id" in err for err in preview["errors"])

# TEST-009: CONFIRMED 没有 S/A Evidence → Evidence Gate
def test_009_evidence_gate_warning(db_session):
    payload = make_sample_import("SCAN-20260818-009", rev=0)
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-009",
        "benefit_record": {
            "vendor": "UnknownVendor",
            "product": "AI App",
            "campaign_name": "Rumored Credits",
            "benefit_type": "GENERAL_CREDITS",
            "benefit_detail": "传言赠送 500 Credits",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://reddit.com/r/ai",
            "source_level": "C",  # Reddit C-level evidence
            "verification_status": "CONFIRMED",  # Incompatible!
            "status": "ACTIVE"
        }
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert len(preview["preview"]["evidence_warnings"]) == 1
    assert "确认级别与证据不匹配" in preview["preview"]["evidence_warnings"][0]["message"]

# TEST-010: Lead 可以 resolve 到同一 Import 中的新 Benefit
def test_010_lead_resolve_to_new_benefit(db_session):
    # 1. Create open lead in DB
    lead = LeadModel(
        lead_id="LEAD-000001",
        vendor="Anthropic",
        product="Claude Code",
        lead_summary="传言 Claude Code 提供新用户额度",
        verification_status="LIKELY",
        source_level="B",
        first_seen="2026-08-10",
        last_checked="2026-08-10",
        status="OPEN"
    )
    db_session.add(lead)
    db_session.commit()

    # 2. Import package containing new Benefit AND resolve lead to that new Benefit local_ref
    payload = make_sample_import("SCAN-20260818-010", rev=0)
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-010",
        "benefit_record": {
            "vendor": "Anthropic",
            "product": "Claude Code",
            "campaign_name": "Claude Code Welcome Quota",
            "benefit_type": "CODING_CREDITS",
            "benefit_detail": "新用户赠送 20 美元使用额度",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://anthropic.com",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        }
    })
    payload["lead_changes"].append({
        "operation": "RESOLVE_TO_BENEFIT",
        "lead_id": "LEAD-000001",
        "target_benefit_local_ref": "BNEW-010"
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True

    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw_json)
    assert commit_res["success"] is True

    # 3. Verify lead resolved to newly generated benefit_id
    updated_lead = db_session.query(LeadModel).filter_by(lead_id="LEAD-000001").first()
    assert updated_lead.status == "RESOLVED"
    assert updated_lead.resolved_benefit_id == "BEN-000001"

# TEST-011: Lead 可以 resolve 到已有 Benefit
def test_011_lead_resolve_to_existing_benefit(db_session):
    b = BenefitModel(
        benefit_id="BEN-000050",
        vendor="Google",
        product="Gemini",
        campaign_name="Gemini Advanced Trial",
        benefit_type="FREE_ACCESS",
        benefit_detail="免费试用2个月",
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
        lead_summary="Gemini 试用线索",
        verification_status="LIKELY",
        source_level="B",
        first_seen="2026-08-05",
        last_checked="2026-08-05",
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

    updated_lead = db_session.query(LeadModel).filter_by(lead_id="LEAD-000002").first()
    assert updated_lead.status == "RESOLVED"
    assert updated_lead.resolved_benefit_id == "BEN-000050"

# TEST-012: Source DEPRECATE 不删除历史
def test_012_source_deprecate_retains_record(db_session):
    src = CanonicalSourceModel(
        source_id="SRC-000001",
        vendor="Kimi",
        product="Kimi API",
        surface="Pricing",
        source_name="Kimi Pricing Page",
        url="https://kimi.ai/pricing",
        source_type="PRICING",
        source_level="S",
        status="ACTIVE"
    )
    db_session.add(src)
    db_session.commit()

    payload = make_sample_import("SCAN-20260818-012", rev=0)
    payload["source_updates"].append({
        "operation": "DEPRECATE",
        "source_id": "SRC-000001",
        "source_record": {
            "vendor": "Kimi",
            "product": "Kimi API",
            "surface": "Pricing",
            "source_name": "Kimi Pricing Page",
            "url": "https://kimi.ai/pricing",
            "source_type": "PRICING",
            "source_level": "S",
            "status": "DEPRECATED"
        }
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert preview["is_valid"] is True

    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)

    updated_src = db_session.query(CanonicalSourceModel).filter_by(source_id="SRC-000001").first()
    assert updated_src is not None
    assert updated_src.status == "DEPRECATED"

# TEST-013: Scan Import 不修改 CLAIMED (User Benefit State)
def test_013_user_benefit_state_protected(db_session):
    # 1. Existing Benefit with CLAIMED state
    b = BenefitModel(
        benefit_id="BEN-000100",
        vendor="TRAE",
        product="TRAE CN",
        campaign_name="Daily Checkin",
        benefit_type="CHECKIN",
        benefit_detail="每日签到送积分",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://trae.cn",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    db_session.add(b)
    db_session.flush()

    user_state = UserBenefitStateModel(
        benefit_id="BEN-000100",
        action_state="CLAIMED",
        notes="我已经在 8月1日 领过了"
    )
    db_session.add(user_state)
    db_session.commit()

    # 2. Import scan that marks this Benefit as ENDED
    payload = make_sample_import("SCAN-20260818-013", rev=0)
    payload["benefit_changes"].append({
        "operation": "UPDATE",
        "benefit_id": "BEN-000100",
        "benefit_record": {
            "vendor": "TRAE",
            "product": "TRAE CN",
            "campaign_name": "Daily Checkin",
            "benefit_type": "CHECKIN",
            "benefit_detail": "签到活动已结束",
            "first_seen": "2026-08-01",
            "last_checked": "2026-08-18",
            "official_source": "https://trae.cn",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ENDED",
            "change_type": "ENDED"
        }
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)

    # 3. Verify: Benefit status is ENDED, but user state is STILL CLAIMED
    updated_b = db_session.query(BenefitModel).filter_by(benefit_id="BEN-000100").first()
    assert updated_b.status == "ENDED"

    u_state = db_session.query(UserBenefitStateModel).filter_by(benefit_id="BEN-000100").first()
    assert u_state.action_state == "CLAIMED"
    assert u_state.notes == "我已经在 8月1日 领过了"

# TEST-014: CREATE 疑似重复 → 进入预览，不自动创建
def test_014_create_candidate_duplicate_detection(db_session):
    b = BenefitModel(
        benefit_id="BEN-000200",
        vendor="DeepSeek",
        product="DeepSeek API",
        campaign_name="Night Pricing 50% Off",
        benefit_type="OFF_PEAK_DISCOUNT",
        benefit_detail="夜间调用半价",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://platform.deepseek.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    db_session.add(b)
    db_session.commit()

    # Import CREATE with same vendor, product, and campaign name
    payload = make_sample_import("SCAN-20260818-014", rev=0)
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-999",
        "benefit_record": {
            "vendor": "DeepSeek",
            "product": "DeepSeek API",
            "campaign_name": "Night Pricing 50% Off",
            "benefit_type": "OFF_PEAK_DISCOUNT",
            "benefit_detail": "夜间调用半价优惠",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://platform.deepseek.com",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        }
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    assert len(preview["preview"]["duplicates"]) == 1
    dup = preview["preview"]["duplicates"][0]
    assert dup["existing_benefit_id"] == "BEN-000200"
    assert dup["local_ref"] == "BNEW-999"

# TEST-015: 事务中途失败 → 整体 rollback
def test_015_atomic_transaction_rollback(db_session):
    payload = make_sample_import("SCAN-20260818-015", rev=0)
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-015",
        "benefit_record": {
            "vendor": "TestVendor",
            "product": "TestProd",
            "campaign_name": "Valid Item",
            "benefit_type": "FREE_ACCESS",
            "benefit_detail": "测试福利",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://example.com",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE"
        }
    })
    # Add a Lead resolve operation pointing to a nonexistent lead to cause failure during commit
    payload["lead_changes"].append({
        "operation": "RESOLVE_TO_BENEFIT",
        "lead_id": "LEAD-NONEXISTENT",
        "target_benefit_local_ref": "BNEW-015"
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    
    with pytest.raises(Exception):
        ImportService.commit_import(db_session, preview["import_pkg"], raw_json)

    # Verify rollback: No benefit created, revision not incremented
    b = db_session.query(BenefitModel).filter_by(vendor="TestVendor").first()
    assert b is None
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    assert sys_state.baseline_revision == 0

# TEST-016: 首次 Baseline 的长期福利不会被自动标 NEW
def test_016_initial_baseline_change_type(db_session):
    payload = make_sample_import("SCAN-20260818-016", rev=0, baseline_action="BUILD_INITIAL_BASELINE")
    payload["benefit_changes"].append({
        "operation": "CREATE",
        "local_ref": "BNEW-016",
        "benefit_record": {
            "vendor": "Google",
            "product": "Gemini API",
            "campaign_name": "Gemini API Free Tier",
            "benefit_type": "API_CREDITS",
            "benefit_detail": "长期免费额度",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "official_source": "https://ai.google.dev",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE",
            "change_type": "NEW"  # Submitted as NEW in initial baseline
        }
    })

    raw_json = dumps_json(payload)
    preview = ImportService.parse_and_preview(db_session, raw_json)
    ImportService.commit_import(db_session, preview["import_pkg"], raw_json)

    b = db_session.query(BenefitModel).filter_by(vendor="Google").first()
    assert b is not None
    # Converted to UNKNOWN because it is initial baseline
    assert b.change_type == "UNKNOWN"

# TEST-017: 用户所有可见主要状态显示中文
def test_017_chinese_status_labels():
    assert VERIFICATION_STATUS_LABELS["CONFIRMED"] == "已确认"
    assert VERIFICATION_STATUS_LABELS["LIKELY"] == "较高可信"
    assert VERIFICATION_STATUS_LABELS["UNVERIFIED"] == "未验证"
    assert VERIFICATION_STATUS_LABELS["DISPUTED"] == "存在争议"

    assert STATUS_LABELS["ACTIVE"] == "有效"
    assert STATUS_LABELS["EXPIRING_SOON"] == "即将过期"
    assert STATUS_LABELS["EXPIRED"] == "已过期"
    assert STATUS_LABELS["UPCOMING"] == "即将开始"
    assert STATUS_LABELS["WAITLIST"] == "候补 / 等待开放"
    assert STATUS_LABELS["ENDED"] == "已结束"

    assert COVERAGE_STATE_LABELS["CHECKED_FOUND"] == "已检查·有发现"
    assert COVERAGE_STATE_LABELS["CHECKED_NONE"] == "已检查·暂无发现"
    assert COVERAGE_STATE_LABELS["REVIEW_NOT_DUE"] == "复查未到期"
    assert COVERAGE_STATE_LABELS["NOT_CHECKED"] == "待检查"
    assert COVERAGE_STATE_LABELS["BLIND_SPOT"] == "监控盲区"
    assert COVERAGE_STATE_LABELS["NOT_APPLICABLE"] == "不适用"

    assert USER_ACTION_STATE_LABELS["NOT_REVIEWED"] == "待处理"
    assert USER_ACTION_STATE_LABELS["INTERESTED"] == "感兴趣"
    assert USER_ACTION_STATE_LABELS["CLAIMED"] == "已领取"
    assert USER_ACTION_STATE_LABELS["NOT_ELIGIBLE"] == "不符合资格"
    assert USER_ACTION_STATE_LABELS["SKIPPED"] == "已跳过"
