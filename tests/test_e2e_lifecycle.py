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

def test_full_e2e_acceptance_loop():
    # 1. 启动空 Benefit Desk 数据库
    test_engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    init_db(bind=test_engine)
    Session = sessionmaker(bind=test_engine)
    db = Session()

    try:
        # 2. baseline_state = EMPTY, baseline_revision = 0
        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        assert sys_state.baseline_state == "EMPTY"
        assert sys_state.baseline_revision == 0

        # 3. 点击“导出扫描上下文”
        context_pkg = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        scan_id_1 = context_pkg.scan.scan_id

        # 4. 得到合法 SCAN_CONTEXT JSON
        assert context_pkg.protocol_version == "0.1"
        assert context_pkg.benefit_schema_version == "1.2.1"
        assert context_pkg.package_type == "SCAN_CONTEXT"
        assert context_pkg.scan.baseline_revision == 0
        assert context_pkg.scan.baseline_state == "EMPTY"
        assert len(context_pkg.benefit_index) == 0

        # 5. 模拟 ChatGPT 返回合法 SCAN_IMPORT JSON
        import_data = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id_1,
                "scan_mode": "FULL_SCAN",
                "context_baseline_revision": 0,
                "generated_at": "2026-08-18T18:25:00+08:00",
                "scan_statuses": [
                    "PUBLIC_COMPLETE",
                    "OVERALL_PARTIAL"
                ],
                "baseline_action": "BUILD_INITIAL_BASELINE",
                "summary_notes": "首次基线构建完成"
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
                        "lead_summary": "疑似新用户赠送 20 美金 API Credits",
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
                },
                {
                    "vendor": "OpenAI",
                    "product": "ChatGPT",
                    "surface": "Web Pricing",
                    "region": "GLOBAL",
                    "coverage_state": "CHECKED_NONE",
                    "scan_observed_at": "2026-08-18T18:25:00+08:00",
                    "actual_checked_at": "2026-08-18T18:25:00+08:00",
                    "next_review_at": "UNKNOWN"
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

        # 6. 上传 Scan Import & 7. 系统执行所有 Validation
        preview = ImportService.parse_and_preview(db, raw_import_json)
        assert preview["is_valid"] is True
        assert len(preview["errors"]) == 0

        # 8. 显示中文导入预览
        p = preview["preview"]
        assert p["benefit_create_count"] == 1
        assert p["lead_create_count"] == 1
        assert p["coverage_recheck_count"] == 2
        assert p["source_add_count"] == 1
        assert p["manual_check_count"] == 1

        # 9. 用户确认
        commit_res = ImportService.commit_import(db, preview["import_pkg"], raw_import_json)
        assert commit_res["success"] is True

        # 10. 新福利获得正式 benefit_id
        b = db.query(BenefitModel).filter_by(vendor="TRAE").first()
        assert b is not None
        assert b.benefit_id == "BEN-000001"
        assert b.campaign_name == "Daily Checkin Bonus"

        # 11. Coverage / Lead / Source 正确写入
        lead = db.query(LeadModel).filter_by(lead_id="LEAD-000001").first()
        assert lead is not None
        assert lead.vendor == "Anthropic"

        cov1 = db.query(CoverageHistoryModel).filter_by(coverage_id="COV-000001").first()
        assert cov1 is not None
        assert cov1.coverage_state == "CHECKED_FOUND"

        cov2 = db.query(CoverageHistoryModel).filter_by(coverage_id="COV-000002").first()
        assert cov2 is not None
        assert cov2.coverage_state == "CHECKED_NONE"

        src = db.query(CanonicalSourceModel).filter_by(source_id="SRC-000001").first()
        assert src is not None
        assert src.status == "ACTIVE"

        mchk = db.query(ManualCheckModel).filter_by(manual_check_id="MCHK-000001").first()
        assert mchk is not None
        assert mchk.channel == "IDE"

        # 12. User Benefit State 保持独立 (用户可以在 UI 标记 CLAIMED)
        u_state = UserBenefitStateModel(benefit_id=b.benefit_id, action_state="CLAIMED", notes="已完成签到")
        db.add(u_state)
        db.commit()

        # 13. baseline_revision + 1, baseline_state = READY
        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        assert sys_state.baseline_revision == 1
        assert sys_state.baseline_state == "READY"

        # 14. 相同 scan_id 再次导入被阻止
        preview_dup = ImportService.parse_and_preview(db, raw_import_json)
        assert preview_dup["is_valid"] is False
        assert any("该扫描已经导入" in err for err in preview_dup["errors"])

        # 15. 再次导出 Scan Context
        context_pkg_2 = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        assert context_pkg_2.scan.baseline_revision == 1
        assert context_pkg_2.scan.baseline_state == "READY"
        scan_id_2 = context_pkg_2.scan.scan_id

        # 16. 新 Context 正确包含刚才入库的数据
        assert len(context_pkg_2.benefit_index) == 1
        assert context_pkg_2.benefit_index[0].benefit_id == "BEN-000001"
        assert len(context_pkg_2.open_leads) == 1
        assert context_pkg_2.open_leads[0].lead_id == "LEAD-000001"
        assert len(context_pkg_2.latest_coverage) == 2
        assert len(context_pkg_2.canonical_sources) == 1
        assert context_pkg_2.canonical_sources[0].source_id == "SRC-000001"
        assert len(context_pkg_2.user_benefit_states) == 1
        assert context_pkg_2.user_benefit_states[0].action_state == "CLAIMED"
        assert len(context_pkg_2.manual_checks_open) == 1
        assert context_pkg_2.manual_checks_open[0].manual_check_id == "MCHK-000001"

        # 17. 下一轮 FULL_SCAN：合法 REVIEW_NOT_DUE (COV-000001 有明确未来日期 2099-01-01) -> PASS
        round2_pass_data = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id_2,
                "scan_mode": "FULL_SCAN",
                "context_baseline_revision": 1,
                "generated_at": "2026-08-18T19:30:00+08:00",
                "scan_statuses": ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"],
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "summary_notes": "第二轮复查未到期"
            },
            "benefit_changes": [],
            "lead_changes": [],
            "coverage_events": [
                {
                    "vendor": "TRAE",
                    "product": "TRAE CN",
                    "surface": "Client Reward",
                    "region": "CN",
                    "coverage_state": "REVIEW_NOT_DUE",
                    "basis_coverage_id": "COV-000001",
                    "scan_observed_at": "2026-08-18T19:30:00+08:00",
                    "actual_checked_at": "2026-08-18T18:25:00+08:00"
                }
            ],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        r2_pass_json = dumps_json(round2_pass_data)
        p_r2 = ImportService.parse_and_preview(db, r2_pass_json)
        assert p_r2["is_valid"] is True
        ImportService.commit_import(db, p_r2["import_pkg"], r2_pass_json)

        # 18. next_review_at UNKNOWN 的 REVIEW_NOT_DUE (COV-000002) -> FAIL
        context_pkg_3 = ExportService.generate_scan_context(db, requested_mode="FULL_SCAN")
        scan_id_3 = context_pkg_3.scan.scan_id

        round3_fail_data = {
            "protocol_version": "0.1",
            "benefit_schema_version": "1.2.1",
            "package_type": "SCAN_IMPORT",
            "scan_result": {
                "scan_id": scan_id_3,
                "scan_mode": "FULL_SCAN",
                "context_baseline_revision": 2,
                "generated_at": "2026-08-18T20:00:00+08:00",
                "scan_statuses": ["PUBLIC_COMPLETE", "OVERALL_PARTIAL"],
                "baseline_action": "UPDATE_EXISTING_BASELINE",
                "summary_notes": "尝试对 UNKNOWN 复查日期的依据使用 REVIEW_NOT_DUE"
            },
            "benefit_changes": [],
            "lead_changes": [],
            "coverage_events": [
                {
                    "vendor": "OpenAI",
                    "product": "ChatGPT",
                    "surface": "Web Pricing",
                    "region": "GLOBAL",
                    "coverage_state": "REVIEW_NOT_DUE",
                    "basis_coverage_id": "COV-000002",
                    "scan_observed_at": "2026-08-18T20:00:00+08:00",
                    "actual_checked_at": "2026-08-18T18:25:00+08:00"
                }
            ],
            "source_updates": [],
            "manual_check_items": [],
            "warnings": []
        }
        r3_fail_json = dumps_json(round3_fail_data)
        p_r3 = ImportService.parse_and_preview(db, r3_fail_json)
        assert p_r3["is_valid"] is False
        assert any("缺少明确的 next_review_at" in e for e in p_r3["errors"])

    finally:
        db.close()

