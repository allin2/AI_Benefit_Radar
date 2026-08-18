import pytest
from datetime import date
from sqlalchemy.orm import sessionmaker

from ai_benefit_desk.db.models import BenefitModel, LeadModel, CanonicalSourceModel, CoverageHistoryModel, ScanModel, SystemStateModel
from ai_benefit_desk.schemas.protocol_models import (
    BenefitChangeOperation, LeadChangeOperation, SourceUpdateOperation,
    ScanImportPackage, CoverageEventItem
)
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.utils.json_utils import loads_json, dumps_json
from ai_benefit_desk.config import PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION

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
            "baseline_action": baseline_action,
            "summary_notes": ""
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

def test_benefit_create_operation_strict_validation():
    # 1. Benefit CREATE with top-level benefit_id -> FAIL
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
    assert "禁止提供顶层 benefit_id" in str(exc.value)

    # 2. Benefit CREATE with patch -> FAIL
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
    assert "禁止提供 patch" in str(exc.value)

    # 3. Benefit CREATE with top-level last_checked -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "BNEW-001",
            "last_checked": "2026-08-18",
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
    assert "禁止提供顶层 last_checked" in str(exc.value)

def test_benefit_update_operation_strict_validation():
    # 1. Benefit UPDATE with local_ref -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "UPDATE",
            "benefit_id": "BEN-000001",
            "local_ref": "BNEW-001",
            "change_type": "EXTENDED",
            "patch": {"end_date": "2026-12-31"}
        })
    assert "禁止提供 local_ref" in str(exc.value)

    # 2. Benefit UPDATE with record -> FAIL
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
    assert "禁止提供 record" in str(exc.value)

    # 3. Benefit UPDATE with patch containing benefit_id -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "UPDATE",
            "benefit_id": "BEN-000001",
            "change_type": "EXTENDED",
            "patch": {"benefit_id": "BEN-000999"}
        })
    assert "禁止包含 benefit_id" in str(exc.value)

def test_benefit_confirm_no_change_operation_strict_validation(db_session):
    # 1. CONFIRM_NO_CHANGE without last_checked -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CONFIRM_NO_CHANGE",
            "benefit_id": "BEN-000001",
            "next_review_date": "2026-09-01"
        })
    assert "必须提供复核日期 (last_checked)" in str(exc.value)

    # 2. CONFIRM_NO_CHANGE without next_review_date -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CONFIRM_NO_CHANGE",
            "benefit_id": "BEN-000001",
            "last_checked": "2026-08-18"
        })
    assert "必须提供下次复查日期 (next_review_date)" in str(exc.value)

    # 3. CONFIRM_NO_CHANGE with patch -> FAIL
    with pytest.raises(Exception) as exc:
        BenefitChangeOperation.model_validate({
            "operation": "CONFIRM_NO_CHANGE",
            "benefit_id": "BEN-000001",
            "last_checked": "2026-08-18",
            "next_review_date": "2026-09-01",
            "patch": {"amount": 100}
        })
    assert "禁止提供 patch" in str(exc.value)

    # 4. Valid CONFIRM_NO_CHANGE updates last_checked and next_review_date in DB
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

    pkg = make_base_import(db_session, "SCAN-20260819-088", rev=0)
    pkg["benefit_changes"].append({
        "operation": "CONFIRM_NO_CHANGE",
        "benefit_id": "BEN-000088",
        "last_checked": "2026-08-19",
        "next_review_date": "2026-09-19"
    })
    raw = dumps_json(pkg)
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is True
    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw)
    assert commit_res["success"] is True

    b_after = db_session.query(BenefitModel).filter_by(benefit_id="BEN-000088").first()
    assert b_after.last_checked == "2026-08-19"
    assert b_after.next_review_date == "2026-09-19"
    assert b_after.change_type == "NO_CHANGE"

# ==========================================
# 2. Lead Operations Strict Contracts
# ==========================================

def test_lead_create_operation_strict_validation():
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
    assert "必须提供 product" in str(exc.value)

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
    assert "必须提供 verification_status" in str(exc.value)

    # 3. Missing first_seen -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "CREATE",
            "local_ref": "LNEW-001",
            "vendor": "Mistral",
            "product": "Le Chat",
            "lead_summary": "Summary",
            "verification_status": "UNVERIFIED",
            "source_level": "B",
            "last_checked": "2026-08-18"
        })
    assert "必须提供 first_seen" in str(exc.value)

    # 4. Lead CREATE with patch -> FAIL
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
    assert "禁止提供 patch" in str(exc.value)

def test_lead_reject_operation_strict_validation(db_session):
    # 1. Lead REJECT without checked_at -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "REJECT",
            "lead_id": "LEAD-000001",
            "reason": "官方页面已证实无此活动"
        })
    assert "必须提供检查时间戳 (checked_at)" in str(exc.value)

    # 2. Lead REJECT with non-timezone checked_at -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "REJECT",
            "lead_id": "LEAD-000001",
            "reason": "官方页面已证实无此活动",
            "checked_at": "2026-08-18T18:00:00"  # missing timezone
        })
    assert "带时区的 ISO8601 时间戳" in str(exc.value)

    # 3. Lead REJECT without reason -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "REJECT",
            "lead_id": "LEAD-000001",
            "checked_at": "2026-08-18T18:00:00+08:00"
        })
    assert "必须提供驳回原因" in str(exc.value)

    # 4. Valid Lead REJECT commits and persists reason + checked_at
    lead = LeadModel(
        lead_id="LEAD-000099",
        vendor="TestVendor",
        product="TestProduct",
        lead_summary="Fake Benefit",
        verification_status="UNVERIFIED",
        source_level="C",
        first_seen="2026-08-01",
        last_checked="2026-08-01",
        status="OPEN"
    )
    lead.regions = ["GLOBAL"]
    db_session.add(lead)
    db_session.commit()

    pkg = make_base_import(db_session, "SCAN-20260819-099", rev=0)
    pkg["lead_changes"].append({
        "operation": "REJECT",
        "lead_id": "LEAD-000099",
        "reason": "官方证实该推广活动已全线下架且无后续计划",
        "checked_at": "2026-08-19T01:15:00+08:00"
    })
    raw = dumps_json(pkg)
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is True
    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw)
    assert commit_res["success"] is True

    lead_after = db_session.query(LeadModel).filter_by(lead_id="LEAD-000099").first()
    assert lead_after.status == "REJECTED"
    assert lead_after.rejection_reason == "官方证实该推广活动已全线下架且无后续计划"
    assert lead_after.checked_at == "2026-08-19T01:15:00+08:00"

def test_lead_resolve_to_benefit_mutual_exclusion():
    # 1. Neither target_benefit_ref nor target_benefit_id -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "RESOLVE_TO_BENEFIT",
            "lead_id": "LEAD-000001"
        })
    assert "必须且只能二选一" in str(exc.value)

    # 2. Both target_benefit_ref and target_benefit_id -> FAIL
    with pytest.raises(Exception) as exc:
        LeadChangeOperation.model_validate({
            "operation": "RESOLVE_TO_BENEFIT",
            "lead_id": "LEAD-000001",
            "target_benefit_ref": "BNEW-001",
            "target_benefit_id": "BEN-000001"
        })
    assert "必须且只能二选一" in str(exc.value)

# ==========================================
# 3. Source Updates Strict Contracts
# ==========================================

def test_source_add_operation_strict_validation():
    # 1. Missing surface -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "ADD",
            "local_ref": "SNEW-001",
            "vendor": "OpenAI",
            "product": "ChatGPT",
            "source_name": "OpenAI Pricing",
            "url": "https://openai.com/pricing",
            "source_type": "OFFICIAL_PAGE",
            "source_level": "S",
            "last_verified_at": "2026-08-18T18:00:00+08:00"
        })
    assert "必须提供 surface" in str(exc.value)

    # 2. Missing source_type -> FAIL
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
    assert "必须提供 source_type" in str(exc.value)

    # 3. Missing last_verified_at -> FAIL
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
            "source_level": "S"
        })
    assert "必须提供 last_verified_at" in str(exc.value)

    # 4. Source ADD with source_id -> FAIL
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
    assert "source_id 由 Benefit Desk 分配" in str(exc.value)

def test_source_deprecate_operation_strict_validation(db_session):
    # 1. Missing reason -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "DEPRECATE",
            "source_id": "SRC-000001",
            "last_verified_at": "2026-08-18T18:00:00+08:00"
        })
    assert "必须提供废弃原因 (reason)" in str(exc.value)

    # 2. Missing last_verified_at -> FAIL
    with pytest.raises(Exception) as exc:
        SourceUpdateOperation.model_validate({
            "operation": "DEPRECATE",
            "source_id": "SRC-000001",
            "reason": "官方入口迁移"
        })
    assert "必须提供 last_verified_at 时间戳" in str(exc.value)

    # 3. Valid DEPRECATE persists deprecation_reason and last_verified_at in DB
    src = CanonicalSourceModel(
        source_id="SRC-000099",
        vendor="TestVendor",
        product="TestProduct",
        surface="PRICING",
        source_name="Old Pricing Page",
        url="https://test.com/pricing-old",
        source_type="PRICING",
        source_level="S",
        status="ACTIVE"
    )
    db_session.add(src)
    db_session.commit()

    pkg = make_base_import(db_session, "SCAN-20260819-SRC99", rev=0)
    pkg["source_updates"].append({
        "operation": "DEPRECATE",
        "source_id": "SRC-000099",
        "reason": "官方入口已迁移到新版控制台 Billing 中心",
        "last_verified_at": "2026-08-19T01:20:00+08:00"
    })
    raw = dumps_json(pkg)
    preview = ImportService.parse_and_preview(db_session, raw)
    assert preview["is_valid"] is True
    commit_res = ImportService.commit_import(db_session, preview["import_pkg"], raw)
    assert commit_res["success"] is True

    src_after = db_session.query(CanonicalSourceModel).filter_by(source_id="SRC-000099").first()
    assert src_after.status == "DEPRECATED"
    assert src_after.deprecation_reason == "官方入口已迁移到新版控制台 Billing 中心"
    assert src_after.last_verified_at == "2026-08-19T01:20:00+08:00"

# ==========================================
# 4. Coverage NOT_CHECKED Criticality Gate
# ==========================================

def test_coverage_not_checked_criticality_gate(db_session):
    # Case A: Critical Surface NOT_CHECKED + PUBLIC_COMPLETE without SCAN_INCOMPLETE -> FAIL
    pkg_crit = make_base_import(db_session, "SCAN-20260819-COV-CRIT", rev=0)
    pkg_crit["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg_crit["coverage_events"].append({
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "Official Pricing Plan",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T00:30:00+08:00"
    })
    prev_crit = ImportService.parse_and_preview(db_session, dumps_json(pkg_crit))
    assert prev_crit["is_valid"] is False
    assert any("存在关键待检查 (NOT_CHECKED) 项时，扫描状态必须包含 SCAN_INCOMPLETE" in e for e in prev_crit["errors"])

    # Case B: Non-Critical Surface NOT_CHECKED with PUBLIC_COMPLETE -> PASS with warning
    pkg_non_crit = make_base_import(db_session, "SCAN-20260819-COV-NONCRIT", rev=0)
    pkg_non_crit["scan_result"]["scan_statuses"] = ["PUBLIC_COMPLETE"]
    pkg_non_crit["coverage_events"].append({
        "vendor": "OpenAI",
        "product": "ChatGPT",
        "surface": "Unofficial Community Forum",
        "region": "GLOBAL",
        "coverage_state": "NOT_CHECKED",
        "scan_observed_at": "2026-08-19T00:30:00+08:00"
    })
    prev_non_crit = ImportService.parse_and_preview(db_session, dumps_json(pkg_non_crit))
    assert prev_non_crit["is_valid"] is True
    assert any(w["type"] == "NON_CRITICAL_NOT_CHECKED" for w in prev_non_crit["warnings"])
