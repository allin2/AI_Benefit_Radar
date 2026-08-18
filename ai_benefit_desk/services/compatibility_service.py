from typing import List, Dict, Any
from sqlalchemy.orm import Session
from ai_benefit_desk.db.models import LeadModel

class CompatibilityService:
    @staticmethod
    def get_compatibility_warnings(db: Session) -> List[Dict[str, Any]]:
        """
        Scan database for legacy compatibility issues that require manual attention.
        Does not modify database records automatically.
        """
        warnings: List[Dict[str, Any]] = []

        # 1. Legacy OPEN + CONFIRMED leads
        legacy_leads = db.query(LeadModel).filter_by(status="OPEN", verification_status="CONFIRMED").all()
        for l in legacy_leads:
            warnings.append({
                "type": "LEGACY_CONFIRMED_LEAD",
                "lead_id": l.lead_id,
                "vendor": l.vendor,
                "product": l.product,
                "message_zh": f"发现旧版本留下的已确认线索 [{l.lead_id}] ({l.vendor} - {l.product})，请人工决定转为正式福利、降级线索或驳回。"
            })

        return warnings
