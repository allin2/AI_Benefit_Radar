import pytest
import os
import json
from datetime import date
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ai_benefit_desk.db.database import Base
from ai_benefit_desk.db.init_db import init_db
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CoverageHistoryModel, CanonicalSourceModel,
    UserBenefitStateModel, ScanModel, ImportAuditModel, SystemStateModel, ManualCheckModel
)
from ai_benefit_desk.services.export_service import ExportService
from ai_benefit_desk.services.import_service import ImportService
from ai_benefit_desk.utils.json_utils import dumps_json, loads_json

# =========================================================================
# LIFECYCLE A — Initial Baseline Lifecycle
# =========================================================================
def test_lifecycle_a_initial_baseline():
    """
    EMPTY
    -> Export Context
    -> DEEP_FULL_SCAN Import
    -> BUILD_INITIAL_BASELINE
    -> CREATE Benefit
    -> CREATE Lead
    -> Source ADD
    -> Coverage
    -> Manual Check
    -> Preview
    -> Commit
    -> READY
    -> baseline_revision + 1
    -> Export Context
    -> same scan_id rejected
    """
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(bind=test_engine)
    Session = sessionmaker(bind=test_engine)
    db = Session()

    try:
        # 1. State: EMPTY, rev = 0
        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        assert sys_state.baseline_state == "EMPTY"
        assert sys_state.baseline_revision == 0

        # 2. Export Context (DEEP_FULL_SCAN)
        context_pkg = ExportService.generate_scan_context(db, requested_mode="DEEP_FULL_SCAN")
        scan_id_1 = context_pkg.scan.scan_id
        assert context_pkg.protocol_version == "0.1"
        assert context_pkg.benefit_schema_version == "1.2.1"
        assert context_pkg.package_type == "SCAN_CONTEXT"
        assert context_pkg.scan.baseline_revision == 0
        assert context_pkg.scan.baseline_state == "EMPTY"
        assert len(context_pkg.benefit_index) == 0

        # 3. DEEP_FULL_SCAN Import with BUILD_INITIAL_BASELINE
        import_data = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id_1,
                "scan_mode": "DEEP_FULL_SCAN",
                "context_baseline_revision": 0,
                "generated_at": "2026-08-18T18:25:00+08:00",
                "scan_statuses": ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"],
                "baseline_action": "BUILD_INITIAL_BASELINE",
                "summary_notes": "Lifecycle A initial baseline build"
            },
            "benefit_changes": [
                {
                    "operation": "CREATE",
                    "local_ref": "BNEW-001",
                    "record": {
                        "benefit_id": None,
                        "vendor": "TRAE",
                        "product": "TRAE CN",
                        "campaign_name": "Daily Checkin Bonus",
                        "benefit_type": "CHECKIN",
                        "benefit_detail": "每日签到获得专属积分",
                        "wallet": "通用积分",
                        "amount": "100",
                        "unit": "POINTS",
                        "reset_policy": "DAILY",
                        "grant_method": "CHECKIN",
                        "regions": ["CN"],
                        "eligibility": "所有注册用户",
                        "eligibility_class": ["ALL_USERS"],
                        "first_seen": "2026-08-18",
                        "last_checked": "2026-08-18",
                        "official_source": "https://trae.cn",
                        "source_level": "S",
                        "verification_status": "CONFIRMED",
                        "status": "ACTIVE",
                        "change_type": "UNKNOWN"
                    },
                    "evidence": [
                        {
                            "url": "https://trae.cn/activity",
                            "source_level": "S",
                            "source_role": "PRIMARY",
                            "checked_at": "2026-08-18T17:20:00+08:00",
                            "supports_fields": ["benefit_detail", "status"]
                        }
                    ]
                }
            ],
            "lead_changes": [
                {
                    "operation": "CREATE",
                    "local_ref": "LNEW-001",
                    "record": {
                        "vendor": "Anthropic",
                        "product": "Claude Code",
                        "lead_summary": "新用户赠送 20 美金 API Credits",
                        "verification_status": "LIKELY",
                        "source_level": "B",
                        "regions": ["GLOBAL"],
                        "first_seen": "2026-08-18",
                        "last_checked": "2026-08-18",
                        "status": "OPEN"
                    },
                    "evidence": []
                }
            ],
            "coverage_events": [
                {
                    "vendor": "TRAE",
                    "product": "TRAE CN",
                    "surface": "Client Reward",
                    "region": "CN",
                    "coverage_state": "CHECKED_FOUND",
                    "scan_observed_at": "2026-08-18T18:25:00+08:00",
                    "actual_checked_at": "2026-08-18T18:25:00+08:00",
                    "next_review_at": "2099-01-01"
                }
            ],
            "source_updates": [
                {
                    "operation": "ADD",
                    "local_ref": "SNEW-001",
                    "record": {
                        "vendor": "TRAE",
                        "product": "TRAE CN",
                        "surface": "Client Reward",
                        "source_name": "TRAE 活动中心",
                        "url": "https://trae.cn/activity",
                        "source_type": "ACTIVITY_CENTER",
                        "source_level": "S",
                        "status": "ACTIVE",
                        "last_verified_at": "2026-08-18T18:25:00+08:00"
                    }
                }
            ],
            "manual_check_items": [
                {
                    "local_ref": "MNEW-001",
                    "vendor": "TRAE",
                    "product": "TRAE IDE",
                    "channel": "IDE",
                    "reason": "检查 IDE 弹窗中是否存在限时积分领取入口",
                    "priority": "MEDIUM",
                    "suggested_action": "打开 IDE 登录查看活动弹窗",
                    "status": "OPEN"
                }
            ],
            "warnings": []
        }
        raw_import_json = dumps_json(import_data)

        # 4. Preview & Validate
        preview = ImportService.parse_and_preview(db, raw_import_json)
        assert preview["is_valid"] is True
        assert preview["preview"]["benefit_create_count"] == 1
        assert preview["preview"]["lead_create_count"] == 1
        assert preview["preview"]["source_add_count"] == 1
        assert preview["preview"]["coverage_recheck_count"] == 1
        assert preview["preview"]["manual_check_count"] == 1

        # 5. Commit
        commit_res = ImportService.commit_import(db, preview["import_pkg"], raw_import_json)
        assert commit_res["success"] is True

        # 6. Verify State = READY, rev = 1
        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        assert sys_state.baseline_state == "READY"
        assert sys_state.baseline_revision == 1

        # 7. Export Context & Verify entries
        context_pkg_2 = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        assert context_pkg_2.scan.baseline_revision == 1
        assert context_pkg_2.scan.baseline_state == "READY"
        assert len(context_pkg_2.benefit_index) == 1
        assert len(context_pkg_2.open_leads) == 1
        assert len(context_pkg_2.canonical_sources) == 1

        # 8. Same scan_id rejected
        prev_dup = ImportService.parse_and_preview(db, raw_import_json)
        assert prev_dup["is_valid"] is False
        assert any("该扫描已经导入" in err for err in prev_dup["errors"])

    finally:
        db.close()


# =========================================================================
# LIFECYCLE B — Normal FULL_SCAN Update Lifecycle
# =========================================================================
def test_lifecycle_b_normal_full_scan_update():
    """
    READY
    -> Export FULL_SCAN Context
    -> existing Benefit UPDATE
    -> merged Benefit validation
    -> Lead UPDATE
    -> Source UPDATE
    -> valid REVIEW_NOT_DUE
    -> Preview
    -> Commit
    -> revision + 1
    -> Export next Context
    Negative checks:
    - Benefit status BANANA -> FAIL
    - Lead CONFIRMED -> FAIL
    - Source level Z -> FAIL
    - Fake permanent IDs -> FAIL
    - next_review_at UNKNOWN REVIEW_NOT_DUE -> FAIL
    """
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(bind=test_engine)
    Session = sessionmaker(bind=test_engine)
    db = Session()

    try:
        # Pre-seed READY database
        b_init = BenefitModel(
            benefit_id="BEN-000001",
            vendor="TRAE",
            product="TRAE CN",
            campaign_name="Daily Checkin",
            benefit_type="CHECKIN",
            benefit_detail="100 pts",
            first_seen="2026-08-01",
            last_checked="2026-08-01",
            official_source="https://trae.cn",
            source_level="S",
            verification_status="CONFIRMED",
            status="ACTIVE",
            end_date="2099-01-01",
            next_review_date="2099-01-01"
        )
        b_init.regions = ["CN"]
        b_init.eligibility_class = ["ALL_USERS"]

        l_init = LeadModel(
            lead_id="LEAD-000001",
            vendor="Anthropic",
            product="Claude Code",
            lead_summary="20 USD Promo",
            verification_status="UNVERIFIED",
            source_level="B",
            first_seen="2026-08-01",
            last_checked="2026-08-01",
            status="OPEN"
        )
        l_init.regions = ["GLOBAL"]

        s_init = CanonicalSourceModel(
            source_id="SRC-000001",
            vendor="TRAE",
            product="TRAE CN",
            surface="Client Reward",
            source_name="TRAE Activity",
            url="https://trae.cn/activity",
            source_type="ACTIVITY_CENTER",
            source_level="S",
            status="ACTIVE",
            last_verified_at="2026-08-01T10:00:00+08:00"
        )

        cov_init = CoverageHistoryModel(
            coverage_id="COV-000001",
            scan_id="SCAN-INIT",
            vendor="TRAE",
            product="TRAE CN",
            surface="Client Reward",
            region="CN",
            coverage_state="CHECKED_FOUND",
            scan_observed_at="2026-08-01T10:00:00+08:00",
            actual_checked_at="2026-08-01T10:00:00+08:00",
            next_review_at="2099-01-01"
        )

        cov_init_unk = CoverageHistoryModel(
            coverage_id="COV-000002",
            scan_id="SCAN-INIT",
            vendor="OpenAI",
            product="ChatGPT",
            surface="Pricing",
            region="GLOBAL",
            coverage_state="CHECKED_NONE",
            scan_observed_at="2026-08-01T10:00:00+08:00",
            actual_checked_at="2026-08-01T10:00:00+08:00",
            next_review_at="UNKNOWN"
        )

        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        sys_state.baseline_state = "READY"
        sys_state.baseline_revision = 1

        db.add_all([b_init, l_init, s_init, cov_init, cov_init_unk])
        db.commit()

        # 1. Export FULL_SCAN Context
        context_pkg = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        scan_id = context_pkg.scan.scan_id
        assert context_pkg.scan.baseline_revision == 1
        assert context_pkg.scan.baseline_state == "READY"

        # 2. Valid Normal Update Import
        valid_update_data = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id,
                "scan_mode": "FULL_SCAN",
                "context_baseline_revision": 1,
                "generated_at": "2026-08-18T19:00:00+08:00",
                "scan_statuses": ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"],
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "summary_notes": "Lifecycle B valid update"
            },
            "benefit_changes": [
                {
                    "operation": "UPDATE",
                    "benefit_id": "BEN-000001",
                    "change_type": "STATUS_CHANGED",
                    "patch": {
                        "status": "EXPIRING_SOON",
                        "end_date": "2026-08-31"
                    }
                }
            ],
            "lead_changes": [
                {
                    "operation": "UPDATE",
                    "lead_id": "LEAD-000001",
                    "patch": {
                        "verification_status": "DISPUTED",
                        "lead_summary": "Updated disputed summary"
                    }
                }
            ],
            "coverage_events": [
                {
                    "vendor": "TRAE",
                    "product": "TRAE CN",
                    "surface": "Client Reward",
                    "region": "CN",
                    "coverage_state": "REVIEW_NOT_DUE",
                    "basis_coverage_id": "COV-000001",
                    "scan_observed_at": "2026-08-18T19:00:00+08:00",
                    "actual_checked_at": "2026-08-01T10:00:00+08:00"
                }
            ],
            "source_updates": [
                {
                    "operation": "UPDATE",
                    "source_id": "SRC-000001",
                    "patch": {
                        "last_verified_at": "2026-08-18T19:00:00+08:00"
                    }
                }
            ],
            "manual_check_items": [],
            "warnings": []
        }
        raw_update_json = dumps_json(valid_update_data)

        # 3. Preview & Validate
        prev = ImportService.parse_and_preview(db, raw_update_json)
        assert prev["is_valid"] is True
        assert prev["preview"]["benefit_update_count"] == 1
        assert prev["preview"]["lead_update_count"] == 1
        assert prev["preview"]["source_update_count"] == 1
        assert prev["preview"]["coverage_review_not_due_count"] == 1

        # 4. Commit
        commit_res = ImportService.commit_import(db, prev["import_pkg"], raw_update_json)
        assert commit_res["success"] is True

        # 5. Check DB & Revision
        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        assert sys_state.baseline_revision == 2

        b_check = db.query(BenefitModel).filter_by(benefit_id="BEN-000001").first()
        assert b_check.status == "EXPIRING_SOON"
        assert b_check.end_date == "2026-08-31"
        assert b_check.campaign_name == "Daily Checkin"

        l_check = db.query(LeadModel).filter_by(lead_id="LEAD-000001").first()
        assert l_check.verification_status == "DISPUTED"

        s_check = db.query(CanonicalSourceModel).filter_by(source_id="SRC-000001").first()
        assert s_check.last_verified_at == "2026-08-18T19:00:00+08:00"

        # 6. Negative Gate Validations:

        # Negative 1: Benefit status BANANA -> FAIL
        context_pkg_neg = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        scan_id_neg = context_pkg_neg.scan.scan_id

        data_neg_b = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id_neg,
                "scan_mode": "FULL_SCAN",
                "context_baseline_revision": 2,
                "generated_at": "2026-08-18T19:30:00+08:00",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "summary_notes": "Neg test"
            },
            "benefit_changes": [{
                "operation": "UPDATE",
                "benefit_id": "BEN-000001",
                "patch": {"status": "BANANA"}
            }],
            "lead_changes": [],
            "coverage_events": [],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        prev_neg_b = ImportService.parse_and_preview(db, dumps_json(data_neg_b))
        assert prev_neg_b["is_valid"] is False

        # Negative 2: Lead CONFIRMED -> FAIL
        data_neg_l = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id_neg,
                "scan_mode": "FULL_SCAN",
                "context_baseline_revision": 2,
                "generated_at": "2026-08-18T19:30:00+08:00",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "summary_notes": "Neg test"
            },
            "benefit_changes": [],
            "lead_changes": [{
                "operation": "UPDATE",
                "lead_id": "LEAD-000001",
                "patch": {"verification_status": "CONFIRMED"}
            }],
            "coverage_events": [],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        prev_neg_l = ImportService.parse_and_preview(db, dumps_json(data_neg_l))
        assert prev_neg_l["is_valid"] is False

        # Negative 3: Source level Z -> FAIL
        data_neg_s = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id_neg,
                "scan_mode": "FULL_SCAN",
                "context_baseline_revision": 2,
                "generated_at": "2026-08-18T19:30:00+08:00",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "summary_notes": "Neg test"
            },
            "benefit_changes": [],
            "lead_changes": [],
            "coverage_events": [],
            "source_updates": [{
                "operation": "UPDATE",
                "source_id": "SRC-000001",
                "patch": {"source_level": "Z"}
            }],
            "manual_check_items": [],
            "warnings": []
        }
        prev_neg_s = ImportService.parse_and_preview(db, dumps_json(data_neg_s))
        assert prev_neg_s["is_valid"] is False

        # Negative 4: Fake permanent ID on new Lead / Source / Coverage -> FAIL
        data_neg_id = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id_neg,
                "scan_mode": "FULL_SCAN",
                "context_baseline_revision": 2,
                "generated_at": "2026-08-18T19:30:00+08:00",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "summary_notes": "Neg test"
            },
            "benefit_changes": [],
            "lead_changes": [{
                "operation": "CREATE",
                "local_ref": "LNEW-002",
                "record": {
                    "lead_id": "LEAD-999999",
                    "vendor": "Meta",
                    "product": "Llama",
                    "lead_summary": "Fake id lead",
                    "verification_status": "LIKELY",
                    "source_level": "A",
                    "first_seen": "2026-08-18",
                    "last_checked": "2026-08-18",
                    "status": "OPEN"
                }
            }],
            "coverage_events": [{
                "coverage_id": "COV-999999",
                "vendor": "Meta",
                "product": "Llama",
                "surface": "API",
                "region": "GLOBAL",
                "coverage_state": "CHECKED_NONE",
                "scan_observed_at": "2026-08-18T19:30:00+08:00",
                "actual_checked_at": "2026-08-18T19:30:00+08:00"
            }],
            "source_updates": [{
                "operation": "ADD",
                "local_ref": "SNEW-002",
                "record": {
                    "source_id": "SRC-999999",
                    "vendor": "Meta",
                    "product": "Llama",
                    "surface": "API",
                    "source_name": "Meta API",
                    "url": "https://meta.com",
                    "source_type": "OFFICIAL_PAGE",
                    "source_level": "S",
                    "status": "ACTIVE"
                }
            }],
            "manual_check_items": [],
            "warnings": []
        }
        prev_neg_id = ImportService.parse_and_preview(db, dumps_json(data_neg_id))
        assert prev_neg_id["is_valid"] is False

        # Negative 5: next_review_at UNKNOWN + REVIEW_NOT_DUE -> FAIL
        data_neg_cov = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id_neg,
                "scan_mode": "FULL_SCAN",
                "context_baseline_revision": 2,
                "generated_at": "2026-08-18T19:30:00+08:00",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "summary_notes": "Neg test"
            },
            "benefit_changes": [],
            "lead_changes": [],
            "coverage_events": [{
                "vendor": "OpenAI",
                "product": "ChatGPT",
                "surface": "Pricing",
                "region": "GLOBAL",
                "coverage_state": "REVIEW_NOT_DUE",
                "basis_coverage_id": "COV-000002",
                "scan_observed_at": "2026-08-18T19:30:00+08:00",
                "actual_checked_at": "2026-08-01T10:00:00+08:00"
            }],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        prev_neg_cov = ImportService.parse_and_preview(db, dumps_json(data_neg_cov))
        assert prev_neg_cov["is_valid"] is False
        assert any("缺少明确的 next_review_at" in e for e in prev_neg_cov["errors"])

    finally:
        db.close()


