from typing import List, Optional, Any, Dict, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator
from ai_benefit_desk.schemas.benefit_models import BenefitRecord, VALID_BENEFIT_TYPES
from ai_benefit_desk.utils.date_utils import is_valid_date_or_unknown, is_valid_timezone_iso8601

# ==========================================
# 0. Protocol Enums Definitions
# ==========================================
VALID_SOURCE_LEVELS = {"S", "A", "B", "C"}
VALID_SOURCE_ROLES = {"PRIMARY", "SUPPORTING", "LEAD"}
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
VALID_COVERAGE_STATES = {
    "CHECKED_FOUND", "CHECKED_NONE", "REVIEW_NOT_DUE",
    "NOT_CHECKED", "BLIND_SPOT", "NOT_APPLICABLE"
}
VALID_SCAN_MODES = {
    "FULL_SCAN", "DEEP_FULL_SCAN", "VENDOR_DEEP_DIVE", "MISSED_BENEFIT_REVIEW"
}
VALID_SCAN_STATUSES = {
    "PUBLIC_COMPLETE", "OVERALL_PARTIAL", "SCAN_INCOMPLETE"
}
VALID_BASELINE_STATES = {
    "EMPTY", "READY"
}
VALID_BASELINE_ACTIONS = {
    "BUILD_INITIAL_BASELINE", "UPDATE_EXISTING_BASELINE"
}
VALID_USER_ACTION_STATES = {
    "NOT_REVIEWED", "INTERESTED", "CLAIMED", "NOT_ELIGIBLE", "SKIPPED"
}
VALID_MANUAL_CHECK_CHANNELS = {
    "ACCOUNT", "DASHBOARD", "APP", "DESKTOP", "IDE", "EMAIL", "CHECKOUT", "OTHER"
}
VALID_MANUAL_CHECK_PRIORITIES = {
    "LOW", "MEDIUM", "HIGH"
}
VALID_MANUAL_CHECK_STATUSES = {
    "OPEN", "COMPLETED", "DISMISSED"
}
VALID_SOURCE_OPERATIONS = {
    "ADD", "UPDATE", "DEPRECATE"
}
VALID_BENEFIT_OPERATIONS = {
    "CREATE", "UPDATE", "CONFIRM_NO_CHANGE"
}
VALID_LEAD_OPERATIONS = {
    "CREATE", "UPDATE", "RESOLVE_TO_BENEFIT", "REJECT"
}
VALID_REGIONS = {
    "CN", "TW", "US", "GLOBAL", "OTHER", "UNKNOWN"
}
VALID_VERIFICATION_STATUSES = {
    "CONFIRMED", "LIKELY", "UNVERIFIED", "DISPUTED"
}
VALID_SOURCE_STATUSES = {
    "ACTIVE", "DEPRECATED"
}
VALID_LEAD_STATUSES = {
    "OPEN", "RESOLVED", "REJECTED"
}
VALID_BENEFIT_STATUSES = {
    "ACTIVE", "EXPIRING_SOON", "EXPIRED", "UPCOMING", "WAITLIST", "ENDED", "UNKNOWN"
}

# ==========================================
# 1. Evidence Model
# ==========================================
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

    @field_validator("checked_at")
    @classmethod
    def validate_checked_at(cls, v: str) -> str:
        if not is_valid_timezone_iso8601(v):
            raise ValueError(f"checked_at must be timezone-aware ISO8601 (e.g. 2026-08-18T19:00:00+08:00): {v}")
        return v

# ==========================================
# 2. Warning Model
# ==========================================
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
    benefit_type: str
    wallet: Optional[str] = "UNKNOWN"
    linked_vendor: Optional[str] = "UNKNOWN"
    linked_product: Optional[str] = "UNKNOWN"
    regions: List[str] = Field(default_factory=lambda: ["UNKNOWN"])
    status: str
    start_date: Optional[str] = "UNKNOWN"
    end_date: Optional[str] = "UNKNOWN"
    last_checked: str
    next_review_date: Optional[str] = "UNKNOWN"

    @field_validator("benefit_type")
    @classmethod
    def validate_benefit_type(cls, v: str) -> str:
        if v not in VALID_BENEFIT_TYPES:
            raise ValueError(f"Invalid benefit_type: {v}")
        return v

    @field_validator("regions")
    @classmethod
    def validate_regions(cls, v: List[str]) -> List[str]:
        if not v:
            return ["UNKNOWN"]
        for r in v:
            if r not in VALID_REGIONS:
                raise ValueError(f"Invalid region: {r}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_BENEFIT_STATUSES:
            raise ValueError(f"Invalid status: {val}")
        return val

    @field_validator("start_date", "end_date", "last_checked", "next_review_date")
    @classmethod
    def validate_dates(cls, v: Optional[str]) -> str:
        val = v or "UNKNOWN"
        if not is_valid_date_or_unknown(val):
            raise ValueError(f"Invalid date format (must be YYYY-MM-DD or UNKNOWN): {val}")
        return val

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

    @field_validator("verification_status")
    @classmethod
    def validate_verification_status(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_VERIFICATION_STATUSES:
            raise ValueError(f"Invalid verification_status: {val}")
        return val

    @field_validator("source_level")
    @classmethod
    def validate_source_level(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_SOURCE_LEVELS:
            raise ValueError(f"Invalid source_level: {val}")
        return val

    @field_validator("regions")
    @classmethod
    def validate_regions(cls, v: List[str]) -> List[str]:
        if not v:
            return ["UNKNOWN"]
        for r in v:
            if r not in VALID_REGIONS:
                raise ValueError(f"Invalid region: {r}")
        return v

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_LEAD_STATUSES:
            raise ValueError(f"Invalid lead status: {val}")
        return val

    @field_validator("first_seen", "last_checked", "next_review_date")
    @classmethod
    def validate_dates(cls, v: Optional[str]) -> str:
        val = v or "UNKNOWN"
        if not is_valid_date_or_unknown(val):
            raise ValueError(f"Invalid date format (must be YYYY-MM-DD or UNKNOWN): {val}")
        return val

class CoverageEventItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    coverage_id: Optional[str] = None
    scan_id: Optional[str] = None
    vendor: str
    product: str
    wallet: Optional[str] = "UNKNOWN"
    surface: str
    region: str
    coverage_state: str
    scan_observed_at: str
    actual_checked_at: Optional[str] = None
    next_review_at: Optional[str] = "UNKNOWN"
    source_id: Optional[str] = None
    basis_coverage_id: Optional[str] = None
    notes: Optional[str] = ""

    @field_validator("coverage_state")
    @classmethod
    def validate_coverage_state(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_COVERAGE_STATES:
            raise ValueError(f"Invalid coverage_state: {val}")
        return val

    @field_validator("region")
    @classmethod
    def validate_region(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_REGIONS:
            raise ValueError(f"Invalid region: {val}")
        return val

    @field_validator("scan_observed_at")
    @classmethod
    def validate_scan_observed_at(cls, v: str) -> str:
        if not is_valid_timezone_iso8601(v):
            raise ValueError(f"Coverage scan_observed_at must be timezone-aware ISO8601 (e.g. 2026-08-18T19:00:00+08:00): {v}")
        return v

    @field_validator("actual_checked_at")
    @classmethod
    def validate_actual_checked_at(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "UNKNOWN":
            if not is_valid_timezone_iso8601(v):
                raise ValueError(f"Coverage actual_checked_at must be timezone-aware ISO8601 (e.g. 2026-08-18T19:00:00+08:00): {v}")
        return v

    @field_validator("next_review_at")
    @classmethod
    def validate_next_review_at(cls, v: Optional[str]) -> str:
        val = v or "UNKNOWN"
        if not is_valid_date_or_unknown(val):
            raise ValueError(f"Invalid date format (must be YYYY-MM-DD or UNKNOWN): {val}")
        return val

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
    status: str = "ACTIVE"
    last_verified_at: Optional[str] = None

    @field_validator("source_level")
    @classmethod
    def validate_source_level(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_SOURCE_LEVELS:
            raise ValueError(f"Invalid source_level: {val}")
        return val

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_SOURCE_STATUSES:
            raise ValueError(f"Invalid source status: {val}")
        return val

    @field_validator("last_verified_at")
    @classmethod
    def validate_last_verified_at(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "" and v.upper() != "UNKNOWN":
            if not is_valid_timezone_iso8601(v):
                raise ValueError(f"last_verified_at must be timezone-aware ISO8601 (e.g. 2026-08-18T19:00:00+08:00): {v}")
        return v

class UserBenefitStateItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    benefit_id: str
    action_state: str
    notes: Optional[str] = ""
    updated_at: Optional[str] = None

    @field_validator("action_state")
    @classmethod
    def validate_action_state(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_USER_ACTION_STATES:
            raise ValueError(f"Invalid action_state: {val}")
        return val

    @field_validator("updated_at")
    @classmethod
    def validate_updated_at(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "":
            if not is_valid_timezone_iso8601(v):
                raise ValueError(f"updated_at must be timezone-aware ISO8601: {v}")
        return v

class ManualCheckItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    local_ref: Optional[str] = None
    manual_check_id: Optional[str] = None
    vendor: str
    product: str
    channel: str
    reason: str
    priority: str = "MEDIUM"
    suggested_action: str
    status: str = "OPEN"
    related_benefit_id: Optional[str] = None
    related_lead_id: Optional[str] = None
    result_notes: Optional[str] = ""

    @field_validator("channel")
    @classmethod
    def validate_channel(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_MANUAL_CHECK_CHANNELS:
            raise ValueError(f"Invalid channel: {val}")
        return val

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_MANUAL_CHECK_PRIORITIES:
            raise ValueError(f"Invalid priority: {val}")
        return val

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_MANUAL_CHECK_STATUSES:
            raise ValueError(f"Invalid manual check status: {val}")
        return val

# ==========================================
# 4. SCAN_CONTEXT Package Models
# ==========================================

class ScanMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scan_id: str
    generated_at: str
    baseline_revision: int
    baseline_state: str
    regions: List[str] = Field(default_factory=lambda: ["CN", "TW", "US", "GLOBAL"])
    requested_mode: str = "FULL_SCAN"
    protocol_version: str = "0.1"
    benefit_schema_version: str = "1.2.1"

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, v: str) -> str:
        if not is_valid_timezone_iso8601(v):
            raise ValueError(f"generated_at must be timezone-aware ISO8601 (e.g. 2026-08-18T19:00:00+08:00): {v}")
        return v

    @field_validator("baseline_state")
    @classmethod
    def validate_baseline_state(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_BASELINE_STATES:
            raise ValueError(f"Invalid baseline_state: {val}")
        return val

    @field_validator("requested_mode")
    @classmethod
    def validate_requested_mode(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_SCAN_MODES:
            raise ValueError(f"Invalid requested_mode: {val}")
        return val

    @field_validator("regions")
    @classmethod
    def validate_regions(cls, v: List[str]) -> List[str]:
        if not v:
            return ["UNKNOWN"]
        for r in v:
            if r not in VALID_REGIONS:
                raise ValueError(f"Invalid region: {r}")
        return v

class ScanContextPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: str = "0.1"
    benefit_schema_version: str = "1.2.1"
    package_type: Literal["SCAN_CONTEXT"] = "SCAN_CONTEXT"
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

class ScanResultMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scan_id: str
    scan_mode: str
    context_baseline_revision: int
    generated_at: str
    scan_statuses: List[str]
    baseline_action: str = "UPDATE_EXISTING_BASELINE"
    summary_notes: Optional[str] = ""

    @field_validator("generated_at")
    @classmethod
    def validate_generated_at(cls, v: str) -> str:
        if not is_valid_timezone_iso8601(v):
            raise ValueError(f"generated_at must be timezone-aware ISO8601 (e.g. 2026-08-18T19:00:00+08:00): {v}")
        return v

    @field_validator("scan_mode")
    @classmethod
    def validate_scan_mode(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_SCAN_MODES:
            raise ValueError(f"Invalid scan_mode: {val}")
        return val

    @field_validator("scan_statuses")
    @classmethod
    def validate_scan_statuses(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("scan_statuses cannot be empty")
        res = []
        for s in v:
            val = s.upper()
            if val not in VALID_SCAN_STATUSES:
                raise ValueError(f"Invalid scan_status: {val}")
            res.append(val)
        return res

    @field_validator("baseline_action")
    @classmethod
    def validate_baseline_action(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_BASELINE_ACTIONS:
            raise ValueError(f"Invalid baseline_action: {val}")
        return val

# Benefit Operations
class BenefitChangeOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str
    local_ref: Optional[str] = None
    benefit_id: Optional[str] = None
    record: Optional[BenefitRecord] = None
    change_type: Optional[str] = None
    patch: Optional[Dict[str, Any]] = None
    last_checked: Optional[str] = None
    next_review_date: Optional[str] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_BENEFIT_OPERATIONS:
            raise ValueError(f"Invalid benefit operation: {val}")
        return val

    @field_validator("last_checked", "next_review_date")
    @classmethod
    def validate_dates(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v != "":
            if not is_valid_date_or_unknown(v):
                raise ValueError(f"Invalid date format (must be YYYY-MM-DD or UNKNOWN): {v}")
        return v

# Lead Operations
class LeadChangeOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str
    local_ref: Optional[str] = None
    lead_id: Optional[str] = None
    record: Optional[LeadRecord] = None
    patch: Optional[Dict[str, Any]] = None
    target_benefit_ref: Optional[str] = None
    target_benefit_id: Optional[str] = None
    rejection_reason: Optional[str] = None
    evidence: List[EvidenceItem] = Field(default_factory=list)

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_LEAD_OPERATIONS:
            raise ValueError(f"Invalid lead operation: {val}")
        return val

# Source Updates
class SourceUpdateOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: str
    local_ref: Optional[str] = None
    source_id: Optional[str] = None
    record: Optional[CanonicalSourceItem] = None
    patch: Optional[Dict[str, Any]] = None

    @field_validator("operation")
    @classmethod
    def validate_operation(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_SOURCE_OPERATIONS:
            raise ValueError(f"Invalid source operation: {val}")
        return val

class ScanImportPackage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    protocol_version: str = "0.1"
    benefit_schema_version: str = "1.2.1"
    package_type: Literal["SCAN_IMPORT"] = "SCAN_IMPORT"
    scan_result: ScanResultMetadata
    benefit_changes: List[BenefitChangeOperation] = Field(default_factory=list)
    lead_changes: List[LeadChangeOperation] = Field(default_factory=list)
    coverage_events: List[CoverageEventItem] = Field(default_factory=list)
    source_updates: List[SourceUpdateOperation] = Field(default_factory=list)
    manual_check_items: List[ManualCheckItem] = Field(default_factory=list)
    warnings: List[WarningItem] = Field(default_factory=list)

