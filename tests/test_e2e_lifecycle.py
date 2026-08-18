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
from ai_benefit_desk.config import PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION
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
                    "vendor": "Anthropic",
                    "product": "Claude Code",
                    "lead_summary": "新用户赠送 20 美金 API Credits",
                    "verification_status": "LIKELY",
                    "source_level": "B",
                    "regions": ["GLOBAL"],
                    "first_seen": "2026-08-18",
                    "last_checked": "2026-08-18",
                    "status": "OPEN",
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
                "lead_id": "LEAD-999999",
                "vendor": "Meta",
                "product": "Llama",
                "lead_summary": "Fake id lead",
                "verification_status": "LIKELY",
                "source_level": "A",
                "first_seen": "2026-08-18",
                "last_checked": "2026-08-18",
                "status": "OPEN"
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
                "source_id": "SRC-999999",
                "vendor": "Meta",
                "product": "Llama",
                "surface": "API",
                "source_name": "Meta API",
                "url": "https://meta.com",
                "source_type": "OFFICIAL_PAGE",
                "source_level": "S",
                "status": "ACTIVE"
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


# =========================================================================
# LIFECYCLE C — Dedup Resolution Lifecycle
# =========================================================================
def test_lifecycle_c_dedup_resolution():
    """
    READY Baseline
    -> existing Benefit BEN-000001
    -> Export Context
    -> Scan Import CREATE BNEW-X
    -> Detect duplicate BEN-000001
    -> Preview
    -> User chooses UPDATE_EXISTING
    -> Commit
    -> Benefit count unchanged
    -> BEN-000001 fact updated
    -> first_seen preserved
    -> User State preserved
    -> local_ref BNEW-X maps BEN-000001
    -> next Context export
    -> PASS
    """
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(bind=test_engine)
    Session = sessionmaker(bind=test_engine)
    db = Session()

    try:
        # Pre-seed READY DB
        b_init = BenefitModel(
            benefit_id="BEN-000001",
            vendor="Vendor A",
            product="Product A",
            campaign_name="Vendor A Deal",
            benefit_type="API_CREDITS",
            benefit_detail="Initial detail 1000",
            amount="1000",
            end_date="2026-08-31",
            first_seen="2026-07-01",
            last_checked="2026-07-01",
            official_source="https://vendor-a.com",
            source_level="S",
            verification_status="CONFIRMED",
            status="ACTIVE"
        )
        b_init.regions = ["US"]
        b_init.eligibility_class = ["ALL_USERS"]

        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        sys_state.baseline_state = "READY"
        sys_state.baseline_revision = 1

        db.add(b_init)
        db.commit()

        # User Benefit State: CLAIMED
        u_state = UserBenefitStateModel(benefit_id="BEN-000001", action_state="CLAIMED", notes="Claimed by user")
        db.add(u_state)
        db.commit()

        # 1. Export Context
        context_pkg = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        scan_id = context_pkg.scan.scan_id
        assert context_pkg.scan.baseline_revision == 1

        # 2. Scan Import with CREATE candidate BNEW-X matching BEN-000001
        import_data = {
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
                "summary_notes": "Lifecycle C Dedup"
            },
            "benefit_changes": [
                {
                    "operation": "CREATE",
                    "local_ref": "BNEW-X",
                    "record": {
                        "vendor": "Vendor A",
                        "product": "Product A",
                        "campaign_name": "Vendor A Deal",
                        "benefit_type": "API_CREDITS",
                        "benefit_detail": "Updated detail 2000",
                        "amount": 2000,
                        "end_date": "2026-10-31",
                        "first_seen": "2026-08-18",
                        "last_checked": "2026-08-18",
                        "official_source": "https://vendor-a.com",
                        "source_level": "S",
                        "verification_status": "CONFIRMED",
                        "status": "ACTIVE"
                    },
                    "evidence": [
                        {
                            "url": "https://vendor-a.com",
                            "source_level": "S",
                            "source_role": "PRIMARY",
                            "checked_at": "2026-08-18T18:00:00+08:00"
                        }
                    ]
                }
            ],
            "lead_changes": [],
            "coverage_events": [],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        raw_json = dumps_json(import_data)

        # 3. Preview detects duplicate
        preview = ImportService.parse_and_preview(db, raw_json)
        assert preview["is_valid"] is True
        dups = preview["preview"]["duplicates"]
        assert len(dups) == 1
        assert dups[0]["existing_benefit_id"] == "BEN-000001"

        # 4. User chooses UPDATE:BEN-000001
        resolutions = {"BNEW-X": "UPDATE:BEN-000001"}
        commit_res = ImportService.commit_import(
            db, preview["import_pkg"], raw_json, dedup_resolutions=resolutions
        )
        assert commit_res["success"] is True

        # 5. Check assertions
        # Total benefit count unchanged
        assert db.query(BenefitModel).count() == 1

        b_chk = db.query(BenefitModel).filter_by(benefit_id="BEN-000001").first()
        assert b_chk.amount == "2000"
        assert b_chk.end_date == "2026-10-31"
        assert b_chk.first_seen == "2026-07-01"

        # User Benefit State preserved
        u_chk = db.query(UserBenefitStateModel).filter_by(benefit_id="BEN-000001").first()
        assert u_chk.action_state == "CLAIMED"

        # local_ref maps to BEN-000001
        assert commit_res["local_ref_map"]["BNEW-X"] == "BEN-000001"

        # 6. Next context export contains updated facts
        context_pkg_2 = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        assert context_pkg_2.scan.baseline_revision == 2
        assert len(context_pkg_2.benefit_index) == 1
        assert context_pkg_2.benefit_index[0].benefit_id == "BEN-000001"

    finally:
        db.close()


# =========================================================================
# LIFECYCLE D — Initial Baseline Package Dedup
# =========================================================================
def test_lifecycle_d_initial_baseline_package_dedup():
    """
    EMPTY
    -> Export Context
    -> DEEP_FULL_SCAN Import
    -> two duplicate CREATE candidates
    -> Preview detects duplicate
    -> user merge
    -> Commit
    -> one permanent Benefit
    -> both local_refs resolve same benefit_id
    -> READY
    -> Export Context
    -> no duplicate Benefit identity
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

        # 2. Export Context
        context_pkg = ExportService.generate_scan_context(db, requested_mode="DEEP_FULL_SCAN")
        scan_id = context_pkg.scan.scan_id

        # 3. DEEP_FULL_SCAN Import with 2 duplicate CREATE candidates
        import_data = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id,
                "scan_mode": "DEEP_FULL_SCAN",
                "context_baseline_revision": 0,
                "generated_at": "2026-08-18T18:00:00+08:00",
                "scan_statuses": ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"],
                "baseline_action": "BUILD_INITIAL_BASELINE",
                "summary_notes": "Lifecycle D Initial Package Dedup"
            },
            "benefit_changes": [
                {
                    "operation": "CREATE",
                    "local_ref": "BNEW-001",
                    "record": {
                        "vendor": "Vendor X",
                        "product": "Product X",
                        "campaign_name": "Campaign X",
                        "benefit_type": "FREE_ACCESS",
                        "benefit_detail": "Official EN page",
                        "amount": 1000,
                        "first_seen": "2026-08-18",
                        "last_checked": "2026-08-18",
                        "official_source": "https://vendor-x.com/en",
                        "source_level": "S",
                        "verification_status": "CONFIRMED",
                        "status": "ACTIVE"
                    },
                    "evidence": [
                        {
                            "url": "https://vendor-x.com/en",
                            "source_level": "S",
                            "source_role": "PRIMARY",
                            "checked_at": "2026-08-18T18:00:00+08:00"
                        }
                    ]
                },
                {
                    "operation": "CREATE",
                    "local_ref": "BNEW-002",
                    "record": {
                        "vendor": "Vendor X",
                        "product": "Product X",
                        "campaign_name": "Campaign X",
                        "benefit_type": "FREE_ACCESS",
                        "benefit_detail": "Official CN page",
                        "amount": 1000,
                        "first_seen": "2026-08-18",
                        "last_checked": "2026-08-18",
                        "official_source": "https://vendor-x.com/cn",
                        "source_level": "S",
                        "verification_status": "CONFIRMED",
                        "status": "ACTIVE"
                    },
                    "evidence": [
                        {
                            "url": "https://vendor-x.com/cn",
                            "source_level": "S",
                            "source_role": "PRIMARY",
                            "checked_at": "2026-08-18T18:00:00+08:00"
                        }
                    ]
                }
            ],
            "lead_changes": [],
            "coverage_events": [],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        raw_json = dumps_json(import_data)

        # 4. Preview & detect intra-package duplicate
        preview = ImportService.parse_and_preview(db, raw_json)
        assert preview["is_valid"] is True
        dups = preview["preview"]["duplicates"]
        assert len(dups) == 1
        assert dups[0]["is_intra_package"] is True
        assert dups[0]["local_ref"] == "BNEW-002"
        assert dups[0]["target_local_ref"] == "BNEW-001"

        # 5. User chooses MERGE_LOCAL:BNEW-001
        resolutions = {"BNEW-002": "MERGE_LOCAL:BNEW-001"}
        commit_res = ImportService.commit_import(
            db, preview["import_pkg"], raw_json, dedup_resolutions=resolutions
        )
        assert commit_res["success"] is True

        # 6. Verify single permanent Benefit created
        assert db.query(BenefitModel).count() == 1
        b_rec = db.query(BenefitModel).first()
        assert b_rec is not None

        # Both local_refs resolve to the same benefit_id
        assert commit_res["local_ref_map"]["BNEW-001"] == b_rec.benefit_id
        assert commit_res["local_ref_map"]["BNEW-002"] == b_rec.benefit_id

        # 7. State = READY, rev = 1
        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        assert sys_state.baseline_state == "READY"
        assert sys_state.baseline_revision == 1

        # 8. Next Export Context has only 1 benefit identity
        context_pkg_2 = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        assert len(context_pkg_2.benefit_index) == 1
        assert context_pkg_2.benefit_index[0].benefit_id == b_rec.benefit_id

    finally:
        db.close()


# =========================================================================
# LIFECYCLE E — Validation Integrity Lifecycle
# =========================================================================
def test_lifecycle_e_validation_integrity():
    """
    Validation Integrity Lifecycle:
    - Pre-seed READY state with 1 Benefit, 1 Lead, 1 Canonical Source (rev=1).
    - Export Scan Context.
    - Negative validation gates:
      1. Benefit UPDATE status = "BANANA" -> FAIL
      2. Lead CREATE verification_status = "CONFIRMED" -> FAIL
      3. Lead UPDATE verification_status = "CONFIRMED" -> FAIL
      4. Source UPDATE source_level = "Z" -> FAIL
      5. Benefit CREATE amount = "many credits" -> FAIL
      6. Conflicting intra-package duplicate commit without resolution -> FAIL
    - Positive update:
      - Benefit UPDATE (amount=2000 as int, status="ENDED", end_date="2026-08-31")
      - Lead UPDATE (lead_summary="Updated Lead summary", verification_status="DISPUTED")
      - Source UPDATE (last_verified_at="2026-08-18T23:00:00+08:00", source_name="Updated Canonical API")
      - Coverage CHECKED_FOUND
    - Commit -> baseline_revision = 2.
    - Export next Scan Context -> SUCCESS with rev=2 and valid data.
    """
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(bind=test_engine)
    Session = sessionmaker(bind=test_engine)
    db = Session()

    try:
        # Pre-seed READY database
        b_init = BenefitModel(
            benefit_id="BEN-000001",
            vendor="VendorE",
            product="ProductE",
            campaign_name="Campaign E",
            benefit_type="API_CREDITS",
            benefit_detail="1000 Credits",
            amount="1000",
            unit="USD",
            wallet="MAIN",
            reset_policy="NONE",
            grant_method="CLAIM",
            eligibility="All",
            first_seen="2026-08-01",
            last_checked="2026-08-01",
            official_source="https://vendore.com",
            source_level="S",
            verification_status="CONFIRMED",
            status="ACTIVE"
        )
        b_init.regions = ["GLOBAL"]
        b_init.eligibility_class = ["ALL_USERS"]
        db.add(b_init)

        l_init = LeadModel(
            lead_id="LEAD-000001",
            vendor="VendorE",
            product="ProductE",
            lead_summary="Lead E summary",
            verification_status="UNVERIFIED",
            source_level="B",
            first_seen="2026-08-01",
            last_checked="2026-08-01",
            status="OPEN"
        )
        l_init.regions = ["GLOBAL"]
        db.add(l_init)

        s_init = CanonicalSourceModel(
            source_id="SRC-000001",
            vendor="VendorE",
            product="ProductE",
            surface="API",
            source_name="Vendor E API Page",
            url="https://vendore.com/api",
            source_type="OFFICIAL_PAGE",
            source_level="S",
            status="ACTIVE",
            last_verified_at="2026-08-18T18:00:00+08:00"
        )
        db.add(s_init)

        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        sys_state.baseline_state = "READY"
        sys_state.baseline_revision = 1
        db.commit()

        # 1. Export Scan Context
        context_pkg = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        scan_id = context_pkg.scan.scan_id
        assert context_pkg.scan.baseline_revision == 1

        # 2. Negative Validation Gate 1: Benefit UPDATE status = "BANANA"
        neg1 = {
            "protocol_version": PROTOCOL_VERSION,
            "benefit_schema_version": BENEFIT_SCHEMA_VERSION,
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id,
                "generated_at": "2026-08-18T18:00:00+08:00",
                "context_baseline_revision": 1,
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "scan_mode": "FULL_SCAN",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "summary_notes": "Neg 1"
            },
            "benefit_changes": [
                {
                    "operation": "UPDATE",
                    "benefit_id": "BEN-000001",
                    "patch": {"status": "BANANA"}
                }
            ],
            "lead_changes": [],
            "coverage_events": [],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        assert ImportService.parse_and_preview(db, dumps_json(neg1))["is_valid"] is False

        # 3. Negative Validation Gate 2: Lead CREATE verification_status = "CONFIRMED"
        neg2 = {
            "protocol_version": PROTOCOL_VERSION,
            "benefit_schema_version": BENEFIT_SCHEMA_VERSION,
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id,
                "generated_at": "2026-08-18T18:00:00+08:00",
                "context_baseline_revision": 1,
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "scan_mode": "FULL_SCAN",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "summary_notes": "Neg 2"
            },
            "benefit_changes": [],
            "lead_changes": [
                {
                    "operation": "CREATE",
                    "local_ref": "LNEW-NEG2",
                    "vendor": "VendorE",
                    "product": "ProductE",
                    "lead_summary": "Confirmed lead forbidden",
                    "verification_status": "CONFIRMED",
                    "source_level": "S",
                    "first_seen": "2026-08-18",
                    "last_checked": "2026-08-18",
                    "status": "OPEN"
                }
            ],
            "coverage_events": [],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        assert ImportService.parse_and_preview(db, dumps_json(neg2))["is_valid"] is False

        # 4. Negative Validation Gate 3: Lead UPDATE verification_status = "CONFIRMED"
        neg3 = {
            "protocol_version": PROTOCOL_VERSION,
            "benefit_schema_version": BENEFIT_SCHEMA_VERSION,
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id,
                "generated_at": "2026-08-18T18:00:00+08:00",
                "context_baseline_revision": 1,
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "scan_mode": "FULL_SCAN",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "summary_notes": "Neg 3"
            },
            "benefit_changes": [],
            "lead_changes": [
                {
                    "operation": "UPDATE",
                    "lead_id": "LEAD-000001",
                    "patch": {"verification_status": "CONFIRMED"}
                }
            ],
            "coverage_events": [],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        assert ImportService.parse_and_preview(db, dumps_json(neg3))["is_valid"] is False

        # 5. Negative Validation Gate 4: Source UPDATE source_level = "Z"
        neg4 = {
            "protocol_version": PROTOCOL_VERSION,
            "benefit_schema_version": BENEFIT_SCHEMA_VERSION,
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id,
                "generated_at": "2026-08-18T18:00:00+08:00",
                "context_baseline_revision": 1,
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "scan_mode": "FULL_SCAN",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "summary_notes": "Neg 4"
            },
            "benefit_changes": [],
            "lead_changes": [],
            "coverage_events": [],
            "source_updates": [
                {
                    "operation": "UPDATE",
                    "source_id": "SRC-000001",
                    "patch": {"source_level": "Z"}
                }
            ],
            "manual_check_items": [],
            "warnings": []
        }
        assert ImportService.parse_and_preview(db, dumps_json(neg4))["is_valid"] is False

        # 6. Negative Validation Gate 5: Benefit CREATE amount = "many credits"
        neg5 = {
            "protocol_version": PROTOCOL_VERSION,
            "benefit_schema_version": BENEFIT_SCHEMA_VERSION,
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id,
                "generated_at": "2026-08-18T18:00:00+08:00",
                "context_baseline_revision": 1,
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "scan_mode": "FULL_SCAN",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "summary_notes": "Neg 5"
            },
            "benefit_changes": [
                {
                    "operation": "CREATE",
                    "local_ref": "BNEW-NEG5",
                    "record": {
                        "vendor": "VendorE",
                        "product": "ProductE",
                        "campaign_name": "Invalid Amount Campaign",
                        "benefit_type": "API_CREDITS",
                        "benefit_detail": "Details",
                        "amount": "many credits",
                        "unit": "USD",
                        "wallet": "MAIN",
                        "reset_policy": "NONE",
                        "grant_method": "CLAIM",
                        "eligibility": "All",
                        "eligibility_class": ["ALL_USERS"],
                        "first_seen": "2026-08-18",
                        "last_checked": "2026-08-18",
                        "official_source": "https://vendore.com",
                        "source_level": "S",
                        "verification_status": "CONFIRMED",
                        "status": "ACTIVE"
                    }
                }
            ],
            "lead_changes": [],
            "coverage_events": [],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        assert ImportService.parse_and_preview(db, dumps_json(neg5))["is_valid"] is False


        # 7. Negative Validation Gate 6: Unresolved conflicting duplicate commit
        neg6 = {
            "protocol_version": PROTOCOL_VERSION,
            "benefit_schema_version": BENEFIT_SCHEMA_VERSION,
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id,
                "generated_at": "2026-08-18T18:00:00+08:00",
                "context_baseline_revision": 1,
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "scan_mode": "FULL_SCAN",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "summary_notes": "Neg 6"
            },
            "benefit_changes": [
                {
                    "operation": "CREATE",
                    "local_ref": "BNEW-001",
                    "record": {
                        "vendor": "VendorDup",
                        "product": "ProductDup",
                        "campaign_name": "Dup Campaign",
                        "benefit_type": "API_CREDITS",
                        "benefit_detail": "Detail 1",
                        "amount": 100,
                        "unit": "USD",
                        "wallet": "MAIN",
                        "reset_policy": "NONE",
                        "grant_method": "CLAIM",
                        "eligibility": "All",
                        "eligibility_class": ["ALL_USERS"],
                        "first_seen": "2026-08-18",
                        "last_checked": "2026-08-18",
                        "official_source": "https://dup.com/1",
                        "source_level": "S",
                        "verification_status": "CONFIRMED",
                        "status": "ACTIVE"
                    }
                },
                {
                    "operation": "CREATE",
                    "local_ref": "BNEW-002",
                    "record": {
                        "vendor": "VendorDup",
                        "product": "ProductDup",
                        "campaign_name": "Dup Campaign",
                        "benefit_type": "API_CREDITS",
                        "benefit_detail": "Detail 2",
                        "amount": 200,
                        "unit": "USD",
                        "wallet": "MAIN",
                        "reset_policy": "NONE",
                        "grant_method": "CLAIM",
                        "eligibility": "All",
                        "eligibility_class": ["ALL_USERS"],
                        "first_seen": "2026-08-18",
                        "last_checked": "2026-08-18",
                        "official_source": "https://dup.com/2",
                        "source_level": "S",
                        "verification_status": "CONFIRMED",
                        "status": "ACTIVE"
                    }
                }
            ],
            "lead_changes": [],
            "coverage_events": [],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        with pytest.raises(ValueError, match="存在尚未处理的冲突福利"):
            ImportService.commit_import(db, dumps_json(neg6), dedup_resolutions={})

        # 8. Positive Validation & Commit
        pos_pkg = {
            "protocol_version": PROTOCOL_VERSION,
            "benefit_schema_version": BENEFIT_SCHEMA_VERSION,
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id,
                "generated_at": "2026-08-18T18:00:00+08:00",
                "context_baseline_revision": 1,
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "scan_mode": "FULL_SCAN",
                "scan_statuses": ["PUBLIC_COMPLETE"],
                "summary_notes": "Positive Update Lifecycle"
            },
            "benefit_changes": [
                {
                    "operation": "UPDATE",
                    "benefit_id": "BEN-000001",
                    "patch": {
                        "amount": 2000,
                        "status": "ENDED",
                        "end_date": "2026-08-31"
                    }
                }
            ],
            "lead_changes": [
                {
                    "operation": "UPDATE",
                    "lead_id": "LEAD-000001",
                    "patch": {
                        "lead_summary": "Updated Lead summary",
                        "verification_status": "DISPUTED"
                    }
                }
            ],
            "coverage_events": [
                {
                    "vendor": "VendorE",
                    "product": "ProductE",
                    "wallet": "MAIN",
                    "surface": "API",
                    "region": "GLOBAL",
                    "coverage_state": "CHECKED_FOUND",
                    "scan_observed_at": "2026-08-18T18:00:00+08:00",
                    "actual_checked_at": "2026-08-18T18:00:00+08:00",
                    "next_review_at": "2026-09-18"
                }
            ],
            "source_updates": [
                {
                    "operation": "UPDATE",
                    "source_id": "SRC-000001",
                    "patch": {
                        "source_name": "Updated Canonical API",
                        "last_verified_at": "2026-08-18T23:00:00+08:00"
                    }
                }
            ],
            "manual_check_items": [],
            "warnings": []
        }
        pos_raw = dumps_json(pos_pkg)
        prev_pos = ImportService.parse_and_preview(db, pos_raw)
        assert prev_pos["is_valid"] is True

        commit_res = ImportService.commit_import(db, prev_pos["import_pkg"], pos_raw)
        assert commit_res["success"] is True


        # 9. Verify Database Records
        b_db = db.query(BenefitModel).filter_by(benefit_id="BEN-000001").first()
        assert b_db.amount == "2000"
        assert b_db.status == "ENDED"
        assert b_db.end_date == "2026-08-31"

        l_db = db.query(LeadModel).filter_by(lead_id="LEAD-000001").first()
        assert l_db.lead_summary == "Updated Lead summary"
        assert l_db.verification_status == "DISPUTED"

        s_db = db.query(CanonicalSourceModel).filter_by(source_id="SRC-000001").first()
        assert s_db.source_name == "Updated Canonical API"
        assert s_db.last_verified_at == "2026-08-18T23:00:00+08:00"

        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        assert sys_state.baseline_revision == 2

        # 10. Next Export Scan Context has rev 2 and valid records
        next_ctx = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        assert next_ctx.scan.baseline_revision == 2
        assert len(next_ctx.benefit_index) == 1
        assert next_ctx.benefit_index[0].status == "ENDED"
        assert next_ctx.benefit_index[0].end_date == "2026-08-31"
        assert len(next_ctx.open_leads) == 1
        assert next_ctx.open_leads[0].verification_status == "DISPUTED"
        assert len(next_ctx.canonical_sources) == 1
        assert next_ctx.canonical_sources[0].source_name == "Updated Canonical API"

    finally:
        db.close()




