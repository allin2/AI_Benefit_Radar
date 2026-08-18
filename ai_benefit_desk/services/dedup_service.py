import re
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from ai_benefit_desk.db.models import BenefitModel
from ai_benefit_desk.schemas.benefit_models import BenefitRecord

def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r"[\s\-_，。！？、]+", "", t)
    return t

class DedupService:
    @staticmethod
    def check_duplicate(db: Session, candidate: BenefitRecord, local_ref: str) -> Optional[Dict[str, Any]]:
        """Check if candidate benefit matches an existing DB record."""
        c_vendor_norm = normalize_text(candidate.vendor)
        c_prod_norm = normalize_text(candidate.product)
        c_camp_norm = normalize_text(candidate.campaign_name)
        c_source_norm = candidate.official_source.strip().lower() if candidate.official_source else ""

        existing_benefits = db.query(BenefitModel).all()
        
        for b in existing_benefits:
            b_vendor_norm = normalize_text(b.vendor)
            b_prod_norm = normalize_text(b.product)
            b_camp_norm = normalize_text(b.campaign_name)
            b_source_norm = b.official_source.strip().lower() if b.official_source else ""

            # Check 1: Same Vendor, Product, and Campaign Name
            if c_vendor_norm == b_vendor_norm and c_prod_norm == b_prod_norm and c_camp_norm == b_camp_norm:
                return {
                    "local_ref": local_ref,
                    "existing_benefit_id": b.benefit_id,
                    "existing_campaign_name": b.campaign_name,
                    "existing_vendor": b.vendor,
                    "existing_product": b.product,
                    "reason": "厂商、产品与活动名称完全匹配",
                    "confidence": "HIGH"
                }

            # Check 2: Same Vendor and Official Source URL (non-UNKNOWN)
            if c_source_norm and c_source_norm != "unknown" and c_source_norm == b_source_norm:
                if c_vendor_norm == b_vendor_norm:
                    return {
                        "local_ref": local_ref,
                        "existing_benefit_id": b.benefit_id,
                        "existing_campaign_name": b.campaign_name,
                        "existing_vendor": b.vendor,
                        "existing_product": b.product,
                        "reason": "厂商与官方来源 URL 完全一致",
                        "confidence": "HIGH"
                    }

            # Check 3: Same Vendor, Product, Benefit Type, and Wallet
            if (c_vendor_norm == b_vendor_norm and c_prod_norm == b_prod_norm and 
                candidate.benefit_type == b.benefit_type and 
                normalize_text(candidate.wallet) == normalize_text(b.wallet) and
                candidate.wallet != "UNKNOWN"):
                return {
                    "local_ref": local_ref,
                    "existing_benefit_id": b.benefit_id,
                    "existing_campaign_name": b.campaign_name,
                    "existing_vendor": b.vendor,
                    "existing_product": b.product,
                    "reason": "厂商、产品、福利类型及 Wallet 资源完全一致",
                    "confidence": "MEDIUM"
                }

        return None

    @staticmethod
    def detect_candidate_duplicates(db: Session, benefit_changes: List[Any]) -> List[Dict[str, Any]]:
        duplicates = []
        for op in benefit_changes:
            if op.operation == "CREATE" and op.record:
                dup = DedupService.check_duplicate(db, op.record, op.local_ref)
                if dup:
                    duplicates.append(dup)
        return duplicates
