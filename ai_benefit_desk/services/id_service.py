from datetime import date
import re
from sqlalchemy.orm import Session
from ai_benefit_desk.db.models import (
    IdSequenceModel, BenefitModel, LeadModel, CanonicalSourceModel,
    CoverageHistoryModel, ManualCheckModel, ScanModel
)

PREFIX_TABLE_MAP = {
    "BEN": (BenefitModel, "benefit_id"),
    "LEAD": (LeadModel, "lead_id"),
    "SRC": (CanonicalSourceModel, "source_id"),
    "COV": (CoverageHistoryModel, "coverage_id"),
    "MCHK": (ManualCheckModel, "manual_check_id")
}

class IdService:
    @staticmethod
    def get_next_id(db: Session, prefix: str, width: int = 6) -> str:
        """Generate next sequential permanent ID for a given prefix."""
        seq = db.query(IdSequenceModel).filter_by(prefix=prefix).with_for_update().first()
        if not seq:
            seq = IdSequenceModel(prefix=prefix, current_val=0)
            db.add(seq)
            db.flush()

        # If table has records with higher ID than current sequence, align it
        if prefix in PREFIX_TABLE_MAP:
            model_cls, id_attr = PREFIX_TABLE_MAP[prefix]
            last_record = db.query(model_cls).order_by(getattr(model_cls, "id").desc()).first()
            if last_record:
                val_str = getattr(last_record, id_attr, "")
                match = re.search(r"-(\d+)$", val_str)
                if match:
                    max_id_num = int(match.group(1))
                    if max_id_num > seq.current_val:
                        seq.current_val = max_id_num
        
        seq.current_val += 1
        db.flush()
        return f"{prefix}-{seq.current_val:0{width}d}"

    @staticmethod
    def generate_benefit_id(db: Session) -> str:
        return IdService.get_next_id(db, "BEN", width=6)

    @staticmethod
    def generate_lead_id(db: Session) -> str:
        return IdService.get_next_id(db, "LEAD", width=6)

    @staticmethod
    def generate_source_id(db: Session) -> str:
        return IdService.get_next_id(db, "SRC", width=6)

    @staticmethod
    def generate_coverage_id(db: Session) -> str:
        return IdService.get_next_id(db, "COV", width=6)

    @staticmethod
    def generate_manual_check_id(db: Session) -> str:
        return IdService.get_next_id(db, "MCHK", width=6)

    @staticmethod
    def generate_scan_id(db: Session, target_date: date = None) -> str:
        """Generate SCAN-YYYYMMDD-001 format scan_id."""
        d = target_date or date.today()
        date_str = d.strftime("%Y%m%d")
        daily_prefix = f"SCAN_{date_str}"
        
        seq = db.query(IdSequenceModel).filter_by(prefix=daily_prefix).with_for_update().first()
        if not seq:
            seq = IdSequenceModel(prefix=daily_prefix, current_val=0)
            db.add(seq)
            db.flush()
            
        seq.current_val += 1
        db.flush()
        return f"SCAN-{date_str}-{seq.current_val:03d}"
