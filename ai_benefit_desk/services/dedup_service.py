import re
from typing import List, Dict, Any, Optional, Tuple, Set
from sqlalchemy.orm import Session
from ai_benefit_desk.db.models import BenefitModel
from ai_benefit_desk.schemas.benefit_models import BenefitRecord

def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    t = text.lower().strip()
    t = re.sub(r"[\s\-_，。！？、]+", "", t)
    return t

def is_known(val: Any) -> bool:
    if val is None:
        return False
    if isinstance(val, str):
        v_strip = val.strip()
        return v_strip != "" and v_strip.upper() != "UNKNOWN"
    if isinstance(val, list):
        return len(val) > 0 and val != ["UNKNOWN"] and val != []
    return True

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
            if c_vendor_norm == b_vendor_norm and c_prod_norm == b_prod_norm and c_camp_norm == b_camp_norm and c_vendor_norm != "":
                return {
                    "local_ref": local_ref,
                    "existing_benefit_id": b.benefit_id,
                    "existing_campaign_name": b.campaign_name,
                    "existing_vendor": b.vendor,
                    "existing_product": b.product,
                    "is_intra_package": False,
                    "reason": "厂商、产品与活动名称完全匹配",
                    "confidence": "HIGH",
                    "has_conflict": False,
                    "conflicts": {}
                }

            # Check 2: Same Vendor, Benefit Type, Wallet, and Official Source URL (non-UNKNOWN)
            if c_source_norm and c_source_norm != "unknown" and c_source_norm == b_source_norm:
                if (c_vendor_norm == b_vendor_norm and c_vendor_norm != "" and 
                    candidate.benefit_type == b.benefit_type and
                    (c_camp_norm == b_camp_norm or (normalize_text(candidate.wallet) == normalize_text(b.wallet) and candidate.wallet != "UNKNOWN"))):
                    return {
                        "local_ref": local_ref,
                        "existing_benefit_id": b.benefit_id,
                        "existing_campaign_name": b.campaign_name,
                        "existing_vendor": b.vendor,
                        "existing_product": b.product,
                        "is_intra_package": False,
                        "reason": "厂商、福利类型与官方来源 URL 完全一致",
                        "confidence": "HIGH",
                        "has_conflict": False,
                        "conflicts": {}
                    }

            # Check 3: Same Vendor, Product, Benefit Type, and Wallet
            if (c_vendor_norm == b_vendor_norm and c_prod_norm == b_prod_norm and c_vendor_norm != "" and
                candidate.benefit_type == b.benefit_type and 
                normalize_text(candidate.wallet) == normalize_text(b.wallet) and
                candidate.wallet != "UNKNOWN"):
                return {
                    "local_ref": local_ref,
                    "existing_benefit_id": b.benefit_id,
                    "existing_campaign_name": b.campaign_name,
                    "existing_vendor": b.vendor,
                    "existing_product": b.product,
                    "is_intra_package": False,
                    "reason": "厂商、产品、福利类型及 Wallet 资源完全一致",
                    "confidence": "MEDIUM",
                    "has_conflict": False,
                    "conflicts": {}
                }

        return None

    @staticmethod
    def check_two_candidates_duplicate(c1: BenefitRecord, c2: BenefitRecord) -> Optional[Tuple[str, str]]:
        """Compare two candidate records in the same package."""
        c1_v = normalize_text(c1.vendor)
        c1_p = normalize_text(c1.product)
        c1_c = normalize_text(c1.campaign_name)
        c1_s = c1.official_source.strip().lower() if c1.official_source else ""

        c2_v = normalize_text(c2.vendor)
        c2_p = normalize_text(c2.product)
        c2_c = normalize_text(c2.campaign_name)
        c2_s = c2.official_source.strip().lower() if c2.official_source else ""

        # Check 1: Same Vendor, Product, and Campaign Name
        if c1_v == c2_v and c1_p == c2_p and c1_c == c2_c and c1_v != "":
            return ("厂商、产品与活动名称完全匹配", "HIGH")

        # Check 2: Same Vendor, Benefit Type, Wallet, and Official Source URL (non-UNKNOWN)
        if c1_s and c1_s != "unknown" and c1_s == c2_s:
            if (c1_v == c2_v and c1_v != "" and 
                c1.benefit_type == c2.benefit_type and
                (c1_c == c2_c or (normalize_text(c1.wallet) == normalize_text(c2.wallet) and c1.wallet != "UNKNOWN"))):
                return ("厂商、福利类型与官方来源 URL 完全一致", "HIGH")

        # Check 3: Same Vendor, Product, Benefit Type, and Wallet
        if (c1_v == c2_v and c1_p == c2_p and c1_v != "" and
            c1.benefit_type == c2.benefit_type and 
            normalize_text(c1.wallet) == normalize_text(c2.wallet) and
            c1.wallet != "UNKNOWN"):
            return ("厂商、产品、福利类型及 Wallet 资源完全一致", "MEDIUM")

        return None

    @staticmethod
    def detect_candidate_conflicts(c1: BenefitRecord, c2: BenefitRecord) -> Dict[str, Tuple[Any, Any]]:
        """Detect explicit conflicting known facts between two candidates."""
        conflicts = {}
        check_fields = [
            "amount", "end_date", "start_date", "status", "wallet", "unit",
            "reset_policy", "grant_method", "benefit_type", "benefit_detail", "official_source"
        ]
        for f in check_fields:
            v1 = getattr(c1, f, None)
            v2 = getattr(c2, f, None)
            if is_known(v1) and is_known(v2) and str(v1).strip() != str(v2).strip():
                conflicts[f] = (v1, v2)

        if is_known(c1.regions) and is_known(c2.regions) and sorted(c1.regions) != sorted(c2.regions):
            conflicts["regions"] = (c1.regions, c2.regions)

        if is_known(c1.eligibility_class) and is_known(c2.eligibility_class) and sorted(c1.eligibility_class) != sorted(c2.eligibility_class):
            conflicts["eligibility_class"] = (c1.eligibility_class, c2.eligibility_class)

        return conflicts

    @staticmethod
    def detect_candidate_duplicates(db: Session, benefit_changes: List[Any]) -> List[Dict[str, Any]]:
        """Detect both historical (DB) and intra-package duplicates."""
        duplicates = []
        create_ops = [op for op in benefit_changes if op.operation == "CREATE" and op.record]

        # 1. Historical Dedup (candidate vs DB)
        for op in create_ops:
            dup = DedupService.check_duplicate(db, op.record, op.local_ref)
            if dup:
                duplicates.append(dup)

        # 2. Intra-package Dedup (candidate vs candidate in same package)
        for i in range(len(create_ops)):
            op1 = create_ops[i]
            for j in range(i + 1, len(create_ops)):
                op2 = create_ops[j]
                match_info = DedupService.check_two_candidates_duplicate(op1.record, op2.record)
                if match_info:
                    match_reason, confidence = match_info
                    conflicts = DedupService.detect_candidate_conflicts(op1.record, op2.record)
                    duplicates.append({
                        "local_ref": op2.local_ref,
                        "existing_benefit_id": None,
                        "target_local_ref": op1.local_ref,
                        "is_intra_package": True,
                        "existing_campaign_name": op1.record.campaign_name,
                        "existing_vendor": op1.record.vendor,
                        "existing_product": op1.record.product,
                        "reason": f"与本次导入中的另一条候选福利 ({op1.local_ref}) 匹配: {match_reason}",
                        "confidence": confidence,
                        "has_conflict": len(conflicts) > 0,
                        "conflicts": conflicts
                    })

        return duplicates

    @staticmethod
    def build_dedup_update_patch(existing_b: BenefitModel, candidate: BenefitRecord) -> Dict[str, Any]:
        """
        Build an UNKNOWN-safe update patch merging candidate facts into an existing Benefit.
        Guarantees:
        - benefit_id and first_seen are IMMUTABLE.
        - UNKNOWN candidate fields never overwrite known existing values.
        - Explicit known new facts update.
        - change_type cannot be 'NEW'.
        """
        patch: Dict[str, Any] = {}

        # 1. Scalar strings & dates
        scalar_fields = [
            ("campaign_name", candidate.campaign_name, existing_b.campaign_name),
            ("benefit_type", candidate.benefit_type, existing_b.benefit_type),
            ("benefit_detail", candidate.benefit_detail, existing_b.benefit_detail),
            ("linked_vendor", candidate.linked_vendor, existing_b.linked_vendor or "UNKNOWN"),
            ("linked_product", candidate.linked_product, existing_b.linked_product or "UNKNOWN"),
            ("linked_benefit_detail", candidate.linked_benefit_detail, existing_b.linked_benefit_detail or "UNKNOWN"),
            ("wallet", candidate.wallet, existing_b.wallet or "UNKNOWN"),
            ("amount", str(candidate.amount) if candidate.amount is not None else None, str(existing_b.amount or "UNKNOWN")),
            ("unit", candidate.unit, existing_b.unit or "UNKNOWN"),
            ("reset_policy", candidate.reset_policy, existing_b.reset_policy or "UNKNOWN"),
            ("grant_method", candidate.grant_method, existing_b.grant_method or "UNKNOWN"),
            ("eligibility", candidate.eligibility, existing_b.eligibility or "UNKNOWN"),
            ("start_date", candidate.start_date, existing_b.start_date or "UNKNOWN"),
            ("end_date", candidate.end_date, existing_b.end_date or "UNKNOWN"),
            ("claim_method", candidate.claim_method, existing_b.claim_method or "UNKNOWN"),
            ("credit_card_required", candidate.credit_card_required, existing_b.credit_card_required or "UNKNOWN"),
            ("verification_required", candidate.verification_required, existing_b.verification_required or "UNKNOWN"),
            ("official_source", candidate.official_source, existing_b.official_source),
            ("source_level", candidate.source_level, existing_b.source_level),
            ("verification_status", candidate.verification_status, existing_b.verification_status),
            ("status", candidate.status, existing_b.status),
            ("region_risk", candidate.region_risk, existing_b.region_risk or "UNKNOWN"),
        ]

        for fname, cval, eval_curr in scalar_fields:
            if is_known(cval) and str(cval).strip() != str(eval_curr).strip():
                patch[fname] = cval

        # 2. Risk fields (default NONE)
        if is_known(candidate.account_risk) and candidate.account_risk != "NONE" and candidate.account_risk != existing_b.account_risk:
            patch["account_risk"] = candidate.account_risk
        if is_known(candidate.compliance_risk) and candidate.compliance_risk != "NONE" and candidate.compliance_risk != existing_b.compliance_risk:
            patch["compliance_risk"] = candidate.compliance_risk

        # 3. Array fields
        if is_known(candidate.regions) and candidate.regions != existing_b.regions:
            patch["regions"] = candidate.regions
        if is_known(candidate.eligibility_class) and candidate.eligibility_class != existing_b.eligibility_class:
            patch["eligibility_class"] = candidate.eligibility_class

        # 4. Dates & Special fields
        if candidate.last_checked:
            patch["last_checked"] = candidate.last_checked

        if is_known(candidate.next_review_date) and candidate.next_review_date != (existing_b.next_review_date or "UNKNOWN"):
            patch["next_review_date"] = candidate.next_review_date

        if candidate.notes and candidate.notes.strip() and candidate.notes.strip() != (existing_b.notes or "").strip():
            patch["notes"] = candidate.notes.strip()

        # 5. change_type handling (NEVER allow "NEW" on existing benefit)
        if candidate.change_type and candidate.change_type not in ("NEW", "UNKNOWN"):
            patch["change_type"] = candidate.change_type
        elif len(patch) > 0:
            patch["change_type"] = "UNKNOWN"
        else:
            patch["change_type"] = "NO_CHANGE"

        return patch

    @staticmethod
    def merge_intra_package_candidates(primary: BenefitRecord, secondary: BenefitRecord) -> BenefitRecord:
        """Merge secondary candidate facts into primary candidate UNKNOWN-safely."""
        primary_dict = primary.model_dump()
        secondary_dict = secondary.model_dump()

        for k, v2 in secondary_dict.items():
            if k in ("benefit_id", "id", "first_seen"):
                continue
            v1 = primary_dict.get(k)
            if not is_known(v1) and is_known(v2):
                primary_dict[k] = v2

        # Keep earliest first_seen if both known
        if is_known(primary.first_seen) and is_known(secondary.first_seen):
            primary_dict["first_seen"] = min(primary.first_seen, secondary.first_seen)

        return BenefitRecord.model_validate(primary_dict)

    @staticmethod
    def validate_dedup_resolutions(dedup_resolutions: Dict[str, str], benefit_changes: List[Any]):
        """Check for circular resolution references in MERGE_LOCAL."""
        for start_ref, res in dedup_resolutions.items():
            visited = {start_ref}
            curr = res
            while curr and curr.startswith("MERGE_LOCAL:"):
                nxt_ref = curr.split(":", 1)[1]
                if nxt_ref in visited:
                    raise ValueError(f"检测到循环合并引用: {' -> '.join(visited)} -> {nxt_ref}")
                visited.add(nxt_ref)
                curr = dedup_resolutions.get(nxt_ref)

