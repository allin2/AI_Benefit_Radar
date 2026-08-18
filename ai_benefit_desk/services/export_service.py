from datetime import datetime, date
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from ai_benefit_desk.config import PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION
from ai_benefit_desk.db.models import (
    BenefitModel, LeadModel, CoverageHistoryModel, CanonicalSourceModel,
    UserBenefitStateModel, ManualCheckModel, ScanModel, SystemStateModel
)
from ai_benefit_desk.schemas.benefit_models import BenefitRecord
from ai_benefit_desk.schemas.protocol_models import (
    ScanContextPackage, ScanMetadata, BenefitIndexItem, LeadRecord,
    CoverageEventItem, CanonicalSourceItem, UserBenefitStateItem, ManualCheckItem
)
from ai_benefit_desk.services.id_service import IdService
from ai_benefit_desk.utils.date_utils import is_review_due, today_str

class ExportService:
    @staticmethod
    def generate_scan_context(
        db: Session,
        requested_mode: str = "FULL_SCAN",
        vendor_filter: Optional[str] = None
    ) -> ScanContextPackage:
        now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        today = date.today()
        
        # 1. System state
        sys_state = db.query(SystemStateModel).filter_by(id=1).first()
        baseline_revision = sys_state.baseline_revision if sys_state else 0
        baseline_state = sys_state.baseline_state if sys_state else "EMPTY"

        # 2. Generate scan_id
        scan_id = IdService.generate_scan_id(db, today)

        # Record scan in scans table
        scan_record = ScanModel(
            scan_id=scan_id,
            requested_mode=requested_mode,
            baseline_revision_at_export=baseline_revision,
            generated_context_at=datetime.utcnow(),
            import_status="EXPORTED"
        )
        db.add(scan_record)
        db.commit()

        # 3. Benefit Index (Lightweight identity index)
        all_benefits_query = db.query(BenefitModel)
        if vendor_filter:
            all_benefits_query = all_benefits_query.filter(BenefitModel.vendor == vendor_filter)
        all_benefits = all_benefits_query.all()

        benefit_index = [
            BenefitIndexItem(
                benefit_id=b.benefit_id,
                vendor=b.vendor,
                product=b.product,
                campaign_name=b.campaign_name,
                wallet=b.wallet,
                status=b.status,
                last_checked=b.last_checked,
                next_review_date=b.next_review_date
            )
            for b in all_benefits
        ]

        # 4. Review Items (Pruned to items needing re-verification)
        review_items = []
        for b in all_benefits:
            needs_review = (
                is_review_due(b.next_review_date, ref_date=today) or
                b.status in ("EXPIRING_SOON", "UNKNOWN", "WAITLIST") or
                b.verification_status in ("LIKELY", "DISPUTED") or
                requested_mode == "DEEP_FULL_SCAN"  # Deep scan includes all for baseline refresh
            )
            if needs_review:
                review_items.append(
                    BenefitRecord(
                        benefit_id=b.benefit_id,
                        vendor=b.vendor,
                        product=b.product,
                        linked_vendor=b.linked_vendor,
                        linked_product=b.linked_product,
                        campaign_name=b.campaign_name,
                        benefit_type=b.benefit_type,
                        benefit_detail=b.benefit_detail,
                        linked_benefit_detail=b.linked_benefit_detail,
                        wallet=b.wallet,
                        amount=b.amount,
                        unit=b.unit,
                        reset_policy=b.reset_policy,
                        grant_method=b.grant_method,
                        regions=b.regions,
                        eligibility=b.eligibility,
                        eligibility_class=b.eligibility_class,
                        start_date=b.start_date,
                        end_date=b.end_date,
                        first_seen=b.first_seen,
                        last_checked=b.last_checked,
                        next_review_date=b.next_review_date,
                        claim_method=b.claim_method,
                        credit_card_required=b.credit_card_required,
                        verification_required=b.verification_required,
                        official_source=b.official_source,
                        source_level=b.source_level,
                        verification_status=b.verification_status,
                        status=b.status,
                        change_type=b.change_type,
                        account_risk=b.account_risk,
                        region_risk=b.region_risk,
                        compliance_risk=b.compliance_risk,
                        notes=b.notes or ""
                    )
                )

        # 5. Open Leads
        leads_query = db.query(LeadModel).filter_by(status="OPEN")
        if vendor_filter:
            leads_query = leads_query.filter(LeadModel.vendor == vendor_filter)
        open_leads = [
            LeadRecord(
                lead_id=l.lead_id,
                vendor=l.vendor,
                product=l.product,
                lead_summary=l.lead_summary,
                verification_status=l.verification_status,
                source_level=l.source_level,
                regions=l.regions,
                missing_evidence=l.missing_evidence,
                first_seen=l.first_seen,
                last_checked=l.last_checked,
                next_review_date=l.next_review_date,
                status=l.status,
                resolved_benefit_id=l.resolved_benefit_id,
                rejection_reason=l.rejection_reason
            )
            for l in leads_query.all()
        ]

        # 6. Latest Coverage (1 per vendor + product + surface + region)
        cov_query = db.query(CoverageHistoryModel).order_by(CoverageHistoryModel.id.desc())
        if vendor_filter:
            cov_query = cov_query.filter(CoverageHistoryModel.vendor == vendor_filter)
        seen_cov = set()
        latest_coverage = []
        for c in cov_query.all():
            key = (c.vendor, c.product, c.surface, c.region)
            if key not in seen_cov:
                seen_cov.add(key)
                latest_coverage.append(
                    CoverageEventItem(
                        coverage_id=c.coverage_id,
                        scan_id=c.scan_id,
                        vendor=c.vendor,
                        product=c.product,
                        wallet=c.wallet,
                        surface=c.surface,
                        region=c.region,
                        coverage_state=c.coverage_state,
                        scan_observed_at=c.scan_observed_at,
                        actual_checked_at=c.actual_checked_at,
                        next_review_at=c.next_review_at,
                        source_id=c.source_id,
                        basis_coverage_id=c.basis_coverage_id,
                        notes=c.notes or ""
                    )
                )

        # 7. Active Canonical Sources
        sources_query = db.query(CanonicalSourceModel).filter_by(status="ACTIVE")
        if vendor_filter:
            sources_query = sources_query.filter(CanonicalSourceModel.vendor == vendor_filter)
        canonical_sources = [
            CanonicalSourceItem(
                source_id=s.source_id,
                vendor=s.vendor,
                product=s.product,
                surface=s.surface,
                source_name=s.source_name,
                url=s.url,
                source_type=s.source_type,
                source_level=s.source_level,
                status=s.status,
                last_verified_at=s.last_verified_at
            )
            for s in sources_query.all()
        ]

        # 8. User Benefit States (Read-only)
        user_states = [
            UserBenefitStateItem(
                benefit_id=u.benefit_id,
                action_state=u.action_state,
                notes=u.notes or "",
                updated_at=u.updated_at.isoformat() if u.updated_at else None
            )
            for u in db.query(UserBenefitStateModel).all()
        ]

        # 9. Open Manual Checks
        mchk_query = db.query(ManualCheckModel).filter_by(status="OPEN")
        if vendor_filter:
            mchk_query = mchk_query.filter(ManualCheckModel.vendor == vendor_filter)
        manual_checks_open = [
            ManualCheckItem(
                manual_check_id=m.manual_check_id,
                vendor=m.vendor,
                product=m.product,
                channel=m.channel,
                reason=m.reason,
                priority=m.priority,
                suggested_action=m.suggested_action,
                status=m.status,
                related_benefit_id=m.related_benefit_id,
                related_lead_id=m.related_lead_id,
                result_notes=m.result_notes or ""
            )
            for m in mchk_query.all()
        ]

        # Assemble Package
        scan_meta = ScanMetadata(
            scan_id=scan_id,
            requested_mode=requested_mode,
            generated_at=now_iso,
            baseline_revision=baseline_revision,
            baseline_state=baseline_state,
            protocol_version=PROTOCOL_VERSION,
            benefit_schema_version=BENEFIT_SCHEMA_VERSION
        )

        return ScanContextPackage(
            protocol_version=PROTOCOL_VERSION,
            benefit_schema_version=BENEFIT_SCHEMA_VERSION,
            package_type="SCAN_CONTEXT",
            scan=scan_meta,
            benefit_index=benefit_index,
            review_items=review_items,
            open_leads=open_leads,
            latest_coverage=latest_coverage,
            canonical_sources=canonical_sources,
            user_benefit_states=user_states,
            manual_checks_open=manual_checks_open
        )
