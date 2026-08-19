import json
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Index
)
from sqlalchemy.orm import relationship
from ai_benefit_desk.db.database import Base

class BenefitModel(Base):
    __tablename__ = "benefits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    benefit_id = Column(String(32), unique=True, nullable=False, index=True)
    vendor = Column(String(128), nullable=False, index=True)
    product = Column(String(128), nullable=False, index=True)
    linked_vendor = Column(String(128), default="UNKNOWN")
    linked_product = Column(String(128), default="UNKNOWN")
    campaign_name = Column(String(255), nullable=False)
    benefit_type = Column(String(64), nullable=False, index=True)
    benefit_detail = Column(Text, nullable=False)
    linked_benefit_detail = Column(Text, default="UNKNOWN")
    wallet = Column(String(128), default="UNKNOWN", index=True)
    amount = Column(String(64), default="UNKNOWN")
    unit = Column(String(32), default="UNKNOWN")
    reset_policy = Column(String(32), default="UNKNOWN")
    grant_method = Column(String(32), default="UNKNOWN")
    _regions = Column("regions", Text, nullable=False, default="[\"UNKNOWN\"]")
    eligibility = Column(Text, default="UNKNOWN")
    _eligibility_class = Column("eligibility_class", Text, nullable=False, default="[\"UNKNOWN\"]")
    start_date = Column(String(32), default="UNKNOWN")
    end_date = Column(String(32), default="UNKNOWN", index=True)
    first_seen = Column(String(32), nullable=False)
    last_checked = Column(String(32), nullable=False)
    next_review_date = Column(String(32), default="UNKNOWN", index=True)
    claim_method = Column(Text, default="UNKNOWN")
    credit_card_required = Column(String(16), default="UNKNOWN")
    verification_required = Column(String(16), default="UNKNOWN")
    official_source = Column(Text, nullable=False)
    source_level = Column(String(8), nullable=False)
    verification_status = Column(String(32), nullable=False, index=True)
    status = Column(String(32), nullable=False, index=True)
    change_type = Column(String(32), nullable=False, default="UNKNOWN")
    account_risk = Column(String(16), default="NONE")
    region_risk = Column(String(16), default="UNKNOWN")
    compliance_risk = Column(String(16), default="NONE")
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user_state = relationship("UserBenefitStateModel", back_populates="benefit", uselist=False, cascade="all, delete-orphan")

    @property
    def regions(self):
        try:
            return json.loads(self._regions) if self._regions else ["UNKNOWN"]
        except Exception:
            return ["UNKNOWN"]

    @regions.setter
    def regions(self, val):
        if isinstance(val, list):
            self._regions = json.dumps(val, ensure_ascii=False)
        else:
            self._regions = json.dumps([str(val)], ensure_ascii=False)

    @property
    def eligibility_class(self):
        try:
            return json.loads(self._eligibility_class) if self._eligibility_class else ["UNKNOWN"]
        except Exception:
            return ["UNKNOWN"]

    @eligibility_class.setter
    def eligibility_class(self, val):
        if isinstance(val, list):
            self._eligibility_class = json.dumps(val, ensure_ascii=False)
        else:
            self._eligibility_class = json.dumps([str(val)], ensure_ascii=False)


class LeadModel(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    lead_id = Column(String(32), unique=True, nullable=False, index=True)
    vendor = Column(String(128), nullable=False, index=True)
    product = Column(String(128), nullable=False, index=True)
    lead_summary = Column(Text, nullable=False)
    verification_status = Column(String(32), nullable=False, index=True)
    source_level = Column(String(8), nullable=False)
    _regions = Column("regions", Text, nullable=False, default="[\"UNKNOWN\"]")
    missing_evidence = Column(Text, default="")
    first_seen = Column(String(32), nullable=False)
    last_checked = Column(String(32), nullable=False)
    next_review_date = Column(String(32), default="UNKNOWN")
    status = Column(String(32), nullable=False, default="OPEN", index=True)  # OPEN / RESOLVED / REJECTED
    resolved_benefit_id = Column(String(32), nullable=True)
    rejection_reason = Column(Text, nullable=True)
    checked_at = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def regions(self):
        try:
            return json.loads(self._regions) if self._regions else ["UNKNOWN"]
        except Exception:
            return ["UNKNOWN"]

    @regions.setter
    def regions(self, val):
        if isinstance(val, list):
            self._regions = json.dumps(val, ensure_ascii=False)
        else:
            self._regions = json.dumps([str(val)], ensure_ascii=False)


class CoverageHistoryModel(Base):
    __tablename__ = "coverage_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    coverage_id = Column(String(32), unique=True, nullable=False, index=True)
    scan_id = Column(String(64), nullable=False, index=True)
    vendor = Column(String(128), nullable=False, index=True)
    product = Column(String(128), nullable=False, index=True)
    wallet = Column(String(128), default="UNKNOWN")
    surface = Column(String(64), nullable=False, index=True)
    region = Column(String(32), nullable=False, index=True)
    coverage_state = Column(String(32), nullable=False, index=True)
    scan_observed_at = Column(String(64), nullable=False)
    actual_checked_at = Column(String(64), nullable=True)
    next_review_at = Column(String(32), default="UNKNOWN")
    source_id = Column(String(32), nullable=True)
    basis_coverage_id = Column(String(32), nullable=True)
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class CanonicalSourceModel(Base):
    __tablename__ = "canonical_sources"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_id = Column(String(32), unique=True, nullable=False, index=True)
    vendor = Column(String(128), nullable=False, index=True)
    product = Column(String(128), nullable=False, index=True)
    surface = Column(String(64), nullable=False)
    source_name = Column(String(255), nullable=False)
    url = Column(Text, nullable=False)
    source_type = Column(String(64), nullable=False)
    source_level = Column(String(8), nullable=False)
    status = Column(String(32), nullable=False, default="ACTIVE", index=True)  # ACTIVE / DEPRECATED
    last_verified_at = Column(String(32), nullable=True)
    deprecation_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class UserBenefitStateModel(Base):
    __tablename__ = "user_benefit_states"

    id = Column(Integer, primary_key=True, autoincrement=True)
    benefit_id = Column(String(32), ForeignKey("benefits.benefit_id"), unique=True, nullable=False, index=True)
    action_state = Column(String(32), nullable=False, default="NOT_REVIEWED", index=True)
    notes = Column(Text, default="")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    benefit = relationship("BenefitModel", back_populates="user_state")


class ManualCheckModel(Base):
    __tablename__ = "manual_checks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    manual_check_id = Column(String(32), unique=True, nullable=False, index=True)
    vendor = Column(String(128), nullable=False, index=True)
    product = Column(String(128), nullable=False, index=True)
    channel = Column(String(32), nullable=False)
    reason = Column(Text, nullable=False)
    priority = Column(String(16), nullable=False, default="MEDIUM")
    suggested_action = Column(Text, nullable=False)
    status = Column(String(32), nullable=False, default="OPEN", index=True)  # OPEN / COMPLETED / DISMISSED
    related_benefit_id = Column(String(32), nullable=True)
    related_lead_id = Column(String(32), nullable=True)
    result_notes = Column(Text, default="")
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ScanModel(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(String(64), unique=True, nullable=False, index=True)
    requested_mode = Column(String(32), nullable=False)
    actual_scan_mode = Column(String(32), nullable=True)
    baseline_revision_at_export = Column(Integer, nullable=True)
    baseline_action = Column(String(64), nullable=True)
    generated_context_at = Column(DateTime, nullable=True)
    imported_at = Column(DateTime, nullable=True)
    _scan_statuses = Column("scan_statuses", Text, nullable=True)
    _forced_review_requirements = Column("forced_review_requirements", Text, nullable=True, default="[]")
    import_status = Column(String(32), nullable=False, default="EXPORTED", index=True)  # EXPORTED, COMMITTED, CANCELLED
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def scan_statuses(self):
        try:
            return json.loads(self._scan_statuses) if self._scan_statuses else {}
        except Exception:
            return {}

    @scan_statuses.setter
    def scan_statuses(self, val):
        self._scan_statuses = json.dumps(val, ensure_ascii=False) if val else "{}"

    @property
    def forced_review_requirements(self):
        try:
            return json.loads(self._forced_review_requirements) if self._forced_review_requirements else []
        except Exception:
            return []

    @forced_review_requirements.setter
    def forced_review_requirements(self, val):
        self._forced_review_requirements = json.dumps(val, ensure_ascii=False) if val is not None else "[]"


class ImportAuditModel(Base):
    __tablename__ = "import_audits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_id = Column(String(64), nullable=False, index=True)
    imported_at = Column(DateTime, default=datetime.utcnow)
    protocol_version = Column(String(16), nullable=False)
    benefit_schema_version = Column(String(16), nullable=False)
    context_baseline_revision = Column(Integer, nullable=False)
    database_revision_before = Column(Integer, nullable=False)
    database_revision_after = Column(Integer, nullable=False)
    raw_import_json = Column(Text, nullable=False)
    _validation_result = Column("validation_result", Text, nullable=False, default="{}")
    _warnings = Column("warnings", Text, nullable=False, default="[]")
    user_confirmed = Column(Boolean, default=True)
    status = Column(String(32), nullable=False, default="SUCCESS")  # SUCCESS / ROLLBACK
    created_at = Column(DateTime, default=datetime.utcnow)

    @property
    def validation_result(self):
        try:
            return json.loads(self._validation_result) if self._validation_result else {}
        except Exception:
            return {}

    @validation_result.setter
    def validation_result(self, val):
        self._validation_result = json.dumps(val, ensure_ascii=False) if val else "{}"

    @property
    def warnings(self):
        try:
            return json.loads(self._warnings) if self._warnings else []
        except Exception:
            return []

    @warnings.setter
    def warnings(self, val):
        self._warnings = json.dumps(val, ensure_ascii=False) if val else "[]"


class SystemStateModel(Base):
    __tablename__ = "system_state"

    id = Column(Integer, primary_key=True)
    baseline_revision = Column(Integer, nullable=False, default=0)
    baseline_state = Column(String(32), nullable=False, default="EMPTY")  # EMPTY / READY
    protocol_version = Column(String(16), nullable=False, default="0.1")
    benefit_schema_version = Column(String(16), nullable=False, default="1.2.1")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class IdSequenceModel(Base):
    __tablename__ = "id_sequences"

    prefix = Column(String(32), primary_key=True)
    current_val = Column(Integer, nullable=False, default=0)
