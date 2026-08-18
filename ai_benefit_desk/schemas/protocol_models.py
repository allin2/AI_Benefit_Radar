from typing import List, Optional, Any, Dict
from pydantic import BaseModel, Field, field_validator
from ai_benefit_desk.schemas.benefit_models import BenefitRecord

# Context items
class ScanMetadata(BaseModel):
    scan_id: str
    requested_mode: str
    generated_at: str
    baseline_revision: int
    baseline_state: str  # EMPTY / READY
    protocol_version: str = "0.1"
    benefit_schema_version: str = "1.2.1"

class BenefitIndexItem(BaseModel):
    benefit_id: str
    vendor: str
    product: str
    campaign_name: str
    wallet: Optional[str] = "UNKNOWN"
    status: str
    last_checked: str
    next_review_date: Optional[str] = "UNKNOWN"

class LeadRecord(BaseModel):
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
    benefit_id: str
    action_state: str  # NOT_REVIEWED, INTERESTED, CLAIMED, NOT_ELIGIBLE, SKIPPED
    notes: Optional[str] = ""
    updated_at: Optional[str] = None

class ManualCheckItem(BaseModel):
    manual_check_id: Optional[str] = None
    local_ref: Optional[str] = None
    vendor: str
    product: str
    channel: str  # ACCOUNT, DASHBOARD, APP, DESKTOP, IDE, EMAIL, CHECKOUT, OTHER
    reason: str
    priority: str = "MEDIUM"  # LOW, MEDIUM, HIGH
    suggested_action: str
    status: str = "OPEN"  # OPEN, COMPLETED, DISMISSED
    related_benefit_id: Optional[str] = None
    related_benefit_local_ref: Optional[str] = None
    related_lead_id: Optional[str] = None
    result_notes: Optional[str] = ""

# Scan Context Package
class ScanContextPackage(BaseModel):
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

# Import Operations
class ScanResultMetadata(BaseModel):
    scan_id: str
    requested_mode: str
    actual_scan_mode: str
    baseline_action: str = "INCREMENTAL_UPDATE"  # BUILD_INITIAL_BASELINE / INCREMENTAL_UPDATE
    context_baseline_revision: int
    scan_timestamp: str
    public_scan_status: str  # PUBLIC_COMPLETE / SCAN_INCOMPLETE
    overall_coverage_status: str  # OVERALL_PARTIAL / PUBLIC_COMPLETE
    summary_notes: Optional[str] = ""

class BenefitChangeOperation(BaseModel):
    operation: str  # CREATE, UPDATE, CONFIRM_NO_CHANGE
    local_ref: Optional[str] = None
    benefit_id: Optional[str] = None
    benefit_record: BenefitRecord
    change_summary: Optional[str] = ""
    change_reasons: List[str] = Field(default_factory=list)

class LeadChangeOperation(BaseModel):
    operation: str  # CREATE, UPDATE, RESOLVE_TO_BENEFIT, REJECT
    local_ref: Optional[str] = None
    lead_id: Optional[str] = None
    lead_record: Optional[LeadRecord] = None
    target_benefit_id: Optional[str] = None
    target_benefit_local_ref: Optional[str] = None
    rejection_reason: Optional[str] = None

class SourceUpdateOperation(BaseModel):
    operation: str  # ADD, UPDATE, DEPRECATE
    local_ref: Optional[str] = None
    source_id: Optional[str] = None
    source_record: CanonicalSourceItem

class ScanImportPackage(BaseModel):
    protocol_version: str = "0.1"
    benefit_schema_version: str = "1.2.1"
    package_type: Optional[str] = "SCAN_IMPORT"
    scan_result: ScanResultMetadata
    benefit_changes: List[BenefitChangeOperation] = Field(default_factory=list)
    lead_changes: List[LeadChangeOperation] = Field(default_factory=list)
    coverage_events: List[CoverageEventItem] = Field(default_factory=list)
    source_updates: List[SourceUpdateOperation] = Field(default_factory=list)
    manual_check_items: List[ManualCheckItem] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
