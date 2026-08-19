"""Protocol V0.1 Final Compliance Tests.

Tests for:
- Vendor-specific coverage mandatory surface validation
- Initial baseline NEW semantics
- Extensible warning types
- Forced early review signals
"""
import pytest
from ai_benefit_desk.db.models import (
    BenefitModel, CoverageHistoryModel, ScanModel, SystemStateModel
)
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.services.vendor_pool_config import (
    VendorPoolConfig, CoverageCriticality, ForcedReviewSignal
)
from ai_benefit_desk.schemas.protocol_models import WarningItem, ScanImportPackage
from ai_benefit_desk.utils.json_utils import loads_json, dumps_json
from pydantic import ValidationError


def ensure_exported_scan(db_session, scan_id: str, rev: int = 0, mode: str = "FULL_SCAN"):
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
# 1. Vendor-Specific Coverage Tests
# =============================================================================

def test_openai_referral_not_checked_is_incomplete_if_mandatory(db_session):
    """REFERRAL is mandatory for OpenAI/ChatGPT per Vendor Pool V1.2.
    NOT_CHECKED + PUBLIC_COMPLETE must fail."""
    pkg = make_base_import(db_session, "SCAN-FINAL-VP-001", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "REFERRAL",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T02:00:00+08:00"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is False
    assert any("SCAN_INCOMPLETE" in e for e in prev["errors"])


def test_partner_bundle_mandatory_not_checked_is_incomplete(db_session):
    """PARTNER_BUNDLE is mandatory for OpenAI/ChatGPT.
    NOT_CHECKED + PUBLIC_COMPLETE must fail."""
    pkg = make_base_import(db_session, "SCAN-FINAL-VP-002", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "PARTNER_BUNDLE",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T02:00:00+08:00"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is False
    assert any("SCAN_INCOMPLETE" in e for e in prev["errors"])
    assert any("PUBLIC_COMPLETE" in e for e in prev["errors"])


def test_optional_surface_not_checked_does_not_force_incomplete(db_session):
    """Explicitly optional surface (BLOG) NOT_CHECKED does NOT force incomplete."""
    pkg = make_base_import(db_session, "SCAN-FINAL-VP-003", rev=0)
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


def test_unknown_criticality_generates_warning(db_session):
    """Unknown vendor/product/surface produces COVERAGE_CRITICALITY_UNKNOWN warning."""
    pkg = make_base_import(db_session, "SCAN-FINAL-VP-004", rev=0)
    pkg["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg["coverage_events"] = [{
        "vendor": "NewVendorXYZ",
        "product": "NewProductABC",
        "surface": "MYSTERIOUS_CHANNEL",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T02:00:00+08:00"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is True  # Not a hard fail
    assert any(w["type"] == "COVERAGE_CRITICALITY_UNKNOWN" for w in prev["warnings"])


def test_hidden_account_blind_spot_allows_public_complete_overall_partial(db_session):
    """HIDDEN_ACCOUNT as BLIND_SPOT is valid with PUBLIC_COMPLETE + OVERALL_PARTIAL."""
    pkg = make_base_import(db_session, "SCAN-FINAL-VP-005", rev=0)
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


def test_vendor_pool_criticality_api():
    """Direct VendorPoolConfig API test."""
    # Known mandatory
    assert VendorPoolConfig.get_coverage_criticality(
        "OpenAI", "ChatGPT", "REFERRAL"
    ) == CoverageCriticality.MANDATORY

    assert VendorPoolConfig.get_coverage_criticality(
        "OpenAI", "OpenAI API", "MODEL_ECONOMICS"
    ) == CoverageCriticality.MANDATORY

    # Known optional
    assert VendorPoolConfig.get_coverage_criticality(
        "OpenAI", "ChatGPT", "COMMUNITY_FORUM"
    ) == CoverageCriticality.OPTIONAL

    # Unknown vendor/product
    assert VendorPoolConfig.get_coverage_criticality(
        "UnknownVendor", "UnknownProduct", "PRICING"
    ) == CoverageCriticality.UNKNOWN

    # Known vendor, unknown surface
    assert VendorPoolConfig.get_coverage_criticality(
        "OpenAI", "ChatGPT", "MYSTERY_XYZ"
    ) == CoverageCriticality.UNKNOWN


# =============================================================================
# 2. Initial Baseline NEW Semantics Tests
# =============================================================================

def test_initial_baseline_unknown_remains_unknown(db_session):
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


def test_initial_baseline_real_new_remains_new(db_session):
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
    # No automatic inference of NEW just because it's a CREATE operation


# =============================================================================
# 3. Warning Type Extensibility Tests
# =============================================================================

def test_known_warning_type_passes():
    """Known/recommended warning type parses successfully."""
    w = WarningItem(type="REGION_UNCERTAIN", message_zh="测试已知警告")
    assert w.type == "REGION_UNCERTAIN"


def test_unknown_warning_type_passes():
    """Unknown but well-formed warning type parses successfully (extensible)."""
    w = WarningItem(type="COVERAGE_CRITICALITY_UNKNOWN", message_zh="自定义警告类型")
    assert w.type == "COVERAGE_CRITICALITY_UNKNOWN"

    # Completely novel type
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
        WarningItem(type="REGION_UNCERTAIN")  # missing message_zh


def test_unknown_warning_in_scan_import_package(db_session):
    """Unknown warning type in full ScanImportPackage does not cause schema failure."""
    pkg = make_base_import(db_session, "SCAN-FINAL-WRN-001", rev=0)
    pkg["warnings"] = [{
        "type": "CUSTOM_NEW_WARNING_TYPE",
        "message_zh": "这是一个自定义警告",
        "related_ref": None
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    # Should not fail schema validation
    assert prev["import_pkg"] is not None
    assert any(w["type"] == "CUSTOM_NEW_WARNING_TYPE" for w in prev["warnings"])


# =============================================================================
# 4. Forced Early Review Signal Tests
# =============================================================================

def test_review_not_due_without_force_signal_passes(db_session):
    """REVIEW_NOT_DUE passes when no forced review signal exists."""
    # Setup: READY baseline with existing coverage
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-FR-001",
        scan_id="SCAN-PREV",
        vendor="Google",
        product="Gemini",
        surface="PRICING",
        region="GLOBAL",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01T10:00:00+08:00",
        actual_checked_at="2026-08-01T10:00:00+08:00",
        next_review_at="2099-01-01"
    )
    db_session.add(c)
    db_session.commit()

    VendorPoolConfig.clear_forced_review_signals()

    pkg = make_base_import(db_session, "SCAN-FINAL-FR-001", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    pkg["scan_result"]["scan_mode"] = "FULL_SCAN"
    pkg["coverage_events"] = [{
        "vendor": "Google",
        "product": "Gemini",
        "surface": "PRICING",
        "region": "GLOBAL",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-19T02:00:00+08:00",
        "basis_coverage_id": "COV-FR-001"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is True


def test_review_not_due_with_force_signal_fails(db_session):
    """REVIEW_NOT_DUE fails when a forced review signal exists for the coverage key."""
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-FR-002",
        scan_id="SCAN-PREV",
        vendor="OpenAI",
        product="ChatGPT",
        surface="PARTNER_BUNDLE",
        region="US",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01T10:00:00+08:00",
        actual_checked_at="2026-08-01T10:00:00+08:00",
        next_review_at="2099-01-01"
    )
    db_session.add(c)
    db_session.commit()

    VendorPoolConfig.clear_forced_review_signals()
    VendorPoolConfig.register_forced_review_signal(
        ForcedReviewSignal(
            vendor="OpenAI",
            product="ChatGPT",
            surface="PARTNER_BUNDLE",
            region="US",
            reason="Major partnership announcement"
        )
    )

    pkg = make_base_import(db_session, "SCAN-FINAL-FR-002", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    pkg["scan_result"]["scan_mode"] = "FULL_SCAN"
    pkg["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "PARTNER_BUNDLE",
        "region": "US",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-19T02:00:00+08:00",
        "basis_coverage_id": "COV-FR-002"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    assert prev["is_valid"] is False
    assert any("强制提前复查信号" in e for e in prev["errors"])

    VendorPoolConfig.clear_forced_review_signals()


def test_force_review_matches_full_coverage_key(db_session):
    """Forced review signal must match full coverage key (vendor/product/surface/region).
    Signal for OpenAI/ChatGPT/PARTNER_BUNDLE/US does NOT block
    OpenAI/OpenAI API/MODEL_ECONOMICS/CN."""
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    sys_state.baseline_state = "READY"
    sys_state.baseline_revision = 1
    db_session.commit()

    c = CoverageHistoryModel(
        coverage_id="COV-FR-003",
        scan_id="SCAN-PREV",
        vendor="OpenAI",
        product="OpenAI API",
        surface="MODEL_ECONOMICS",
        region="CN",
        coverage_state="CHECKED_FOUND",
        scan_observed_at="2026-08-01T10:00:00+08:00",
        actual_checked_at="2026-08-01T10:00:00+08:00",
        next_review_at="2099-01-01"
    )
    db_session.add(c)
    db_session.commit()

    VendorPoolConfig.clear_forced_review_signals()
    # Register signal for DIFFERENT coverage key
    VendorPoolConfig.register_forced_review_signal(
        ForcedReviewSignal(
            vendor="OpenAI",
            product="ChatGPT",
            surface="PARTNER_BUNDLE",
            region="US",
            reason="Wrong target"
        )
    )

    pkg = make_base_import(db_session, "SCAN-FINAL-FR-003", rev=1, baseline_action="UPDATE_EXISTING_BASELINE")
    pkg["scan_result"]["scan_mode"] = "FULL_SCAN"
    pkg["coverage_events"] = [{
        "vendor": "OpenAI",
        "product": "OpenAI API",
        "surface": "MODEL_ECONOMICS",
        "region": "CN",
        "coverage_state": "REVIEW_NOT_DUE",
        "scan_observed_at": "2026-08-19T02:00:00+08:00",
        "basis_coverage_id": "COV-FR-003"
    }]
    prev = ImportService.parse_and_preview(db_session, dumps_json(pkg))
    # Should PASS because signal doesn't match this coverage key
    assert prev["is_valid"] is True

    VendorPoolConfig.clear_forced_review_signals()
