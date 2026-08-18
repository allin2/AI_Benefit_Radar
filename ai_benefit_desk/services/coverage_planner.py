"""Coverage and Scan Planning Service.

Implements Vendor Pool V1.2 and Search Playbook V1.2.2 mandatory and optional
surface requirements for coverage tracking and completion gate validation.
"""

from typing import Optional, Set, Dict, Any, List

# Standard mandatory surface categories from Search Playbook V1.2.2 & Vendor Pool V1.2
MANDATORY_SURFACE_NAMES = {
    # Pricing & Plans
    "PRICING", "OFFICIAL_PRICING", "PLAN", "PLANS", "PRICING_PLANS", "PRICING_PAGE",
    # Signup & Registration
    "SIGNUP", "SIGNUP_LANDING", "REGISTER", "REGISTRATION",
    # Model Economics & API / Free Tiers
    "MODEL_ECONOMICS", "API_PRICING", "API_CREDITS", "FREE_TIER", "CREDITS",
    # Programs (Student, Startup, Open Source, Creator, Developer)
    "PROGRAMS", "STUDENT_STARTUP_PROGRAMS", "DEVELOPER_PROGRAM", "EDUCATION", "STARTUP",
    "RESEARCH_PROGRAM", "CREATOR_PROGRAM", "PARTNER_PROGRAM",
    # Partner Bundles & Cloud Offerings
    "PARTNER_BUNDLE", "CLOUD_PARTNER", "HARDWARE_BUNDLE",
    # Core Landing & Documentation
    "MAIN_PAGE", "HOMEPAGE", "OFFICIAL_HOME", "OFFICIAL_PAGE", "DOCS", "OFFICIAL_DOCS",
    "DOCUMENTATION", "API_DOCS", "BILLING_DOCS", "HELP_FAQ",
    # Console / In-app (Expected BLIND_SPOT if public web cannot observe)
    "BILLING_CONSOLE", "CONSOLE", "HIDDEN_ACCOUNT", "CLIENT_REWARD", "DASHBOARD"
}

# Explicit non-mandatory / optional surface categories
NON_MANDATORY_SURFACE_NAMES = {
    "COMMUNITY_FORUM", "FORUM", "COMMUNITY", "COMMUNITY_POSTS", "REDDIT", "DISCORD",
    "BLOG", "NEWS", "CHANGELOG", "PRESS_RELEASE",
    "THIRD_PARTY_DEAL_SITE", "SOCIAL_MEDIA", "THIRD_PARTY", "UNOFFICIAL_COMMUNITY",
    "PROMOTIONAL_EMAIL", "EXTRA_SURFACE"
}

class CoveragePlanner:
    """Provides coverage planning facts and mandatory surface checks."""

    @classmethod
    def normalize_surface(cls, surface: Optional[str]) -> str:
        if not surface:
            return ""
        # Normalize uppercase, replace hyphens and spaces with underscores
        return surface.strip().upper().replace("-", "_").replace(" ", "_").replace("/", "_")

    @classmethod
    def is_mandatory_surface(
        cls,
        vendor: Optional[str],
        product: Optional[str],
        surface: Optional[str]
    ) -> Optional[bool]:
        """Determines if a given vendor/product/surface is mandatory.

        Returns:
            True: Surface is explicitly mandatory according to Vendor Pool / Playbook.
            False: Surface is explicitly non-mandatory (optional auxiliary).
            None: Surface criticality is UNKNOWN (not explicitly mapped).
        """
        norm_s = cls.normalize_surface(surface)
        if not norm_s:
            return None

        # Exact match
        if norm_s in MANDATORY_SURFACE_NAMES:
            return True
        if norm_s in NON_MANDATORY_SURFACE_NAMES:
            return False

        # Segment match (check if any mandatory or non-mandatory token forms a distinct token)
        for m_name in MANDATORY_SURFACE_NAMES:
            if m_name in norm_s:
                return True

        for nm_name in NON_MANDATORY_SURFACE_NAMES:
            if nm_name in norm_s:
                return False

        return None
