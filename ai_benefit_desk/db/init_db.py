from sqlalchemy.orm import Session
from ai_benefit_desk.db.database import engine, Base, SessionLocal
from ai_benefit_desk.db.models import SystemStateModel, IdSequenceModel
from ai_benefit_desk.config import PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION

def init_db(bind=None):
    target_engine = bind or engine
    Base.metadata.create_all(bind=target_engine)
    
    db: Session = SessionLocal(bind=target_engine) if bind else SessionLocal()
    try:
        # Check system state
        state = db.query(SystemStateModel).filter_by(id=1).first()
        if not state:
            state = SystemStateModel(
                id=1,
                baseline_revision=0,
                baseline_state="EMPTY",
                protocol_version=PROTOCOL_VERSION,
                benefit_schema_version=BENEFIT_SCHEMA_VERSION
            )
            db.add(state)
            
        # Initialize default ID sequences if not present
        prefixes = ["BEN", "LEAD", "SRC", "COV", "MCHK", "SCAN"]
        for p in prefixes:
            seq = db.query(IdSequenceModel).filter_by(prefix=p).first()
            if not seq:
                db.add(IdSequenceModel(prefix=p, current_val=0))
                
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
