import pytest
import os
from pathlib import Path
from datetime import date
from sqlalchemy.orm import sessionmaker

from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CanonicalSourceModel, CoverageHistoryModel,
    ManualCheckModel, ScanModel, SystemStateModel
)
from ai_benefit_desk.schemas.protocol_models import (
    BenefitChangeOperation, LeadChangeOperation, SourceUpdateOperation,
    BenefitCreateOperation, BenefitUpdateOperation, BenefitConfirmNoChangeOperation,
    LeadCreateOperation, LeadUpdateOperation, LeadResolveOperation, LeadRejectOperation,
    SourceAddOperation, SourceUpdateOperationModel, SourceDeprecateOperation,
    ScanImportPackage, CoverageEventItem
)
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.utils.json_utils import loads_json, dumps_json
from ai_benefit_desk.config import PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "AI-Benefit-Scan-Import-SCAN-20260818-001.json"

def make_base_import(db_session, scan_id: str, rev: int = 0, baseline_action: str = "BUILD_INITIAL_BASELINE"):
    scan = ScanModel(
        scan_id=scan_id,
        requested_mode="FULL_SCAN",
        baseline_revision_at_export=rev,
        import_status="EXPORTED"
    )
    db_session.add(scan)
    db_session.commit()
    return {
        "protocol_version": PROTOCOL_VERSION,
        "benefit_schema_version": BENEFIT_SCHEMA_VERSION,
        "package_type": "SCAN_IMPORT",
        "scan_result": {
            "scan_id": scan_id,
            "scan_mode": "FULL_SCAN",
            "context_baseline_revision": rev,
            "generated_at": "2026-08-19T00:30:00+08:00",
            "scan_statuses": ["PUBLIC_COMPLETE"],
            "baseline_action": baseline_action
        },
        "benefit_changes": [],
        "lead_changes": [],
        "coverage_events": [],
        "source_updates": [],
        "manual_check_items": [],
        "warnings": []
    }

# ==========================================
# 1. Benefit Operations Strict Contracts
# ==========================================

def test_benefit_create_operation_negative_matrix():
    # 1. CREATE without record -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "BNEW-001"
        })
    assert "Field required" in str(exc.value) or "record" in str(exc.value)

    # 2. CREATE with top-level benefit_id -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "BNEW-001",
            "benefit_id": "BEN-000123",
            "record": {
                "benefit_id": None,
                "vendor": "OpenAI",
                "product": "ChatGPT",
                "campaign_name": "Free Plus",
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
    assert "Extra inputs are not permitted" in str(exc.value) or "benefit_id" in str(exc.value)

    # 3. CREATE with patch -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "BNEW-001",
            "patch": {"amount": 100},
            "record": {
                "benefit_id": None,
                "vendor": "OpenAI",
                "product": "ChatGPT",
                "campaign_name": "Free Plus",
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
    assert "Extra inputs are not permitted" in str(exc.value) or "patch" in str(exc.value)

    # 4. CREATE with record.benefit_id != None -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "BNEW-001",
            "record": {
                "benefit_id": "BEN-000001",
                "vendor": "OpenAI",
                "product": "ChatGPT",
                "campaign_name": "Free Plus",
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
    assert "benefit_id 必须为 null" in str(exc.value)

def test_benefit_update_operation_negative_matrix():
    # 1. UPDATE with local_ref -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "UPDATE",
            "benefit_id": "BEN-000001",
            "local_ref": "BNEW-001",
            "change_type": "EXTENDED",
            "patch": {"end_date": "2026-12-31"}
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "local_ref" in str(exc.value)

    # 2. UPDATE with record -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "UPDATE",
            "benefit_id": "BEN-000001",
            "change_type": "EXTENDED",
            "record": {
                "benefit_id": None,
                "vendor": "OpenAI",
                "product": "ChatGPT",
                "campaign_name": "Free Plus",
                "benefit_type": "FREE_ACCESS",
                "benefit_detail": "Detail",
                "first_seen": "2026-08-18",
                "last_checked": "2026-08-18",
                "official_source": "https://openai.com",
                "source_level": "S",
                "verification_status": "CONFIRMED",
                "status": "ACTIVE"
            },
            "patch": {"end_date": "2026-12-31"}
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "record" in str(exc.value)

    # 3. UPDATE with patch containing benefit_id -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "UPDATE",
            "benefit_id": "BEN-000001",
            "change_type": "EXTENDED",
            "patch": {"benefit_id": "BEN-000999"}
        })
    assert "禁止修改 benefit_id" in str(exc.value)

def test_benefit_confirm_no_change_operation_negative_matrix():
    # 1. CONFIRM_NO_CHANGE without last_checked -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CONFIRM_NO_CHANGE",
            "benefit_id": "BEN-000001",
            "next_review_date": "2026-09-01"
        })
    assert "Field required" in str(exc.value) or "last_checked" in str(exc.value)

    # 2. CONFIRM_NO_CHANGE without next_review_date -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CONFIRM_NO_CHANGE",
            "benefit_id": "BEN-000001",
            "last_checked": "2026-08-18"
        })
    assert "Field required" in str(exc.value) or "next_review_date" in str(exc.value)

    # 3. CONFIRM_NO_CHANGE with patch -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CONFIRM_NO_CHANGE",
            "benefit_id": "BEN-000001",
            "last_checked": "2026-08-18",
            "next_review_date": "2026-09-01",
            "patch": {"amount": 100}
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "patch" in str(exc.value)

    # 4. CONFIRM_NO_CHANGE with record -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CONFIRM_NO_CHANGE",
            "benefit_id": "BEN-000001",
            "last_checked": "2026-08-18",
            "next_review_date": "2026-09-01",
            "record": {}
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "record" in str(exc.value)

def test_benefit_positive_operations_lifecycle(db_session):
    # Setup baseline Benefit
    b = BenefitModel(
        benefit_id="BEN-000088",
        vendor="Anthropic",
        product="Claude",
        campaign_name="Claude Pro Quota",
        benefit_type="API_CREDITS",
        benefit_detail="Quota detail",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        next_review_date="2026-08-15",
        official_source="https://anthropic.com",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    db_session.add(b)
    db_session.commit()

    # 1. Positive Benefit CREATE
    pkg = make_base_import(db_session, "SCAN-20260819-BOP-POS", rev=0)
    pkg["benefit_changes"] = [
        {
            "operation": "CREATE",
            "local_ref": "BNEW-101",
            "record": {
                "benefit_id": None,
                "vendor": "Anthropic",
                "product": "Claude API",
                "campaign_name": "Claude 3.5 Sonnet Credits",
                "benefit_type": "API_CREDITS",
                "benefit_detail": "$20 Free API Credits",
                "first_seen": "2026-08-18",
                "last_checked": "2026-08-18",
                "official_source": "https://anthropic.com/api",
                "source_level": "S",
                "verification_status": "CONFIRMED",
                "status": "ACTIVE"
            }
        },
        {
            "operation": "UPDATE",
            "benefit_id": "BEN-000088",
            "change_type": "EXTENDED",
            "patch": {"end_date": "2026-10-31"}
        },
        {
            "operation": "CONFIRM_NO_CHANGE",
            "benefit_id": "BEN-000088",
            "last_checked": "2026-08-19",
            "next_review_date": "2026-09-19"
        }
    ]
    raw = dumps_json(pkg)
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is True
    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw)
    assert commit_res["success"] is True

    created_b = db_session.query(BenefitModel).filter_by(campaign_name="Claude 3.5 Sonnet Credits").first()
    assert created_b is not None
    assert created_b.benefit_id.startswith("BEN-")

    b_after = db_session.query(BenefitModel).filter_by(benefit_id="BEN-000088").first()
    assert b_after.last_checked == "2026-08-19"
    assert b_after.next_review_date == "2026-09-19"

# ==========================================
# 2. Lead Operations Strict Contracts
# ==========================================

def test_lead_create_operation_negative_matrix():
    # 1. Missing product -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "LNEW-001",
            "vendor": "Mistral",
            "lead_summary": "Summary",
            "verification_status": "UNVERIFIED",
            "source_level": "B",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18"
        })
    assert "Field required" in str(exc.value) or "product" in str(exc.value)

    # 2. Missing verification_status -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "LNEW-001",
            "vendor": "Mistral",
            "product": "Le Chat",
            "lead_summary": "Summary",
            "source_level": "B",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18"
        })
    assert "Field required" in str(exc.value) or "verification_status" in str(exc.value)

    # 3. Missing source_level -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "LNEW-001",
            "vendor": "Mistral",
            "product": "Le Chat",
            "lead_summary": "Summary",
            "verification_status": "UNVERIFIED",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18"
        })
    assert "Field required" in str(exc.value) or "source_level" in str(exc.value)

    # 4. Lead CREATE with lead_id -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "LNEW-001",
            "lead_id": "LEAD-000001",
            "vendor": "Mistral",
            "product": "Le Chat",
            "lead_summary": "Summary",
            "verification_status": "UNVERIFIED",
            "source_level": "B",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18"
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "lead_id" in str(exc.value)

    # 5. Lead CREATE with patch -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "LNEW-001",
            "vendor": "Mistral",
            "product": "Le Chat",
            "lead_summary": "Summary",
            "verification_status": "UNVERIFIED",
            "source_level": "B",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "patch": {"status": "RESOLVED"}
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "patch" in str(exc.value)

def test_lead_update_and_resolve_negative_matrix():
    # 1. UPDATE with local_ref -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "UPDATE",
            "lead_id": "LEAD-000001",
            "local_ref": "LNEW-001",
            "patch": {"lead_summary": "Updated"}
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "local_ref" in str(exc.value)

    # 2. RESOLVE without target -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "RESOLVE_TO_BENEFIT",
            "lead_id": "LEAD-000001"
        })
    assert "二选一" in str(exc.value)

    # 3. RESOLVE with both ref + id -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "RESOLVE_TO_BENEFIT",
            "lead_id": "LEAD-000001",
            "target_benefit_ref": "BNEW-001",
            "target_benefit_id": "BEN-000001"
        })
    assert "二选一" in str(exc.value)

def test_lead_reject_negative_matrix():
    # 1. REJECT without reason -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "REJECT",
            "lead_id": "LEAD-000001",
            "checked_at": "2026-08-18T18:00:00+08:00"
        })
    assert "Field required" in str(exc.value) or "reason" in str(exc.value)

    # 2. REJECT without checked_at -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "REJECT",
            "lead_id": "LEAD-000001",
            "reason": "官方页面已证实无此活动"
        })
    assert "Field required" in str(exc.value) or "checked_at" in str(exc.value)

    # 3. REJECT checked_at without timezone -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "REJECT",
            "lead_id": "LEAD-000001",
            "reason": "官方页面已证实无此活动",
            "checked_at": "2026-08-18T18:00:00"
        })
    assert "带时区" in str(exc.value) or "ISO8601" in str(exc.value)

    # 4. REJECT with patch -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "REJECT",
            "lead_id": "LEAD-000001",
            "reason": "官方页面已证实无此活动",
            "checked_at": "2026-08-18T18:00:00+08:00",
            "patch": {"status": "REJECTED"}
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "patch" in str(exc.value)

def test_lead_positive_operations_lifecycle(db_session):
    # Setup test leads & benefits
    lead1 = LeadModel(
        lead_id="LEAD-000111",
        vendor="Mistral",
        product="Le Chat",
        lead_summary="Mistral Deal 1",
        verification_status="UNVERIFIED",
        source_level="B",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        status="OPEN"
    )
    lead2 = LeadModel(
        lead_id="LEAD-000222",
        vendor="Mistral",
        product="Le Chat",
        lead_summary="Mistral Deal 2",
        verification_status="UNVERIFIED",
        source_level="C",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        status="OPEN"
    )
    b_exist = BenefitModel(
        benefit_id="BEN-000333",
        vendor="Mistral",
        product="Le Chat",
        campaign_name="Mistral Existing Benefit",
        benefit_type="API_CREDITS",
        benefit_detail="Existing",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        official_source="https://mistral.ai",
        source_level="S",
        verification_status="CONFIRMED",
        status="ACTIVE"
    )
    db_session.add_all([lead1, lead2, b_exist])
    db_session.commit()

    pkg = make_base_import(db_session, "SCAN-20260819-LOP-POS", rev=0)
    pkg["benefit_changes"] = [
        {
            "operation": "CREATE",
            "local_ref": "BNEW-201",
            "record": {
                "benefit_id": None,
                "vendor": "Mistral",
                "product": "Le Chat",
                "campaign_name": "Mistral New Plan",
                "benefit_type": "FREE_ACCESS",
                "benefit_detail": "Free Le Chat access",
                "first_seen": "2026-08-18",
                "last_checked": "2026-08-18",
                "official_source": "https://mistral.ai/news",
                "source_level": "S",
                "verification_status": "CONFIRMED",
                "status": "ACTIVE"
            }
        }
    ]
    pkg["lead_changes"] = [
        {
            "operation": "CREATE",
            "local_ref": "LNEW-201",
            "vendor": "Mistral",
            "product": "Le Chat",
            "lead_summary": "Potential Student Discount",
            "verification_status": "LIKELY",
            "source_level": "A",
            "regions": ["GLOBAL"],
            "missing_evidence": "Need official student doc",
            "first_seen": "2026-08-18",
            "last_checked": "2026-08-18",
            "next_review_date": "2026-09-01"
        },
        {
            "operation": "UPDATE",
            "lead_id": "LEAD-000111",
            "patch": {"lead_summary": "Updated Mistral Summary"}
        },
        {
            "operation": "RESOLVE_TO_BENEFIT",
            "lead_id": "LEAD-000111",
            "target_benefit_ref": "BNEW-201"
        },
        {
            "operation": "RESOLVE_TO_BENEFIT",
            "lead_id": "LEAD-000222",
            "target_benefit_id": "BEN-000333"
        }
    ]
    raw = dumps_json(pkg)
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is True
    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw)
    assert commit_res["success"] is True

    created_lead = db_session.query(LeadModel).filter_by(lead_summary="Potential Student Discount").first()
    assert created_lead is not None
    assert created_lead.lead_id.startswith("LEAD-")

    resolved_lead1 = db_session.query(LeadModel).filter_by(lead_id="LEAD-000111").first()
    assert resolved_lead1.status == "RESOLVED"
    assert resolved_lead1.resolved_benefit_id.startswith("BEN-")

    resolved_lead2 = db_session.query(LeadModel).filter_by(lead_id="LEAD-000222").first()
    assert resolved_lead2.status == "RESOLVED"
    assert resolved_lead2.resolved_benefit_id == "BEN-000333"

# ==========================================
# 3. Source Updates Strict Contracts
# ==========================================

def test_source_add_operation_negative_matrix():
    # 1. ADD without source_type -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "ADD",
            "local_ref": "SNEW-001",
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PRICING",
            "source_name": "OpenAI Pricing",
            "url": "https://openai.com/pricing",
            "source_level": "S",
            "last_verified_at": "2026-08-18T18:00:00+08:00"
        })
    assert "Field required" in str(exc.value) or "source_type" in str(exc.value)

    # 2. ADD without source_level -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "ADD",
            "local_ref": "SNEW-001",
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PRICING",
            "source_name": "OpenAI Pricing",
            "url": "https://openai.com/pricing",
            "source_type": "OFFICIAL_PAGE",
            "last_verified_at": "2026-08-18T18:00:00+08:00"
        })
    assert "Field required" in str(exc.value) or "source_level" in str(exc.value)

    # 3. ADD with source_id -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "ADD",
            "local_ref": "SNEW-001",
            "source_id": "SRC-000001",
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PRICING",
            "source_name": "OpenAI Pricing",
            "url": "https://openai.com/pricing",
            "source_type": "OFFICIAL_PAGE",
            "source_level": "S",
            "last_verified_at": "2026-08-18T18:00:00+08:00"
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "source_id" in str(exc.value)

    # 4. ADD with patch -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "ADD",
            "local_ref": "SNEW-001",
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "surface": "PRICING",
            "source_name": "OpenAI Pricing",
            "url": "https://openai.com/pricing",
            "source_type": "OFFICIAL_PAGE",
            "source_level": "S",
            "last_verified_at": "2026-08-18T18:00:00+08:00",
            "patch": {"status": "ACTIVE"}
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "patch" in str(exc.value)

def test_source_update_and_deprecate_negative_matrix():
    # 1. UPDATE with local_ref -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "UPDATE",
            "source_id": "SRC-000001",
            "local_ref": "SNEW-001",
            "patch": {"source_name": "New Name"}
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "local_ref" in str(exc.value)

    # 2. DEPRECATE without reason -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "DEPRECATE",
            "source_id": "SRC-000001",
            "last_verified_at": "2026-08-18T18:00:00+08:00"
        })
    assert "Field required" in str(exc.value) or "reason" in str(exc.value)

    # 3. DEPRECATE without last_verified_at -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "DEPRECATE",
            "source_id": "SRC-000001",
            "reason": "官方入口迁移"
        })
    assert "Field required" in str(exc.value) or "last_verified_at" in str(exc.value)

    # 4. DEPRECATE last_verified_at without timezone -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "DEPRECATE",
            "source_id": "SRC-000001",
            "reason": "官方入口迁移",
            "last_verified_at": "2026-08-18T18:00:00"
        })
    assert "带时区" in str(exc.value) or "ISO8601" in str(exc.value)

    # 5. DEPRECATE with patch -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "DEPRECATE",
            "source_id": "SRC-000001",
            "reason": "官方入口迁移",
            "last_verified_at": "2026-08-18T18:00:00+08:00",
            "patch": {"status": "DEPRECATED"}
        })
    assert "Extra inputs are not permitted" in str(exc.value) or "patch" in str(exc.value)

def test_source_positive_operations_lifecycle(db_session):
    src = CanonicalSourceModel(
        source_id="SRC-000555",
        vendor="Google",
        product="Gemini",
        surface="PRICING",
        source_name="Old Gemini Pricing",
        url="https://gemini.google.com/pricing-old",
        source_type="PRICING",
        source_level="S",
        status="ACTIVE"
    )
    db_session.add(src)
    db_session.commit()

    pkg = make_base_import(db_session, "SCAN-20260819-SOP-POS", rev=0)
    pkg["source_updates"] = [
        {
            "operation": "ADD",
            "local_ref": "SNEW-301",
            "vendor": "Google",
            "product": "Gemini",
            "surface": "DOCS",
            "source_name": "Gemini API Platform Docs",
            "url": "https://ai.google.dev/docs",
            "source_type": "OFFICIAL_DOCS",
            "source_level": "S",
            "status": "ACTIVE",
            "last_verified_at": "2026-08-19T01:30:00+08:00"
        },
        {
            "operation": "UPDATE",
            "source_id": "SRC-000555",
            "patch": {"source_name": "Updated Gemini Pricing Name"}
        },
        {
            "operation": "DEPRECATE",
            "source_id": "SRC-000555",
            "reason": "已迁移至 Google AI Studio",
            "last_verified_at": "2026-08-19T01:35:00+08:00"
        }
    ]
    raw = dumps_json(pkg)
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is True
    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw)
    assert commit_res["success"] is True

    created_src = db_session.query(CanonicalSourceModel).filter_by(source_name="Gemini API Platform Docs").first()
    assert created_src is not None
    assert created_src.source_id.startswith("SRC-")

    dep_src = db_session.query(CanonicalSourceModel).filter_by(source_id="SRC-000555").first()
    assert dep_src.status == "DEPRECATED"
    assert dep_src.deprecation_reason == "已迁移至 Google AI Studio"
    assert dep_src.last_verified_at == "2026-08-19T01:35:00+08:00"

# ==========================================
# 4. Coverage Completion Regression Tests
# ==========================================

def test_coverage_mandatory_surfaces_completion_gate(db_session):
    # Case A: Mandatory MODEL_ECONOMICS + NOT_CHECKED -> SCAN_INCOMPLETE required
    pkg_a = make_base_import(db_session, "SCAN-20260819-COV-A", rev=0)
    pkg_a["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg_a["coverage_events"] = [{
        "vendor": "Anthropic",
        "product": "Anthropic API",
        "surface": "MODEL_ECONOMICS",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T00:30:00+08:00"
    }]
    prev_a = ImportService.parse_and_preview(db_session, dumps_json(pkg_a))
    assert prev_a["is_valid"] is False
    assert any("SCAN_INCOMPLETE" in e for e in prev_a["errors"])

    # Case B: Mandatory PARTNER_BUNDLE + NOT_CHECKED -> SCAN_INCOMPLETE required
    pkg_b = make_base_import(db_session, "SCAN-20260819-COV-B", rev=0)
    pkg_b["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg_b["coverage_events"] = [{
        "vendor": "Microsoft",
        "product": "Azure OpenAI",
        "surface": "PARTNER_BUNDLE",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T00:30:00+08:00"
    }]
    prev_b = ImportService.parse_and_preview(db_session, dumps_json(pkg_b))
    assert prev_b["is_valid"] is False
    assert any("SCAN_INCOMPLETE" in e for e in prev_b["errors"])

    # Case C: Mandatory PROGRAMS + NOT_CHECKED -> SCAN_INCOMPLETE required
    pkg_c = make_base_import(db_session, "SCAN-20260819-COV-C", rev=0)
    pkg_c["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg_c["coverage_events"] = [{
        "vendor": "Google",
        "product": "Google AI Studio",
        "surface": "PROGRAMS",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T00:30:00+08:00"
    }]
    prev_c = ImportService.parse_and_preview(db_session, dumps_json(pkg_c))
    assert prev_c["is_valid"] is False
    assert any("SCAN_INCOMPLETE" in e for e in prev_c["errors"])

    # Case D: Non-mandatory COMMUNITY_FORUM + NOT_CHECKED -> PASS with warning
    pkg_d = make_base_import(db_session, "SCAN-20260819-COV-D", rev=0)
    pkg_d["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg_d["coverage_events"] = [{
        "vendor": "Google",
        "product": "Google AI Studio",
        "surface": "COMMUNITY_FORUM",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T00:30:00+08:00"
    }]
    prev_d = ImportService.parse_and_preview(db_session, dumps_json(pkg_d))
    assert prev_d["is_valid"] is True
    assert any(w["type"] == "NON_MANDATORY_NOT_CHECKED" for w in prev_d["warnings"])

    # Case E: Mandatory HIDDEN_ACCOUNT + BLIND_SPOT -> PUBLIC_COMPLETE + OVERALL_PARTIAL is valid
    pkg_e = make_base_import(db_session, "SCAN-20260819-COV-E", rev=0)
    pkg_e["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"]
    pkg_e["coverage_events"] = [{
        "vendor": "Google",
        "product": "Google AI Studio",
        "surface": "HIDDEN_ACCOUNT",
        "region": "GLOBAL",
        "coverage_state": "BLIND_SPOT",
        "scan_observed_at": "2026-08-19T00:30:00+08:00"
    }]
    prev_e = ImportService.parse_and_preview(db_session, dumps_json(pkg_e))
    assert prev_e["is_valid"] is True

    # Case F: Criticality UNKNOWN + NOT_CHECKED -> generates COVERAGE_CRITICALITY_UNKNOWN warning
    pkg_f = make_base_import(db_session, "SCAN-20260819-COV-F", rev=0)
    pkg_f["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg_f["coverage_events"] = [{
        "vendor": "UnknownVendor",
        "product": "UnknownProduct",
        "surface": "CustomMysteriousChannelXYZ",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T00:30:00+08:00"
    }]
    prev_f = ImportService.parse_and_preview(db_session, dumps_json(pkg_f))
    assert prev_f["is_valid"] is True
    assert any(w["type"] == "COVERAGE_CRITICALITY_UNKNOWN" for w in prev_f["warnings"])

# ==========================================
# 5. Real Large Scan Import E2E Test
# ==========================================

def test_real_scan_import_20260818_001_end_to_end_preview(db_session):
    """Real ChatGPT Scan Import E2E verification."""
    assert FIXTURE_PATH.exists(), f"Fixture missing: {FIXTURE_PATH}"
    
    with open(FIXTURE_PATH, "r", encoding="utf-8") as f:
        raw_json_str = f.read()

    # Pre-insert exported scan record so scan_id revision binding is satisfied
    fixture_dict = loads_json(raw_json_str)
    scan_meta = fixture_dict["scan_result"]
    scan_id = scan_meta["scan_id"]
    ctx_rev = scan_meta["context_baseline_revision"]

    scan_rec = ScanModel(
        scan_id=scan_id,
        requested_mode=scan_meta["scan_mode"],
        baseline_revision_at_export=ctx_rev,
        import_status="EXPORTED"
    )
    db_session.add(scan_rec)
    db_session.commit()

    # Step 1: Parse and Preview
    preview_res = ImportService.parse_and_preview(db_session, raw_json_str)
    
    # Assert structural integrity and schema compliance
    assert preview_res["is_valid"] is True, f"Validation errors: {preview_res.get('errors')}"
    
    preview_counts = preview_res["preview"]
    assert preview_counts["benefit_create_count"] == 112
    assert preview_counts["lead_create_count"] == 9
    assert preview_counts["source_add_count"] == 92
    assert preview_counts["coverage_event_count"] == 340
    assert preview_res["import_pkg"].package_type == "SCAN_IMPORT"
    assert preview_counts["scan_id"] == "SCAN-20260818-001"
