from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, ConfigDict, field_validator
from ai_benefit_desk.schemas.benefit_models import BenefitRecord

# ==========================================
# 1. Evidence Model
# ==========================================
VALID_SOURCE_LEVELS = {"S", "A", "B", "C"}
VALID_SOURCE_ROLES = {"PRIMARY", "SUPPORTING", "LEAD"}

class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    source_level: str
    source_role: str = "PRIMARY"
    checked_at: str
    supports_fields: List[str] = Field(default_factory=list)

    @field_validator("source_level")
    @classmethod
    def validate_source_level(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_SOURCE_LEVELS:
            raise ValueError(f"Invalid source_level: {val}")
        return val

    @field_validator("source_role")
    @classmethod
    def validate_source_role(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_SOURCE_ROLES:
            raise ValueError(f"Invalid source_role: {val}")
        return val

# ==========================================
# 2. Warning Model
# ==========================================
VALID_WARNING_TYPES = {
    "REGION_UNCERTAIN",
    "EVIDENCE_MISMATCH",
    "POSSIBLE_DUPLICATE",
    "BASELINE_CONFLICT",
    "INCOMPLETE_COVERAGE",
    "SOURCE_CONFLICT",
    "TIME_STATUS_UNCERTAIN",
    "OTHER"
}

class WarningItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: str
    message_zh: str
    related_ref: Optional[str] = None

    @field_validator("type")
    @classmethod
    def validate_warning_type(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_WARNING_TYPES:
            raise ValueError(f"Invalid warning type: {val}")
        return val

# ==========================================
# 3. Base Record Models for Context & Import
# ==========================================

class BenefitIndexItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    benefit_id: str
    vendor: str
    product: str
    campaign_name: str
    wallet: Optional[str] = "UNKNOWN"
    status: str
    last_checked: str
    next_review_date: Optional[str] = "UNKNOWN"

class LeadRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    lead_id: Optional[str] = None
    vendor: str
    product: str
    lead_summary: str
    verification_status: str
    source_level: str
    regions: List[str] = Field(default_factory=lambda: ["UNKNOWN"])
    missing_evidence: Optional[str] = ""
    first_seen: str
    last_checked: str
    next_review_date: Optional[str] = "UNKNOWN"
    status: str = "OPEN"
    resolved_benefit_id: Optional[str] = None
    rejection_reason: Optional[str] = None

class CoverageEventItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coverage_id: Optional[str] = None
    scan_id: Optional[str] = None
    vendor: str
    product: str
    wallet: Optional[str] = "UNKNOWN"
    surface: str
    region: str
    coverage_state: str  # CHECKED_FOUND, CHECKED_NONE, REVIEW_NOT_DUE, NOT_CHECKED, BLIND_SPOT, NOT_APPLICABLE
    scan_observed_at: str
    actual_checked_at: str
    next_review_at: Optional[str] = "UNKNOWN"
    source_id: Optional[str] = None
    basis_coverage_id: Optional[str] = None
    notes: Optional[str] = ""

class CanonicalSourceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source_id: Optional[str] = None
    vendor: str
    product: str
    surface: str
    source_name: str
    url: str
    source_type: str
    source_level: str
    status: str = "ACTIVE"  # ACTIVE / DEPRECATED
    last_verified_at: Optional[str] = None

class UserBenefitStateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    benefit_id: str
    action_state: str  # NOT_REVIEWED, INTERESTED, CLAIMED, NOT_ELIGIBLE, SKIPPED
    notes: Optional[str] = ""
    updated_at: Optional[str] = None

class ManualCheckItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_ref: Optional[str] = None
    manual_check_id: Optional[str] = None
    vendor: str
    product: str
    channel: str  # ACCOUNT, DASHBOARD, APP, DESKTOP, IDE, EMAIL, CHECKOUT, OTHER
    reason: str
    priority: str = "MEDIUM"  # LOW, MEDIUM, HIGH
    suggested_action: str
    status: str = "OPEN"  # OPEN, COMPLETED, DISMISSED
    related_benefit_id: Optional[str] = None
    related_lead_id: Optional[str] = None
    result_notes: Optional[str] = ""

# ==========================================
# 4. SCAN_CONTEXT Package Models
# ==========================================

class ScanMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scan_id: str
    generated_at: str
    baseline_revision: int
    baseline_state: str  # EMPTY / READY
    regions: List[str] = Field(default_factory=lambda: ["CN", "TW", "US", "GLOBAL"])
    requested_mode: str = "FULL_SCAN"
    protocol_version: str = "0.1"
    benefit_schema_version: str = "1.2.1"

class ScanContextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: str = "0.1"
    benefit_schema_version: str = "1.2.1"
    package_type: str = "SCAN_CONTEXT"
    scan: ScanMetadata
    benefit_index: List[BenefitIndexItem] = Field(default_factory=list)
    review_items: List[BenefitRecord] = Field(default_factory=list)
    open_leads: List[LeadRecord] = Field(default_factory=list)
    latest_coverage: List[CoverageEventItem] = Field(default_factory=list)
    canonical_sources: List[CanonicalSourceItem] = Field(default_factory=list)
    user_benefit_states: List[UserBenefitStateItem] = Field(default_factory=list)
    manual_checks_open: List[ManualCheckItem] = Field(default_factory=list)

# ==========================================
# 5. SCAN_IMPORT Package Models
# ==========================================

VALID_SCAN_MODES = {"FULL_SCAN", "DEEP_FULL_SCAN", "VENDOR_DEEP_DIVE", "MISSED_BENEFIT_REVIEW"}
VALID_SCAN_STATUSES = {"PUBLIC_COMPLETE", "OVERALL_PARTIAL", "SCAN_INCOMPLETE"}
VALID_BASELINE_ACTIONS = {"BUILD_INITIAL_BASELINE", "UPDATE_EXISTING_BASELINE"}

class ScanResultMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scan_id: str
    scan_mode: str
    context_baseline_revision: int
    generated_at: str
    scan_statuses: List[str]
    baseline_action: str = "UPDATE_EXISTING_BASELINE"
    summary_notes: Optional[str] = ""

    @field_validator("scan_mode")
    @classmethod
    def validate_scan_mode(cls, v: str) -> str:
        if v not in VALID_SCAN_MODES:
            raise ValueError(f"Invalid scan_mode: {v}")
        return v

    @field_validator("scan_statuses")
    @classmethod
    def validate_scan_statuses(cls, v: List[str]) -> List[str]:
        for s in v:
            if s not in VALID_SCAN_STATUSES:
                raise ValueError(f"Invalid scan_status: {s}")
        return v

    @field_validator("baseline_action")
    @classmethod
    def validate_baseline_action(cls, v: str) -> str:
        if v not in VALID_BASELINE_ACTIONS:
            raise ValueError(f"Invalid baseline_action: {v}")
        return v

# Benefit Operations
class BenefitChangeOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str  # CREATE, UPDATE, CONFIRM_NO_CHANGE
    local_ref: Optional[str] = None
    benefit_id: Optional[str] = None
    record: Optional[BenefitRecord] = None
    change_type: Optional[str] = None
    patch: Optional[Dict[str, Any]] = None
    last_checked: Optional[str] = None
    next_review_date: Optional[str] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)

# Lead Operations
class LeadChangeOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str  # CREATE, UPDATE, RESOLVE_TO_BENEFIT, REJECT
    local_ref: Optional[str] = None
    lead_id: Optional[str] = None
    record: Optional[LeadRecord] = None
    patch: Optional[Dict[str, Any]] = None
    target_benefit_ref: Optional[str] = None
    target_benefit_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)

# Source Updates
class SourceUpdateOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str  # ADD, UPDATE, DEPRECATE
    local_ref: Optional[str] = None
    source_id: Optional[str] = None
    record: Optional[CanonicalSourceItem] = None
    patch: Optional[Dict[str, Any]] = None

class ScanImportPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: str = "0.1"
    benefit_schema_version: str = "1.2.1"
    package_type: Optional[str] = "SCAN_IMPORT"
    scan_result: ScanResultMetadata
    benefit_changes: List[BenefitChangeOperation] = Field(default_factory=list)
    lead_changes: List[LeadChangeOperation] = Field(default_factory=list)
    coverage_events: List[CoverageEventItem] = Field(default_factory=list)
    source_updates: List[SourceUpdateOperation] = Field(default_factory=list)
    manual_check_items: List[ManualCheckItem] = Field(default_factory=list)
    warnings: List[WarningItem] = Field(default_factory=list)
