from typing import List, Optional
from pydantic import BaseModel, Field, field_validator, ConfigDict
from ai_benefit_desk.utils.date_utils import is_valid_date_or_unknown

VALID_BENEFIT_TYPES = {
    "FREE_MODEL", "FREE_AGENT", "FREE_ACCESS",
    "API_CREDITS", "CODING_CREDITS", "GENERAL_CREDITS",
    "TOKENS", "POINTS", "FREE_QUOTA",
    "SIGNUP_BONUS", "AUTO_GRANT", "CHECKIN", "TASK_REWARD", "REFERRAL_REWARD",
    "SUBSCRIPTION_DISCOUNT", "FIRST_MONTH_DISCOUNT", "ANNUAL_DISCOUNT", "RECHARGE_BONUS",
    "BUNDLED_SUBSCRIPTION",
    "RATE_DISCOUNT", "MODEL_MULTIPLIER", "CACHE_DISCOUNT", "BATCH_DISCOUNT", "OFF_PEAK_DISCOUNT",
    "COMPENSATION", "MIGRATION_BONUS", "WINBACK_OFFER",
    "STUDENT_PROGRAM", "TEACHER_PROGRAM", "RESEARCHER_PROGRAM", "ACADEMIC_PROGRAM",
    "STARTUP_PROGRAM", "OPEN_SOURCE_PROGRAM", "DEVELOPER_PROGRAM", "CREATOR_PROGRAM",
    "HACKATHON",
    "BETA_ACCESS", "EARLY_ACCESS", "DEVELOPER_PREVIEW", "WAITLIST",
    "VOUCHER", "COUPON",
    "OTHER"
}

VALID_UNITS = {
    "CREDITS", "TOKENS", "POINTS", "REQUESTS", "USD", "CNY",
    "PERCENT", "MONTH", "DAY", "ACCESS", "VOUCHER", "UNKNOWN"
}

VALID_RESET_POLICIES = {
    "NONE", "HOURLY", "DAILY", "WEEKLY", "MONTHLY", "CUSTOM", "UNKNOWN"
}

VALID_GRANT_METHODS = {
    "AUTO", "CLAIM", "SIGNUP", "LOGIN", "CHECKIN", "TASK", "REFERRAL",
    "PURCHASE", "RECHARGE", "RENEWAL", "APPLICATION", "INVITE", "LOTTERY", "UNKNOWN"
}

VALID_REGIONS = {"CN", "TW", "US", "GLOBAL", "OTHER", "UNKNOWN"}

VALID_ELIGIBILITY_CLASSES = {
    "ALL_USERS", "NEW_USERS", "CURRENT_PAID", "HISTORICAL_PAID",
    "STUDENT", "TEACHER", "RESEARCHER", "ACADEMIC", "STARTUP",
    "OPEN_SOURCE", "DEVELOPER", "INVITE_ONLY", "ACTIVITY_TARGETED",
    "GRAY_ROLLOUT", "APPLICATION_REQUIRED", "LOTTERY", "CONTRIBUTION_REQUIRED", "UNKNOWN"
}

VALID_YES_NO_UNKNOWN = {"YES", "NO", "UNKNOWN"}
VALID_SOURCE_LEVELS = {"S", "A", "B", "C"}
VALID_VERIFICATION_STATUSES = {"CONFIRMED", "LIKELY", "UNVERIFIED", "DISPUTED"}
VALID_STATUSES = {"ACTIVE", "EXPIRING_SOON", "EXPIRED", "UPCOMING", "WAITLIST", "ENDED", "UNKNOWN"}
VALID_CHANGE_TYPES = {
    "NEW", "NO_CHANGE", "RESTORED", "EXPANDED", "REDUCED", "EXTENDED", "SHORTENED",
    "DISCOUNTED", "PRICE_INCREASED", "ELIGIBILITY_EXPANDED", "ELIGIBILITY_REDUCED",
    "STATUS_CHANGED", "IMPORTANT_RULE_CHANGE", "ENDED", "UNKNOWN"
}
VALID_RISK_LEVELS = {"NONE", "LOW", "MEDIUM", "HIGH", "UNKNOWN"}

class BenefitRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")
    benefit_id: Optional[str] = None
    vendor: str
    product: str = "UNKNOWN"
    linked_vendor: Optional[str] = "UNKNOWN"
    linked_product: Optional[str] = "UNKNOWN"
    campaign_name: str
    benefit_type: str
    benefit_detail: str
    linked_benefit_detail: Optional[str] = "UNKNOWN"
    wallet: Optional[str] = "UNKNOWN"
    amount: Optional[str] = "UNKNOWN"
    unit: Optional[str] = "UNKNOWN"
    reset_policy: Optional[str] = "UNKNOWN"
    grant_method: Optional[str] = "UNKNOWN"
    regions: List[str] = Field(default_factory=lambda: ["UNKNOWN"])
    eligibility: Optional[str] = "UNKNOWN"
    eligibility_class: List[str] = Field(default_factory=lambda: ["UNKNOWN"])
    start_date: Optional[str] = "UNKNOWN"
    end_date: Optional[str] = "UNKNOWN"
    first_seen: str
    last_checked: str
    next_review_date: Optional[str] = "UNKNOWN"
    claim_method: Optional[str] = "UNKNOWN"
    credit_card_required: Optional[str] = "UNKNOWN"
    verification_required: Optional[str] = "UNKNOWN"
    official_source: str
    source_level: str
    verification_status: str
    status: str
    change_type: str = "UNKNOWN"
    account_risk: Optional[str] = "NONE"
    region_risk: Optional[str] = "UNKNOWN"
    compliance_risk: Optional[str] = "NONE"
    notes: Optional[str] = ""

    @field_validator("amount", mode="before")
    @classmethod
    def validate_amount(cls, v) -> str:
        if v is None:
            return "UNKNOWN"
        if isinstance(v, (int, float)):
            if isinstance(v, float) and v.is_integer():
                return str(int(v))
            return str(v)
        if isinstance(v, str):
            val = v.strip()
            if not val or val.upper() == "UNKNOWN":
                return "UNKNOWN"
            try:
                float(val)
                return val
            except ValueError:
                raise ValueError(f"Invalid amount value: '{v}'. Must be a number (e.g. 1000, 12.5) or 'UNKNOWN'.")
        raise ValueError(f"Invalid amount type: {type(v)}. Must be a number or 'UNKNOWN'.")

    @field_validator("benefit_type")
    @classmethod
    def validate_benefit_type(cls, v: str) -> str:
        if v not in VALID_BENEFIT_TYPES:
            raise ValueError(f"Invalid benefit_type: {v}")
        return v


    @field_validator("unit")
    @classmethod
    def validate_unit(cls, v: Optional[str]) -> str:
        val = (v or "UNKNOWN").upper()
        if val not in VALID_UNITS:
            raise ValueError(f"Invalid unit: {val}")
        return val

    @field_validator("reset_policy")
    @classmethod
    def validate_reset_policy(cls, v: Optional[str]) -> str:
        val = (v or "UNKNOWN").upper()
        if val not in VALID_RESET_POLICIES:
            raise ValueError(f"Invalid reset_policy: {val}")
        return val

    @field_validator("grant_method")
    @classmethod
    def validate_grant_method(cls, v: Optional[str]) -> str:
        val = (v or "UNKNOWN").upper()
        if val not in VALID_GRANT_METHODS:
            raise ValueError(f"Invalid grant_method: {val}")
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

    @field_validator("eligibility_class")
    @classmethod
    def validate_eligibility_class(cls, v: List[str]) -> List[str]:
        if not v:
            return ["UNKNOWN"]
        for ec in v:
            if ec not in VALID_ELIGIBILITY_CLASSES:
                raise ValueError(f"Invalid eligibility_class: {ec}")
        return v

    @field_validator("credit_card_required", "verification_required")
    @classmethod
    def validate_yes_no_unknown(cls, v: Optional[str]) -> str:
        val = (v or "UNKNOWN").upper()
        if val not in VALID_YES_NO_UNKNOWN:
            raise ValueError(f"Invalid yes/no/unknown value: {val}")
        return val

    @field_validator("source_level")
    @classmethod
    def validate_source_level(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_SOURCE_LEVELS:
            raise ValueError(f"Invalid source_level: {val}")
        return val

    @field_validator("verification_status")
    @classmethod
    def validate_verification_status(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_VERIFICATION_STATUSES:
            raise ValueError(f"Invalid verification_status: {val}")
        return val

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: str) -> str:
        val = v.upper()
        if val not in VALID_STATUSES:
            raise ValueError(f"Invalid status: {val}")
        return val

    @field_validator("change_type")
    @classmethod
    def validate_change_type(cls, v: Optional[str]) -> str:
        val = (v or "UNKNOWN").upper()
        if val not in VALID_CHANGE_TYPES:
            raise ValueError(f"Invalid change_type: {val}")
        return val

    @field_validator("account_risk", "region_risk", "compliance_risk")
    @classmethod
    def validate_risk(cls, v: Optional[str]) -> str:
        val = (v or "UNKNOWN").upper()
        if val not in VALID_RISK_LEVELS:
            raise ValueError(f"Invalid risk level: {val}")
        return val

    @field_validator("start_date", "end_date", "first_seen", "last_checked", "next_review_date")
    @classmethod
    def validate_dates(cls, v: Optional[str]) -> str:
        val = v or "UNKNOWN"
        if not is_valid_date_or_unknown(val):
            raise ValueError(f"Invalid date format (must be YYYY-MM-DD or UNKNOWN): {val}")
        return val
