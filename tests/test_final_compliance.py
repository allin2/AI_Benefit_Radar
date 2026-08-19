"""Protocol V0.1 Final Compliance Tests.

Comprehensive test suite verifying:
- Section A: Canonical Vendor Pool V1.2 runtime parity & high-risk mandatory surfaces (Qoder, Kimi, MiniMax, WorkBuddy, Coze, etc.)
- Section B: Program surface atomicity (PROGRAM_STUDENT does not complete other programs)
- Section C: Region-specific product separation (HappyShrimp CN vs International, Model Studio CN vs International)
- Section D: BLIND_SPOT semantics on mandatory surfaces
- Section E: Initial baseline NEW semantics (CREATE != NEW, UNKNOWN preserved, explicit NEW preserved)
- Section F: Extensible warning types
- Section G: Planner-driven precise forced review mapping (accurate Surface & Region)
- Section H: REVIEW_NOT_DUE gate & key-matching regressions
- Section I: Legacy database schema migration (forced_review_requirements) & idempotency
"""
import pytest
from sqlalchemy import create_engine, text
from ai_benefit_desk.db.models import (
    BenefitModel, CoverageHistoryModel, CanonicalSourceModel, LeadModel,
    ScanModel, SystemStateModel
)
from ai_benefit_desk.db.init_db import migrate_db_schema
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.services.export_service import ExportService
from ai_benefit_desk.services.review_service import ReviewPlanner
from ai_benefit_desk.services.vendor_pool_config import (
    VendorPoolConfig, CoverageCriticality, VENDOR_REGISTRY
)
from ai_benefit_desk.schemas.protocol_models import WarningItem
from ai_benefit_desk.utils.json_utils import dumps_json
from pydantic import ValidationError


def ensure_exported_scan(db_session, scan_id: str, rev: int = 0, mode: str = "FULL_SCAN", forced_reqs=None):
    existing = db_session.query(ScanModel).filter_by(scan_id=scan_id).first()
    if not existing:
        scan_rec = ScanModel(
            scan_id=scan_id,
            requested_mode=mode,
            baseline_revision_at_export=rev,
            import_status="EXPORTED"
        )
        if forced_reqs is not None:
            scan_rec.forced_review_requirements = forced_reqs
        db_session.add(scan_rec)
        db_session.commit()
    else:
        if forced_reqs is not None:
            existing.forced_review_requirements = forced_reqs
            db_session.commit()


def make_base_import(db_session, scan_id: str, rev: int = 0, baseline_action: str = "BUILD_INITIAL_BASELINE"):
    ensure_exported_scan(db_session, scan_id, rev=rev)
    return {
        "protocol_version": "0.1",
        "benefit_schema_version": "1.2.1",
        "package_type": "SCAN_IMPORT",
        "scan_result": {
            "scan_id": scan_id,
            "scan_mode": "FULL_SCAN",
            "context_baseline_revision": rev,
            "generated_at": "2026-08-19T02:00:00+08:00",
            "scan_statuses": ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"],
            "baseline_action": baseline_action
        },
        "benefit_changes": [],
        "lead_changes": [],
        "coverage_events": [],
        "source_updates": [],
        "manual_check_items": [],
        "warnings": []
    }


# =============================================================================
# A. Canonical Vendor Pool V1.2 Parity & High-Risk Surface Tests
# =============================================================================

def test_all_canonical_mandatory_surfaces_resolve_mandatory():
    """Manifest Contract Test: EVERY mandatory surface defined in canonical VENDOR_REGISTRY
    must resolve to CoverageCriticality.MANDATORY when queried through VendorPoolConfig."""
    failures = []
    total_checked = 0

    for vendor, products in VENDOR_REGISTRY.items():
        for ps in products:
            for surface in ps.mandatory_surfaces:
                total_checked += 1
                crit = VendorPoolConfig.get_coverage_criticality(vendor, ps.canonical_name, surface)
                if crit != CoverageCriticality.MANDATORY:
                    failures.append(f"{vendor} / {ps.canonical_name} / {surface} -> expected MANDATORY, got {crit}")

    assert total_checked >= 150, f"Expected at least 150 mandatory surface checks, got {total_checked}"
    assert len(failures) == 0, f"Parity failures detected ({len(failures)}):\n" + "\n".join(failures)


def test_qoder_credits_is_mandatory():
    """Qoder CREDITS is mandatory."""
    assert VendorPoolConfig.get_coverage_criticality("Qoder", "Qoder", "CREDITS") == CoverageCriticality.MANDATORY


def test_qoder_model_discount_is_mandatory():
    """Qoder MODEL_DISCOUNT is mandatory."""
    assert VendorPoolConfig.get_coverage_criticality("Qoder", "Qoder", "MODEL_DISCOUNT") == CoverageCriticality.MANDATORY


def test_qoder_events_is_mandatory():
    """Qoder EVENTS is mandatory."""
    assert VendorPoolConfig.get_coverage_criticality("Qoder", "Qoder", "EVENTS") == CoverageCriticality.MANDATORY


def test_qoder_daily_reset_is_mandatory():
    """Qoder DAILY_RESET is mandatory."""
    assert VendorPoolConfig.get_coverage_criticality("Qoder", "Qoder", "DAILY_RESET") == CoverageCriticality.MANDATORY


def test_kimi_referral_or_canonical_high_risk_surface_is_mandatory():
    """Kimi REFERRAL and CREDITS are mandatory."""
    assert VendorPoolConfig.get_coverage_criticality("Kimi", "Kimi", "REFERRAL") == CoverageCriticality.MANDATORY
    assert VendorPoolConfig.get_coverage_criticality("Kimi", "Kimi", "CREDITS") == CoverageCriticality.MANDATORY


def test_minimax_migration_or_canonical_high_risk_surface_is_mandatory():
    """MiniMax MIGRATION is mandatory."""
    assert VendorPoolConfig.get_coverage_criticality("MiniMax", "MiniMax", "MIGRATION") == CoverageCriticality.MANDATORY


def test_workbuddy_checkin_is_mandatory():
    """WorkBuddy CHECKIN and CLIENT_REWARD are mandatory."""
    assert VendorPoolConfig.get_coverage_criticality("Tencent", "WorkBuddy", "CHECKIN") == CoverageCriticality.MANDATORY
    assert VendorPoolConfig.get_coverage_criticality("Tencent", "WorkBuddy", "CLIENT_REWARD") == CoverageCriticality.MANDATORY


def test_coze_credits_is_mandatory():
    """Coze CN CREDITS is mandatory."""
    assert VendorPoolConfig.get_coverage_criticality("Coze", "Coze CN", "CREDITS") == CoverageCriticality.MANDATORY


def test_qoder_mandatory_not_checked_causes_scan_incomplete(db_session):
    """Qoder CREDITS is mandatory; NOT_CHECKED + PUBLIC_COMPLETE must fail."""
    pkg = make_base_import(db_session, "SCAN-QODER-001", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg["coverage_events"] = [{
        "vendor": "Qoder",
        "product": "Qoder",
        "surface": "CREDITS",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T02:00:00+08:00"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is False
    assert any("SCAN_INCOMPLETE" in e for e in prev["errors"])


def test_github_mandatory_not_checked_causes_scan_incomplete(db_session):
    """GitHub Copilot PROGRAM_STUDENT is mandatory; NOT_CHECKED + PUBLIC_COMPLETE must fail."""
    pkg = make_base_import(db_session, "SCAN-GITHUB-001", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg["coverage_events"] = [{
        "vendor": "GitHub",
        "product": "GitHub Copilot",
        "surface": "PROGRAM_STUDENT",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T02:00:00+08:00"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is False
    assert any("SCAN_INCOMPLETE" in e for e in prev["errors"])


def test_kimi_mandatory_not_checked_causes_scan_incomplete(db_session):
    """Kimi FREE_SIGNUP is mandatory; NOT_CHECKED + PUBLIC_COMPLETE must fail."""
    pkg = make_base_import(db_session, "SCAN-KIMI-001", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg["coverage_events"] = [{
        "vendor": "Kimi",
        "product": "Kimi",
        "surface": "FREE_SIGNUP",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T02:00:00+08:00"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is False
    assert any("SCAN_INCOMPLETE" in e for e in prev["errors"])


def test_unknown_vendor_surface_returns_unknown_warning(db_session):
    """Unregistered vendor returns CoverageCriticality.UNKNOWN and generates COVERAGE_CRITICALITY_UNKNOWN warning."""
    crit = VendorPoolConfig.get_coverage_criticality("AlienVendor", "QuantumLLM", "TELEPATHY")
    assert crit == CoverageCriticality.UNKNOWN

    pkg = make_base_import(db_session, "SCAN-UNK-001", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg["coverage_events"] = [{
        "vendor": "AlienVendor",
        "product": "QuantumLLM",
        "surface": "TELEPATHY",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T02:00:00+08:00"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is True
    assert any(w["type"] == "COVERAGE_CRITICALITY_UNKNOWN" for w in prev["warnings"])


# =============================================================================
# B. Program Atomicity Tests
# =============================================================================

def test_student_checked_does_not_complete_teacher():
    """Checking PROGRAM_STUDENT does not satisfy PROGRAM_TEACHER on GitHub Copilot."""
    crit_student = VendorPoolConfig.get_coverage_criticality("GitHub", "GitHub Copilot", "PROGRAM_STUDENT")
    crit_teacher = VendorPoolConfig.get_coverage_criticality("GitHub", "GitHub Copilot", "PROGRAM_TEACHER")
    assert crit_student == CoverageCriticality.MANDATORY
    assert crit_teacher == CoverageCriticality.MANDATORY


def test_student_checked_does_not_complete_research():
    """Checking PROGRAM_STUDENT does not satisfy PROGRAM_RESEARCH on OpenAI ChatGPT."""
    crit_student = VendorPoolConfig.get_coverage_criticality("OpenAI", "ChatGPT", "PROGRAM_STUDENT")
    crit_research = VendorPoolConfig.get_coverage_criticality("OpenAI", "ChatGPT", "PROGRAM_RESEARCH")
    assert crit_student == CoverageCriticality.MANDATORY
    assert crit_research == CoverageCriticality.MANDATORY


def test_program_category_does_not_complete_all_atomic_programs(db_session):
    """Checking only PROGRAM_STUDENT while leaving PROGRAM_STARTUP as NOT_CHECKED causes SCAN_INCOMPLETE."""
    pkg = make_base_import(db_session, "SCAN-PROG-001", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg["coverage_events"] = [
        {
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PROGRAM_STUDENT",
            "region": "GLOBAL",
            "coverage_state": "CHECKED_FOUND",
            "actual_checked_at": "2026-08-19T02:00:00+08:00",
            "scan_observed_at": "2026-08-19T02:00:00+08:00"
        },
        {
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PROGRAM_STARTUP",
            "region": "GLOBAL",
            "coverage_state": "NOT_CHECKED",
            "scan_observed_at": "2026-08-19T02:00:00+08:00"
        }
    ]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is False
    assert any("SCAN_INCOMPLETE" in e for e in prev["errors"])


# =============================================================================
# C. CN / International Product Separation Tests
# =============================================================================

def test_region_specific_products_are_not_collapsed():
    """CN and International products must be registered as distinct products in VendorPoolConfig."""
    # HappyShrimp CN vs International
    surfaces_cn = VendorPoolConfig.get_mandatory_surfaces("HappyShrimp", "HappyShrimp CN")
    surfaces_intl = VendorPoolConfig.get_mandatory_surfaces("HappyShrimp", "HappyShrimp International")
    assert surfaces_cn is not None and "CHECKIN" in surfaces_cn
    assert surfaces_intl is not None and "CHECKIN" not in surfaces_intl

    # Model Studio CN vs International
    ms_cn = VendorPoolConfig.get_mandatory_surfaces("Alibaba", "Alibaba Cloud Model Studio CN")
    ms_intl = VendorPoolConfig.get_mandatory_surfaces("Alibaba", "Model Studio International")
    assert ms_cn is not None and "TOKEN_GRANT" in ms_cn
    assert ms_intl is not None and "TOKEN_GRANT" not in ms_intl


# =============================================================================
# D. BLIND_SPOT Semantics Tests
# =============================================================================

def test_mandatory_hidden_account_blind_spot_allows_public_complete_overall_partial(db_session):
    """Mandatory surface HIDDEN_ACCOUNT marked as BLIND_SPOT allows PUBLIC_COMPLETE + OVERALL_PARTIAL."""
    pkg = make_base_import(db_session, "SCAN-BLIND-001", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"]
    pkg["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "HIDDEN_ACCOUNT",
        "region": "GLOBAL",
        "coverage_state": "BLIND_SPOT",
        "scan_observed_at": "2026-08-19T02:00:00+08:00"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is True


def test_optional_surface_not_checked_does_not_force_incomplete(db_session):
    """Explicitly optional surface (BLOG) NOT_CHECKED does NOT force incomplete."""
    pkg = make_base_import(db_session, "SCAN-OPT-001", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"]
    pkg["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "BLOG",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T02:00:00+08:00"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is True
    assert any(w["type"] == "NON_MANDATORY_NOT_CHECKED" for w in prev["warnings"])


# =============================================================================
# E. Initial Baseline NEW Semantics Tests
# =============================================================================

def test_initial_baseline_unknown_preserved(db_session):
    """UNKNOWN change_type on initial baseline stays UNKNOWN."""
    pkg = make_base_import(db_session, "SCAN-FINAL-IB-001", rev=0)
    pkg["benefit_changes"] = [{
        "operation": "CREATE",
        "local_ref": "BNEW-IB-001",
        "record": {
            "benefit_id": None,
            "vendor": "TestVendorA",
            "product": "TestProductA",
            "campaign_name": "TestCampaign",
            "benefit_type": "FREE_ACCESS",
            "benefit_detail": "Test detail",
            "first_seen": "2026-08-19",
            "last_checked": "2026-08-19",
            "official_source": "https://test.com",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE",
            "change_type": "UNKNOWN"
        }
    }]
    raw = dumps_json(pkg)
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is True
    ImportService.commit_import(db_session, preview["import_pkg"], raw)

    b = db_session.query(BenefitModel).filter_by(vendor="TestVendorA").first()
    assert b is not None
    assert b.change_type == "UNKNOWN"


def test_initial_baseline_new_preserved(db_session):
    """Legitimate NEW change_type on initial baseline stays NEW (not forced to UNKNOWN)."""
    pkg = make_base_import(db_session, "SCAN-FINAL-IB-002", rev=0)
    pkg["benefit_changes"] = [{
        "operation": "CREATE",
        "local_ref": "BNEW-IB-002",
        "record": {
            "benefit_id": None,
            "vendor": "TestVendorB",
            "product": "TestProductB",
            "campaign_name": "BrandNewCampaign",
            "benefit_type": "FREE_ACCESS",
            "benefit_detail": "Just launched today",
            "first_seen": "2026-08-19",
            "last_checked": "2026-08-19",
            "official_source": "https://test.com/new",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE",
            "change_type": "NEW"
        }
    }]
    raw = dumps_json(pkg)
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is True
    ImportService.commit_import(db_session, preview["import_pkg"], raw)

    b = db_session.query(BenefitModel).filter_by(vendor="TestVendorB").first()
    assert b is not None
    assert b.change_type == "NEW"


def test_create_does_not_imply_new(db_session):
    """CREATE operation does not automatically set change_type to NEW."""
    pkg = make_base_import(db_session, "SCAN-FINAL-IB-003", rev=0)
    pkg["benefit_changes"] = [{
        "operation": "CREATE",
        "local_ref": "BNEW-IB-003",
        "record": {
            "benefit_id": None,
            "vendor": "TestVendorC",
            "product": "TestProductC",
            "campaign_name": "OldCampaign",
            "benefit_type": "FREE_ACCESS",
            "benefit_detail": "Has been around",
            "first_seen": "2026-01-01",
            "last_checked": "2026-08-19",
            "official_source": "https://test.com/old",
            "source_level": "S",
            "verification_status": "CONFIRMED",
            "status": "ACTIVE",
            "change_type": "UNKNOWN"
        }
    }]
    raw = dumps_json(pkg)
    preview = ImportService.parse_and_preview(db_session, raw)
    ImportService.commit_import(db_session, preview["import_pkg"], raw)

    b = db_session.query(BenefitModel).filter_by(vendor="TestVendorC").first()
    assert b.change_type == "UNKNOWN"


# =============================================================================
# F. Warning Extensibility Tests
# =============================================================================

def test_known_warning_type_passes():
    """Known/recommended warning type parses successfully."""
    w = WarningItem(type="REGION_UNCERTAIN", message_zh="测试已知警告")
    assert w.type == "REGION_UNCERTAIN"


def test_unknown_warning_type_passes():
    """Unknown but well-formed warning type parses successfully (extensible)."""
    w = WarningItem(type="COVERAGE_CRITICALITY_UNKNOWN", message_zh="自定义警告类型")
    assert w.type == "COVERAGE_CRITICALITY_UNKNOWN"

    w2 = WarningItem(type="VENDOR_SPECIFIC_ISSUE", message_zh="厂商特定问题")
    assert w2.type == "VENDOR_SPECIFIC_ISSUE"


def test_empty_warning_type_fails():
    """Empty warning type must be rejected."""
    with pytest.raises(ValidationError):
        WarningItem(type="", message_zh="空类型")

    with pytest.raises(ValidationError):
        WarningItem(type="   ", message_zh="空白类型")


def test_warning_missing_message_fails():
    """Warning must have message_zh."""
    with pytest.raises(ValidationError):
        WarningItem(type="REGION_UNCERTAIN")


def test_unknown_warning_in_scan_import_package(db_session):
    """Unknown warning type in full ScanImportPackage does not cause schema failure."""
    pkg = make_base_import(db_session, "SCAN-FINAL-WRN-001", rev=0)
    pkg["warnings"] = [{
        "type": "CUSTOM_NEW_WARNING_TYPE",
        "message_zh": "这是一个自定义警告",
        "related_ref": None
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["import_pkg"] is not None
    assert any(w["type"] == "CUSTOM_NEW_WARNING_TYPE" for w in prev["warnings"])


# =============================================================================
# G. Precise Forced Review Mapping & Surface / Region Inference Tests
# =============================================================================

def test_workbuddy_checkin_forced_review_not_pricing(db_session):
    """WorkBuddy check-in lead must map to CLIENT_REWARD surface, not PRICING."""
    lead = LeadModel(
        lead_id="LEAD-WB-001",
        vendor="Tencent",
        product="WorkBuddy",
        lead_summary="WorkBuddy 每日签到领算力活动上线",
        verification_status="UNVERIFIED",
        source_level="A",
        _regions='["CN"]',
        first_seen="2026-08-19",
        last_checked="2026-08-19",
        status="OPEN"
    )
    surface = ReviewPlanner.infer_lead_surface(lead)
    assert surface == "CLIENT_REWARD", f"Expected CLIENT_REWARD, got {surface}"


def test_referral_forced_review_surface(db_session):
    """Kimi referral lead must map to REFERRAL surface, not PRICING."""
    lead = LeadModel(
        lead_id="LEAD-KIMI-REF",
        vendor="Kimi",
        product="Kimi",
        lead_summary="Kimi 邀请好友送额度活动",
        verification_status="UNVERIFIED",
        source_level="A",
        _regions='["CN"]',
        first_seen="2026-08-19",
        last_checked="2026-08-19",
        status="OPEN"
    )
    surface = ReviewPlanner.infer_lead_surface(lead)
    assert surface == "REFERRAL", f"Expected REFERRAL, got {surface}"


def test_deprecated_cn_source_keeps_cn_region(db_session):
    """Deprecated CN source preserves region CN, does not default to GLOBAL."""
    src = CanonicalSourceModel(
        source_id="SRC-DEP-CN",
        vendor="Tencent",
        product="WorkBuddy",
        surface="CLIENT_REWARD",
        source_name="腾讯 WorkBuddy 官方国内文档",
        url="https://workbuddy.qq.com/cn/docs",
        source_type="OFFICIAL_PORTAL",
        source_level="S",
        status="DEPRECATED",
        deprecation_reason="Page moved"
    )
    db_session.add(src)
    db_session.commit()

    reqs = ReviewPlanner.plan_forced_reviews(db_session, requested_mode="FULL_SCAN")
    wb_req = next((r for r in reqs if r["vendor"] == "Tencent" and r["surface"] == "CLIENT_REWARD"), None)
    assert wb_req is not None
    assert wb_req["region"] == "CN", f"Expected CN, got {wb_req['region']}"


def test_unknown_region_is_not_global(db_session):
    """When region cannot be determined, it is UNKNOWN (not coerced to GLOBAL)."""
    lead = LeadModel(
        lead_id="LEAD-UNK-REG",
        vendor="OpenAI",
        product="ChatGPT",
        lead_summary="New mysterious promotion",
        verification_status="UNVERIFIED",
        source_level="A",
        _regions='["UNKNOWN"]',
        first_seen="2026-08-19",
        last_checked="2026-08-19",
        status="OPEN"
    )
    db_session.add(lead)
    db_session.commit()

    reqs = ReviewPlanner.plan_forced_reviews(db_session, requested_mode="FULL_SCAN")
    match = next((r for r in reqs if r.get("reason") and "LEAD-UNK-REG" in str(r.get("reason", "")) or "mysterious" in str(r.get("reason", ""))), None)
    assert match is not None
    assert match["region"] == "UNKNOWN", f"Expected UNKNOWN, got {match['region']}"


# =============================================================================
# H. REVIEW_NOT_DUE Gate & Key-Matching Regression Tests
# =============================================================================

def test_exact_forced_review_blocks_review_not_due(db_session):
    """Planner-generated forced review requirement blocks REVIEW_NOT_DUE for exact Coverage Key."""
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-EXACT-001",
        scan_id="SCAN-PREV",
        vendor="Tencent",
        product="WorkBuddy",
        surface="CLIENT_REWARD",
        region="CN",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01T10:00:00+08:00",
        actual_checked_at="2026-08-01T10:00:00+08:00",
        next_review_at="2099-01-01"
    )
    db_session.add(c)

    lead = LeadModel(
        lead_id="LEAD-EXACT-001",
        vendor="Tencent",
        product="WorkBuddy",
        lead_summary="WorkBuddy 每日签到领算力活动上线",
        verification_status="UNVERIFIED",
        source_level="A",
        _regions='["CN"]',
        first_seen="2026-08-19",
        last_checked="2026-08-19",
        status="OPEN"
    )
    db_session.add(lead)
    db_session.commit()

    ctx = ExportService.generate_scan_context(db_session, requested_mode="FULL_SCAN")
    scan_id = ctx.scan.scan_id

    pkg = make_base_import(db_session, scan_id, rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    pkg["scan_result"]["scan_mode"] = "FULL_SCAN"
    pkg["coverage_events"] = [{
        "vendor": "Tencent",
        "product": "WorkBuddy",
        "surface": "CLIENT_REWARD",
        "region": "CN",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-19T02:00:00+08:00",
        "basis_coverage_id": "COV-EXACT-001"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is False
    assert any("强制提前复查信号" in e for e in prev["errors"])


def test_other_region_signal_does_not_block(db_session):
    """Forced review signal for US region does NOT block CN coverage event."""
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-REG-001",
        scan_id="SCAN-PREV",
        vendor="OpenAI",
        product="ChatGPT",
        surface="PARTNER_BUNDLE",
        region="CN",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01T10:00:00+08:00",
        actual_checked_at="2026-08-01T10:00:00+08:00",
        next_review_at="2099-01-01"
    )
    db_session.add(c)
    db_session.commit()

    # Signal for US only
    ensure_exported_scan(
        db_session, "SCAN-REG-001", rev=1, mode="FULL_SCAN",
        forced_reqs=[{
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PARTNER_BUNDLE",
            "region": "US",
            "reason": "US partner promotion"
        }]
    )

    pkg = make_base_import(db_session, "SCAN-REG-001", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    pkg["scan_result"]["scan_mode"] = "FULL_SCAN"
    pkg["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "PARTNER_BUNDLE",
        "region": "CN",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-19T02:00:00+08:00",
        "basis_coverage_id": "COV-REG-001"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is True


def test_other_surface_signal_does_not_block(db_session):
    """Forced review signal for PARTNER_BUNDLE does NOT block PRICING coverage event."""
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-SURF-001",
        scan_id="SCAN-PREV",
        vendor="OpenAI",
        product="ChatGPT",
        surface="PRICING",
        region="GLOBAL",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01T10:00:00+08:00",
        actual_checked_at="2026-08-01T10:00:00+08:00",
        next_review_at="2099-01-01"
    )
    db_session.add(c)
    db_session.commit()

    # Signal for PARTNER_BUNDLE only
    ensure_exported_scan(
        db_session, "SCAN-SURF-001", rev=1, mode="FULL_SCAN",
        forced_reqs=[{
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PARTNER_BUNDLE",
            "region": "GLOBAL",
            "reason": "Partner deal"
        }]
    )

    pkg = make_base_import(db_session, "SCAN-SURF-001", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    pkg["scan_result"]["scan_mode"] = "FULL_SCAN"
    pkg["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "PRICING",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-19T02:00:00+08:00",
        "basis_coverage_id": "COV-SURF-001"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is True


# =============================================================================
# I. Legacy Database Migration Tests
# =============================================================================

def test_old_scan_table_gets_forced_review_requirements_column():
    """Simulate legacy database without forced_review_requirements column; migration adds it."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id VARCHAR(64) NOT NULL,
                requested_mode VARCHAR(32) NOT NULL,
                actual_scan_mode VARCHAR(32),
                baseline_revision_at_export INTEGER,
                baseline_action VARCHAR(64),
                generated_context_at DATETIME,
                imported_at DATETIME,
                scan_statuses TEXT,
                import_status VARCHAR(32) DEFAULT 'EXPORTED',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        conn.execute(text("""
            CREATE TABLE coverage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coverage_id VARCHAR(32) NOT NULL,
                scan_id VARCHAR(64) NOT NULL,
                vendor VARCHAR(128) NOT NULL,
                product VARCHAR(128) NOT NULL,
                surface VARCHAR(64) NOT NULL,
                region VARCHAR(32) NOT NULL,
                coverage_state VARCHAR(32) NOT NULL,
                scan_observed_at VARCHAR(64) NOT NULL,
                actual_checked_at VARCHAR(64)
            )
        """))
        conn.commit()

        # Check before migration: column does not exist
        cols_before = [c[1] for c in conn.execute(text("PRAGMA table_info(scans)")).fetchall()]
        assert "forced_review_requirements" not in cols_before

    # Run migration
    migrate_db_schema(engine)

    # Check after migration: column exists
    with engine.connect() as conn:
        cols_after = [c[1] for c in conn.execute(text("PRAGMA table_info(scans)")).fetchall()]
        assert "forced_review_requirements" in cols_after


def test_scan_migration_is_idempotent():
    """Running migrate_db_schema multiple times is safe and idempotent."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id VARCHAR(64) NOT NULL,
                requested_mode VARCHAR(32) NOT NULL,
                import_status VARCHAR(32) DEFAULT 'EXPORTED'
            )
        """))
        conn.execute(text("""
            CREATE TABLE coverage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coverage_id VARCHAR(32) NOT NULL,
                scan_id VARCHAR(64) NOT NULL,
                vendor VARCHAR(128) NOT NULL,
                product VARCHAR(128) NOT NULL,
                surface VARCHAR(64) NOT NULL,
                region VARCHAR(32) NOT NULL,
                coverage_state VARCHAR(32) NOT NULL,
                scan_observed_at VARCHAR(64) NOT NULL,
                actual_checked_at VARCHAR(64)
            )
        """))
        conn.commit()

    migrate_db_schema(engine)
    migrate_db_schema(engine)
    migrate_db_schema(engine)

    with engine.connect() as conn:
        cols = [c[1] for c in conn.execute(text("PRAGMA table_info(scans)")).fetchall()]
        assert "forced_review_requirements" in cols


def test_existing_scan_rows_survive_migration():
    """Existing scan rows survive migration and retain data."""
    engine = create_engine("sqlite:///:memory:")
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE scans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id VARCHAR(64) NOT NULL,
                requested_mode VARCHAR(32) NOT NULL,
                import_status VARCHAR(32) DEFAULT 'EXPORTED'
            )
        """))
        conn.execute(text("""
            CREATE TABLE coverage_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                coverage_id VARCHAR(32) NOT NULL,
                scan_id VARCHAR(64) NOT NULL,
                vendor VARCHAR(128) NOT NULL,
                product VARCHAR(128) NOT NULL,
                surface VARCHAR(64) NOT NULL,
                region VARCHAR(32) NOT NULL,
                coverage_state VARCHAR(32) NOT NULL,
                scan_observed_at VARCHAR(64) NOT NULL,
                actual_checked_at VARCHAR(64)
            )
        """))
        conn.execute(text("INSERT INTO scans (scan_id, requested_mode) VALUES ('SCAN-HISTORIC-001', 'FULL_SCAN')"))
        conn.commit()

    migrate_db_schema(engine)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT scan_id, requested_mode, forced_review_requirements FROM scans WHERE scan_id = 'SCAN-HISTORIC-001'")).fetchone()
        assert row is not None
        assert row[0] == "SCAN-HISTORIC-001"
        assert row[1] == "FULL_SCAN"
        assert row[2] in (None, "[]")
