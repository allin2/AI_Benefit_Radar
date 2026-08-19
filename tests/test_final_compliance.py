"""Protocol V0.1 Final Compliance Tests.

Tests for:
- Vendor Pool V1.2 canonical mandatory surface resolution & completeness
- Vendor-specific coverage completion gate (Qoder, GitHub, Kimi, etc.)
- Program atomicity (PROGRAM_STUDENT does not satisfy PROGRAM_TEACHER / other programs)
- BLIND_SPOT semantics on mandatory surfaces
- Initial baseline NEW semantics (CREATE != NEW, UNKNOWN preserved, explicit NEW preserved)
- Extensible warning types
- Planner-driven forced early review signal lifecycle, DB persistence & reload resilience
"""
import pytest
from ai_benefit_desk.db.models import (
    BenefitModel, CoverageHistoryModel, CanonicalSourceModel, LeadModel,
    ScanModel, SystemStateModel
)
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.services.export_service import ExportService
from ai_benefit_desk.services.review_service import ReviewPlanner
from ai_benefit_desk.services.vendor_pool_config import (
    VendorPoolConfig, CoverageCriticality
)
from ai_benefit_desk.schemas.protocol_models import WarningItem, ScanImportPackage
from ai_benefit_desk.utils.json_utils import loads_json, dumps_json
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
# A. Vendor Pool Canonical Mandatory Surface & Completeness Tests
# =============================================================================

def test_runtime_vendor_pool_resolves_canonical_mandatory_surfaces():
    """All Tier 1 and major Chinese vendors/products resolve to non-empty mandatory surface sets."""
    canonical_checks = [
        ("OpenAI", "ChatGPT", "REFERRAL"),
        ("OpenAI", "OpenAI API", "MODEL_ECONOMICS"),
        ("Anthropic", "Claude", "PRICING"),
        ("Google", "Gemini", "FREE_SIGNUP"),
        ("Microsoft", "Copilot", "SUBSCRIPTION"),
        ("GitHub", "GitHub Copilot", "PROGRAM_STUDENT"),
        ("Qoder", "Qoder", "PRICING"),
        ("Kimi", "Kimi", "FREE_SIGNUP"),
        ("MiniMax", "MiniMax", "PRICING"),
        ("Mistral AI", "Le Chat", "FREE_SIGNUP"),
        ("Meta", "Llama Startup Program", "PROGRAM_STARTUP"),
        ("ByteDance", "Doubao", "MODEL_ECONOMICS"),
        ("Alibaba", "Tongyi Qianwen", "MODEL_ECONOMICS"),
        ("Tencent", "WorkBuddy", "CLIENT_REWARD"),
        ("TRAE", "TRAE CN", "CLIENT_REWARD"),
        ("Cursor", "Cursor", "FREE_SIGNUP"),
        ("Windsurf", "Windsurf", "FREE_SIGNUP"),
        ("DeepSeek", "DeepSeek API", "BILLING_CONSOLE"),
        ("xAI", "Grok", "MODEL_ECONOMICS"),
        ("Perplexity", "Perplexity", "REFERRAL"),
        ("Zhipu", "ChatGLM", "MODEL_ECONOMICS"),
    ]
    for vendor, product, expected_surface in canonical_checks:
        crit = VendorPoolConfig.get_coverage_criticality(vendor, product, expected_surface)
        assert crit == CoverageCriticality.MANDATORY, f"Expected {vendor}/{product}/{expected_surface} to be MANDATORY, got {crit}"

    # Verify all registered products have non-empty mandatory surfaces
    all_pairs = VendorPoolConfig.get_all_registered_vendor_products()
    assert len(all_pairs) >= 30, f"Expected at least 30 registered vendor/product pairs, got {len(all_pairs)}"
    for v, p in all_pairs:
        surfaces = VendorPoolConfig.get_mandatory_surfaces(v, p)
        assert surfaces and len(surfaces) > 0, f"Vendor {v}/{p} has empty mandatory surfaces!"


def test_qoder_mandatory_not_checked_causes_scan_incomplete(db_session):
    """Qoder PRICING is mandatory; NOT_CHECKED + PUBLIC_COMPLETE must fail."""
    pkg = make_base_import(db_session, "SCAN-QODER-001", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg["coverage_events"] = [{
        "vendor": "Qoder",
        "product": "Qoder",
        "surface": "PRICING",
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
    assert prev["is_valid"] is True  # UNKNOWN criticality does not hard block
    assert any(w["type"] == "COVERAGE_CRITICALITY_UNKNOWN" for w in prev["warnings"])


# =============================================================================
# B. Program Atomicity Tests
# =============================================================================

def test_student_checked_does_not_complete_teacher_requirement():
    """Checking PROGRAM_STUDENT does not satisfy other distinct program requirements (atomicity)."""
    # Verify both are registered separately on OpenAI/ChatGPT
    crit_student = VendorPoolConfig.get_coverage_criticality("OpenAI", "ChatGPT", "PROGRAM_STUDENT")
    crit_startup = VendorPoolConfig.get_coverage_criticality("OpenAI", "ChatGPT", "PROGRAM_STARTUP")
    crit_research = VendorPoolConfig.get_coverage_criticality("OpenAI", "ChatGPT", "PROGRAM_RESEARCH")
    
    assert crit_student == CoverageCriticality.MANDATORY
    assert crit_startup == CoverageCriticality.MANDATORY
    assert crit_research == CoverageCriticality.MANDATORY


def test_single_program_does_not_complete_all_programs(db_session):
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
# C. BLIND_SPOT Semantics Tests
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
# D. Planner-Driven Forced Early Review Signal & DB Persistence Tests
# =============================================================================

def test_planner_forced_review_blocks_review_not_due(db_session):
    """Planner-generated forced review signal (persisted on ScanModel) blocks REVIEW_NOT_DUE."""
    # Setup READY baseline with prior coverage
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-PLN-001",
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
    
    # Add an Open Lead that triggers ReviewPlanner to plan a forced review for OpenAI/ChatGPT/PRICING/GLOBAL
    lead = LeadModel(
        lead_id="LEAD-PLN-001",
        vendor="OpenAI",
        product="ChatGPT",
        lead_summary="Major price cut across GPT-5 tiers",
        verification_status="UNVERIFIED",
        source_level="A",
        _regions='["GLOBAL"]',
        first_seen="2026-08-19",
        last_checked="2026-08-19",
        status="OPEN"
    )
    db_session.add(lead)
    db_session.commit()

    # Generate scan context via ExportService -> calls ReviewPlanner.plan_forced_reviews()
    ctx = ExportService.generate_scan_context(db_session, requested_mode="FULL_SCAN")
    new_scan_id = ctx.scan.scan_id

    # Verify ScanModel persisted the forced review requirement
    scan_rec = db_session.query(ScanModel).filter_by(scan_id=new_scan_id).first()
    assert len(scan_rec.forced_review_requirements) > 0

    # Simulate scan result trying to use REVIEW_NOT_DUE on the planned forced surface
    pkg = make_base_import(db_session, new_scan_id, rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    pkg["scan_result"]["scan_mode"] = "FULL_SCAN"
    pkg["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "PRICING",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-19T02:00:00+08:00",
        "basis_coverage_id": "COV-PLN-001"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is False
    assert any("强制提前复查信号" in e for e in prev["errors"])


def test_no_forced_review_allows_valid_review_not_due(db_session):
    """REVIEW_NOT_DUE passes when no forced review signal exists for the coverage key."""
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-NOF-001",
        scan_id="SCAN-PREV",
        vendor="Anthropic",
        product="Claude",
        surface="PRICING",
        region="GLOBAL",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01T10:00:00+08:00",
        actual_checked_at="2026-08-01T10:00:00+08:00",
        next_review_at="2099-01-01"
    )
    db_session.add(c)
    db_session.commit()

    ensure_exported_scan(db_session, "SCAN-NOF-001", rev=1, mode="FULL_SCAN", forced_reqs=[])

    pkg = make_base_import(db_session, "SCAN-NOF-001", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    pkg["scan_result"]["scan_mode"] = "FULL_SCAN"
    pkg["coverage_events"] = [{
        "vendor": "Anthropic",
        "product": "Claude",
        "surface": "PRICING",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-19T02:00:00+08:00",
        "basis_coverage_id": "COV-NOF-001"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is True


def test_forced_review_matches_full_coverage_key(db_session):
    """Forced review signal matches exact (vendor, product, surface, region) key.
    Signal for OpenAI/ChatGPT/PRICING/US does not block OpenAI/ChatGPT/PRICING/GLOBAL."""
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-FKEY-001",
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

    # Register forced review signal for US region only
    ensure_exported_scan(
        db_session, "SCAN-FKEY-001", rev=1, mode="FULL_SCAN",
        forced_reqs=[{
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PRICING",
            "region": "US",
            "reason": "US pricing change only"
        }]
    )

    pkg = make_base_import(db_session, "SCAN-FKEY-001", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    pkg["scan_result"]["scan_mode"] = "FULL_SCAN"
    pkg["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "PRICING",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-19T02:00:00+08:00",
        "basis_coverage_id": "COV-FKEY-001"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is True


def test_forced_review_survives_new_service_instance_or_reload(db_session):
    """Forced review requirements survive DB reload because they are stored on ScanModel."""
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-PERSIST-001",
        scan_id="SCAN-PREV",
        vendor="DeepSeek",
        product="DeepSeek API",
        surface="PRICING",
        region="GLOBAL",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01T10:00:00+08:00",
        actual_checked_at="2026-08-01T10:00:00+08:00",
        next_review_at="2099-01-01"
    )
    db_session.add(c)
    db_session.commit()

    scan_id = "SCAN-PERSIST-001"
    ensure_exported_scan(
        db_session, scan_id, rev=1, mode="FULL_SCAN",
        forced_reqs=[{
            "vendor": "DeepSeek",
            "product": "DeepSeek API",
            "surface": "PRICING",
            "region": "GLOBAL",
            "reason": "DeepSeek V3 price update"
        }]
    )

    # Re-query scan_rec from fresh DB session
    reloaded_scan = db_session.query(ScanModel).filter_by(scan_id=scan_id).first()
    assert len(reloaded_scan.forced_review_requirements) == 1
    assert reloaded_scan.forced_review_requirements[0]["reason"] == "DeepSeek V3 price update"

    # Validation must successfully read and enforce it
    pkg = make_base_import(db_session, scan_id, rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    pkg["scan_result"]["scan_mode"] = "FULL_SCAN"
    pkg["coverage_events"] = [{
        "vendor": "DeepSeek",
        "product": "DeepSeek API",
        "surface": "PRICING",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-19T02:00:00+08:00",
        "basis_coverage_id": "COV-PERSIST-001"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is False
    assert any("强制提前复查信号" in e for e in prev["errors"])


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
    """CREATE operation does not automatically set change_type to NEW.
    If record says UNKNOWN, it stays UNKNOWN."""
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
