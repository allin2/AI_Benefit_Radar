from datetime import date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CoverageHistoryModel, ManualCheckModel,
    CanonicalSourceModel, UserBenefitStateModel, ScanModel, SystemStateModel
)
from ai_benefit_desk.utils.date_utils import is_expiring_soon, is_review_due

class ReviewService:
    @staticmethod
    def get_overview_metrics(db: Session) -> Dict[str, Any]:
        today = date.today()
        
        # Benefits
        all_benefits = db.query(BenefitModel).all()
        confirmed_active = [
            b for b in all_benefits 
            if b.verification_status == "CONFIRMED" and b.status in ("ACTIVE", "EXPIRING_SOON")
        ]
        
        expiring_soon = [
            b for b in confirmed_active
            if is_expiring_soon(b.end_date, days=7, ref_date=today)
        ]
        
        review_due = [
            b for b in all_benefits
            if is_review_due(b.next_review_date, ref_date=today)
        ]

        # User States
        user_states = {s.benefit_id: s.action_state for s in db.query(UserBenefitStateModel).all()}
        not_reviewed_count = sum(1 for b in confirmed_active if user_states.get(b.benefit_id, "NOT_REVIEWED") == "NOT_REVIEWED")
        interested_count = sum(1 for b in confirmed_active if user_states.get(b.benefit_id) == "INTERESTED")

        # Leads
        open_leads = db.query(LeadModel).filter_by(status="OPEN").count()

        # Blind Spots (latest coverage per surface)
        # Query distinct vendor, product, surface, region
        all_covs = db.query(CoverageHistoryModel).order_by(CoverageHistoryModel.id.desc()).all()
        seen_surfaces = set()
        blind_spot_count = 0
        for c in all_covs:
            key = (c.vendor, c.product, c.surface, c.region)
            if key not in seen_surfaces:
                seen_surfaces.add(key)
                if c.coverage_state == "BLIND_SPOT":
                    blind_spot_count += 1

        # Manual Checks
        open_manual_checks = db.query(ManualCheckModel).filter_by(status="OPEN").count()

        # System State
        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        baseline_revision = sys_state.baseline_revision if sys_state else 0
        baseline_state = sys_state.baseline_state if sys_state else "EMPTY"

        # Latest Scan
        latest_scan = db.query(ScanModel).order_by(ScanModel.id.desc()).first()

        return {
            "confirmed_active_count": len(confirmed_active),
            "expiring_soon_count": len(expiring_soon),
            "expiring_soon_items": expiring_soon,
            "not_reviewed_count": not_reviewed_count,
            "interested_count": interested_count,
            "review_due_count": len(review_due),
            "review_due_items": review_due,
            "open_leads_count": open_leads,
            "blind_spots_count": blind_spot_count,
            "open_manual_checks_count": open_manual_checks,
            "baseline_revision": baseline_revision,
            "baseline_state": baseline_state,
            "latest_scan_id": latest_scan.scan_id if latest_scan else "-",
            "latest_scan_time": latest_scan.created_at.strftime("%Y-%m-%d %H:%M") if (latest_scan and latest_scan.created_at) else "-"
        }


class ReviewPlanner:
    """Planner responsible for determining review requirements and forced review signals."""

    @staticmethod
    def infer_lead_surface(lead: LeadModel) -> str:
        """Infer the exact surface for an open lead based on summary / category."""
        summary = (lead.lead_summary or "").lower()
        if any(k in summary for k in ("checkin", "check-in", "签到", "打卡", "client reward", "reward", "任务")):
            return "CLIENT_REWARD"
        if any(k in summary for k in ("referral", "邀请", "推荐", "invite")):
            return "REFERRAL"
        if any(k in summary for k in ("model discount", "discount", "multiplier", "off-peak", "夜间", "折扣", "倍率", "降价", "economics")):
            return "MODEL_ECONOMICS"
        if any(k in summary for k in ("subscription", "pro", "plus", "tier", "会员", "订阅")):
            return "SUBSCRIPTION"
        if any(k in summary for k in ("student", "education", "高校", "学生")):
            return "PROGRAM_STUDENT"
        if any(k in summary for k in ("startup", "初创", "孵化")):
            return "PROGRAM_STARTUP"
        if any(k in summary for k in ("research", "science", "科研")):
            return "PROGRAM_RESEARCH"
        if any(k in summary for k in ("developer", "开发者")):
            return "PROGRAM_DEVELOPER"
        if any(k in summary for k in ("open source", "oss", "开源")):
            return "PROGRAM_OPEN_SOURCE"
        if any(k in summary for k in ("partner", "bundle", "合作")):
            return "PARTNER_BUNDLE"
        if any(k in summary for k in ("credit", "token", "grant", "额度", "体验金", "赠送")):
            return "CREDITS"
        if any(k in summary for k in ("migration", "迁移")):
            return "MIGRATION"
        if any(k in summary for k in ("api", "console", "控制台")):
            return "BILLING_CONSOLE"
        if any(k in summary for k in ("free signup", "注册", "免费注册")):
            return "FREE_SIGNUP"
        if any(k in summary for k in ("price", "pricing", "价格", "费率", "cut", "降费")):
            return "PRICING"
        return "UNKNOWN"

    @staticmethod
    def infer_benefit_surface(benefit: BenefitModel) -> str:
        """Infer the exact surface for a disputed / likely benefit."""
        b_type = (benefit.benefit_type or "").upper()
        if b_type in ("CHECKIN", "CLIENT_REWARD"):
            return "CLIENT_REWARD"
        if b_type == "REFERRAL":
            return "REFERRAL"
        if b_type == "STUDENT_PROGRAM":
            return "PROGRAM_STUDENT"
        if b_type == "STARTUP_PROGRAM":
            return "PROGRAM_STARTUP"
        if b_type == "RESEARCHER_PROGRAM":
            return "PROGRAM_RESEARCH"
        if b_type == "DEVELOPER_PROGRAM":
            return "PROGRAM_DEVELOPER"
        if b_type == "OPEN_SOURCE_PROGRAM":
            return "PROGRAM_OPEN_SOURCE"
        if b_type in ("API_CREDITS", "WALLET_GRANT", "CREDITS"):
            return "CREDITS"
        if b_type in ("SUBSCRIPTION_UPGRADE", "SUBSCRIPTION"):
            return "SUBSCRIPTION"
        if b_type == "PARTNER_BUNDLE":
            return "PARTNER_BUNDLE"
        if b_type == "MODEL_DISCOUNT":
            return "MODEL_ECONOMICS"
        if b_type == "FREE_TIER":
            return "FREE_SIGNUP"

        text = f"{benefit.campaign_name} {benefit.benefit_detail}".lower()
        if any(k in text for k in ("checkin", "check-in", "签到", "打卡")):
            return "CLIENT_REWARD"
        if any(k in text for k in ("referral", "邀请", "推荐", "invite")):
            return "REFERRAL"
        if any(k in text for k in ("discount", "multiplier", "倍率", "折扣")):
            return "MODEL_ECONOMICS"
        if any(k in text for k in ("price", "pricing", "费率", "价格")):
            return "PRICING"
        return "UNKNOWN"

    @staticmethod
    def plan_forced_reviews(
        db: Session,
        scan_id: Optional[str] = None,
        requested_mode: str = "FULL_SCAN"
    ) -> List[Dict[str, str]]:
        """Compute forced early review requirements for the scan.

        Triggers include:
        1. Open Leads indicating promotion/pricing/reward changes
        2. Deprecated sources requiring re-verification of the associated surface
        3. Benefits with DISPUTED or LIKELY status needing confirmation

        Returns:
            List of dicts: {"vendor": ..., "product": ..., "surface": ..., "region": ..., "reason": ...}
        """
        requirements: List[Dict[str, str]] = []
        seen_keys = set()

        # 1. Open Leads with promotional/pricing/reward changes
        leads = db.query(LeadModel).filter_by(status="OPEN").all()
        for lead in leads:
            surface = ReviewPlanner.infer_lead_surface(lead)
            regions = lead.regions if (lead.regions and len(lead.regions) > 0) else ["UNKNOWN"]
            for region in regions:
                key = (lead.vendor, lead.product, surface, region)
                if key not in seen_keys:
                    seen_keys.add(key)
                    requirements.append({
                        "vendor": lead.vendor,
                        "product": lead.product,
                        "surface": surface,
                        "region": region,
                        "reason": f"Open Lead pending verification: {lead.lead_summary}"
                    })

        # 2. Canonical Sources with status DEPRECATED
        dep_sources = db.query(CanonicalSourceModel).filter_by(status="DEPRECATED").all()
        for s in dep_sources:
            surface = s.surface or "DOCS"
            linked_cov = db.query(CoverageHistoryModel).filter_by(source_id=s.source_id).first()
            if linked_cov and linked_cov.region and linked_cov.region != "UNKNOWN":
                region = linked_cov.region
            else:
                combined = f"{s.vendor} {s.product} {s.source_name} {s.url}".upper()
                if " CN" in combined or ".CN" in combined or "/CN" in combined or "国内" in combined or "中文" in combined:
                    region = "CN"
                elif " US" in combined or "/US" in combined:
                    region = "US"
                else:
                    region = "UNKNOWN"

            key = (s.vendor, s.product, surface, region)
            if key not in seen_keys:
                seen_keys.add(key)
                requirements.append({
                    "vendor": s.vendor,
                    "product": s.product,
                    "surface": surface,
                    "region": region,
                    "reason": f"Canonical source deprecated: {s.url} ({s.deprecation_reason or 'deprecated'})"
                })

        # 3. Disputed or likely benefits
        disputed = db.query(BenefitModel).filter(
            BenefitModel.verification_status.in_(["DISPUTED", "LIKELY"])
        ).all()
        for b in disputed:
            surface = ReviewPlanner.infer_benefit_surface(b)
            regions = b.regions if (b.regions and len(b.regions) > 0) else ["UNKNOWN"]
            for region in regions:
                key = (b.vendor, b.product, surface, region)
                if key not in seen_keys:
                    seen_keys.add(key)
                    requirements.append({
                        "vendor": b.vendor,
                        "product": b.product,
                        "surface": surface,
                        "region": region,
                        "reason": f"Benefit {b.benefit_id} in {b.verification_status} status requires re-verification"
                    })

        return requirements

    @staticmethod
    def register_scan_forced_reviews(
        db: Session,
        scan_id: str,
        requirements: List[Dict[str, str]]
    ) -> None:
        """Persist forced review requirements on ScanModel."""
        scan = db.query(ScanModel).filter_by(scan_id=scan_id).first()
        if scan:
            existing = list(scan.forced_review_requirements)
            existing_keys = {(r.get("vendor"), r.get("product"), r.get("surface"), r.get("region")) for r in existing}
            for req in requirements:
                k = (req.get("vendor"), req.get("product"), req.get("surface"), req.get("region"))
                if k not in existing_keys:
                    existing.append(req)
                    existing_keys.add(k)
            scan.forced_review_requirements = existing
            db.commit()

