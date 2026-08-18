import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_benefit_desk.db.database import Base
from ai_benefit_desk.db.init_db import init_db
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CanonicalSourceModel, CoverageHistoryModel,
    ManualCheckModel, SystemStateModel, ScanModel
)
from ai_benefit_desk.schemas.protocol_models import (
    ScanImportPackage, ScanContextPackage, LeadChangeOperation, SourceUpdateOperation
)
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.services.export_service import ExportService
from ai_benefit_desk.utils.json_utils import loads_json, dumps_json

FIXTURES_DIR = Path(__file__).parent / "fixtures"

def test_real_deep_full_scan_import_parse_and_schema_validation():
    """Verify that real ChatGPT-generated DEEP_FULL_SCAN package parses with zero Pydantic errors."""
    import_path = FIXTURES_DIR / "AI-Benefit-Scan-Import-SCAN-20260818-001.json"
    assert import_path.exists(), "Real scan import fixture not found!"

    with open(import_path, "r", encoding="utf-8") as f:
        raw_json = f.read()

    data = loads_json(raw_json)
    pkg = ScanImportPackage.model_validate(data)

    # 1. Package envelope verification
    assert pkg.protocol_version == "0.1"
    assert pkg.benefit_schema_version == "1.2.1"
    assert pkg.package_type == "SCAN_IMPORT"
    assert pkg.scan_result.scan_id == "SCAN-20260818-001"
    assert pkg.scan_result.scan_mode == "DEEP_FULL_SCAN"
    assert pkg.scan_result.context_baseline_revision == 0
    assert pkg.scan_result.baseline_action == "BUILD_INITIAL_BASELINE"

    # 2. Benefit changes (nested record under record)
    assert len(pkg.benefit_changes) == 112
    for bop in pkg.benefit_changes:
        assert bop.operation == "CREATE"
        assert bop.local_ref.startswith("BNEW-")
        assert bop.record is not None
        assert bop.record.benefit_id is None
        assert bop.record.vendor
        assert bop.record.product
        assert bop.record.campaign_name

    # 3. Lead changes (flat canonical structure, NOT nested in record)
    assert len(pkg.lead_changes) == 9
    for lop in pkg.lead_changes:
        assert lop.operation == "CREATE"
        assert lop.local_ref.startswith("LNEW-")
        assert lop.vendor
        assert lop.product
        assert lop.lead_summary
        assert lop.verification_status in ("UNVERIFIED", "LIKELY", "DISPUTED")
        assert lop.verification_status != "CONFIRMED"

    # 4. Coverage events
    assert len(pkg.coverage_events) == 340
    for cov in pkg.coverage_events:
        assert cov.coverage_state in ("CHECKED_FOUND", "CHECKED_NONE", "BLIND_SPOT", "NOT_CHECKED", "NOT_APPLICABLE", "REVIEW_NOT_DUE")
        assert cov.vendor
        assert cov.surface

    # 5. Source updates (flat canonical structure, NOT nested in record)
    assert len(pkg.source_updates) == 92
    for sop in pkg.source_updates:
        assert sop.operation == "ADD"
        assert sop.local_ref.startswith("SNEW-")
        assert sop.vendor
        assert sop.url
        assert sop.surface

    # 6. Manual check items
    assert len(pkg.manual_check_items) == 11
    for mop in pkg.manual_check_items:
        assert mop.local_ref.startswith("MNEW-")
        assert mop.vendor
        assert mop.reason

    # 7. Structured warnings
    assert len(pkg.warnings) == 6
    for w in pkg.warnings:
        assert w.type
        assert w.message_zh

def test_real_deep_full_scan_import_preview_and_commit(db_session):
    """Verify preview calculations, conflict detection, transactional commit, and re-export."""
    import_path = FIXTURES_DIR / "AI-Benefit-Scan-Import-SCAN-20260818-001.json"
    context_path = FIXTURES_DIR / "AI-Benefit-Scan-Context-SCAN-20260818-001.json"
    assert import_path.exists() and context_path.exists()

    with open(context_path, "r", encoding="utf-8") as f:
        ctx_raw = f.read()
    with open(import_path, "r", encoding="utf-8") as f:
        import_raw = f.read()

    # Pre-seed ScanModel for exported context
    scan_exp = ScanModel(
        scan_id="SCAN-20260818-001",
        requested_mode="DEEP_FULL_SCAN",
        baseline_revision_at_export=0,
        import_status="EXPORTED"
    )
    db_session.add(scan_exp)
    db_session.commit()

    # Preview
    preview = ImportService.parse_and_preview(db_session, import_raw)
    assert preview["is_valid"] is True, f"Preview failed with errors: {preview.get('errors')}"
    p_summary = preview["preview"]
    assert p_summary["benefit_create_count"] == 112
    assert p_summary["lead_create_count"] == 9
    assert p_summary["coverage_recheck_count"] == 273
    assert p_summary["coverage_blind_spot_count"] == 55
    assert p_summary["source_add_count"] == 92
    assert p_summary["manual_check_count"] == 11
    assert len(preview["warnings"]) == 6

    # Commit
    commit_res = ImportService.commit_import(
        db_session, preview["import_pkg"], import_raw, user_override_evidence=True
    )
    assert commit_res["success"] is True
    assert commit_res["baseline_revision_after"] == 1
    sys_state = db_session.query(SystemStateModel).filter_by(id=1).first()
    assert sys_state.baseline_state == "READY"
    assert sys_state.baseline_revision == 1

    # Verify Database Counts
    assert db_session.query(BenefitModel).count() == 112
    assert db_session.query(LeadModel).count() == 9
    assert db_session.query(CanonicalSourceModel).count() == 92
    assert db_session.query(CoverageHistoryModel).count() == 340
    assert db_session.query(ManualCheckModel).count() == 11

    # Verify ID assignment
    all_b = db_session.query(BenefitModel).all()
    for b in all_b:
        assert b.benefit_id.startswith("BEN-")
        # Under BUILD_INITIAL_BASELINE, change_type should be normalized to UNKNOWN
        assert b.change_type == "UNKNOWN"

    all_l = db_session.query(LeadModel).all()
    for l in all_l:
        assert l.lead_id.startswith("LEAD-")
        assert l.status == "OPEN"

    all_s = db_session.query(CanonicalSourceModel).all()
    for s in all_s:
        assert s.source_id.startswith("SRC-")

    # Re-export Scan Context
    new_ctx = ExportService.generate_scan_context(db_session, requested_mode="FULL_SCAN")
    assert new_ctx.scan.baseline_revision == 1
    assert new_ctx.scan.baseline_state == "READY"
    assert len(new_ctx.benefit_index) == 112
    assert len(new_ctx.open_leads) == 9
    assert len(new_ctx.canonical_sources) == 92
    assert len(new_ctx.latest_coverage) == 340

def test_flat_lead_operation_schema_and_validation(db_session):
    """Test schema constraints on flat LeadChangeOperation."""
    # 1. Lead CREATE with CONFIRMED raises ValueError
    with pytest.raises(Exception) as exc_info:
        LeadChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "LNEW-001",
            "vendor": "TestVendor",
            "product": "TestProd",
            "lead_summary": "Summary",
            "verification_status": "CONFIRMED"
        })
    assert "RESOLVE_TO_BENEFIT" in str(exc_info.value)

    # 2. Lead CREATE with unknown extra field raises extra_forbidden
    with pytest.raises(Exception) as exc_info:
        LeadChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "LNEW-001",
            "vendor": "TestVendor",
            "product": "TestProd",
            "lead_summary": "Summary",
            "verification_status": "UNVERIFIED",
            "invalid_extra_field": "disallowed"
        })
    assert "extra_forbidden" in str(exc_info.value) or "Extra inputs are not permitted" in str(exc_info.value)

def test_flat_source_update_schema_and_validation(db_session):
    """Test schema constraints on flat SourceUpdateOperation."""
    # 1. Source ADD with invalid timestamp raises ValueError
    with pytest.raises(Exception) as exc_info:
        SourceUpdateOperation.model_validate({
            "operation": "ADD",
            "local_ref": "SNEW-001",
            "vendor": "TestVendor",
            "product": "TestProd",
            "surface": "Pricing",
            "source_name": "Test Source",
            "url": "https://test.com",
            "last_verified_at": "2026-08-18"  # missing timezone
        })
    assert "timezone-aware" in str(exc_info.value)

    # 2. Source ADD with unknown extra field raises extra_forbidden
    with pytest.raises(Exception) as exc_info:
        SourceUpdateOperation.model_validate({
            "operation": "ADD",
            "local_ref": "SNEW-001",
            "vendor": "TestVendor",
            "product": "TestProd",
            "surface": "Pricing",
            "source_name": "Test Source",
            "url": "https://test.com",
            "extra_field": 123
        })
    assert "extra_forbidden" in str(exc_info.value) or "Extra inputs are not permitted" in str(exc_info.value)
