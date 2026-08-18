from sqlalchemy import text
from sqlalchemy.orm import Session
from ai_benefit_desk.db.database import engine, Base, SessionLocal
from ai_benefit_desk.db.models import SystemStateModel, IdSequenceModel
from ai_benefit_desk.config import PROTOCOL_VERSION, BENEFIT_SCHEMA_VERSION

def migrate_db_schema(target_engine):
    """Safely migrate legacy database schema if needed (e.g. SQLite column constraint updates)."""
    with target_engine.connect() as conn:
        # Check if coverage_history table exists
        res = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='coverage_history'"))
        if not res.fetchone():
            return
        
        # Check if actual_checked_at column in coverage_history has notnull == 1
        cols = conn.execute(text("PRAGMA table_info(coverage_history)")).fetchall()
        needs_coverage_migration = False
        for col in cols:
            # PRAGMA table_info returns (cid, name, type, notnull, dflt_value, pk)
            name = col[1]
            notnull = col[3]
            if name == "actual_checked_at" and notnull == 1:
                needs_coverage_migration = True
                break
        
        if needs_coverage_migration:
            conn.execute(text("""
                CREATE TABLE coverage_history_dg_tmp (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    coverage_id VARCHAR(32) NOT NULL,
                    scan_id VARCHAR(64) NOT NULL,
                    vendor VARCHAR(128) NOT NULL,
                    product VARCHAR(128) NOT NULL,
                    wallet VARCHAR(128) DEFAULT 'UNKNOWN',
                    surface VARCHAR(64) NOT NULL,
                    region VARCHAR(32) NOT NULL,
                    coverage_state VARCHAR(32) NOT NULL,
                    scan_observed_at VARCHAR(64) NOT NULL,
                    actual_checked_at VARCHAR(64),
                    next_review_at VARCHAR(32) DEFAULT 'UNKNOWN',
                    source_id VARCHAR(32),
                    basis_coverage_id VARCHAR(32),
                    notes TEXT DEFAULT '',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.execute(text("""
                INSERT INTO coverage_history_dg_tmp (
                    id, coverage_id, scan_id, vendor, product, wallet, surface, region,
                    coverage_state, scan_observed_at, actual_checked_at, next_review_at,
                    source_id, basis_coverage_id, notes, created_at
                )
                SELECT
                    id, coverage_id, scan_id, vendor, product, wallet, surface, region,
                    coverage_state, scan_observed_at, actual_checked_at, next_review_at,
                    source_id, basis_coverage_id, notes, created_at
                FROM coverage_history
            """))
            conn.execute(text("DROP TABLE coverage_history"))
            conn.execute(text("ALTER TABLE coverage_history_dg_tmp RENAME TO coverage_history"))
            
            # Re-create indexes
            conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_coverage_history_coverage_id ON coverage_history (coverage_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_coverage_history_scan_id ON coverage_history (scan_id)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_coverage_history_vendor ON coverage_history (vendor)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_coverage_history_product ON coverage_history (product)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_coverage_history_surface ON coverage_history (surface)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_coverage_history_region ON coverage_history (region)"))
            conn.execute(text("CREATE INDEX IF NOT EXISTS ix_coverage_history_coverage_state ON coverage_history (coverage_state)"))
            conn.commit()


def init_db(bind=None):
    target_engine = bind or engine
    Base.metadata.create_all(bind=target_engine)
    migrate_db_schema(target_engine)
    
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
