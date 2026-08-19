"""Vendor Pool V1.2 Runtime Configuration.

This module is the single source of truth for Vendor/Product-specific
mandatory surface requirements and forced early review signals.

Data is derived from:
- Vendor Pool V1.2 (Final)
- Search Playbook V1.2.2 (Final)
- AI 福利监控规则 V1.2.1
"""
from typing import Dict, List, Optional, Set
from enum import Enum


class CoverageCriticality(Enum):
    """Three-state coverage criticality."""
    MANDATORY = "MANDATORY"
    OPTIONAL = "OPTIONAL"
    UNKNOWN = "UNKNOWN"


class ForcedReviewSignal:
    """A forced early review signal that overrides REVIEW_NOT_DUE."""
    def __init__(self, vendor: str, product: str, surface: str, region: str, reason: str):
        self.vendor = vendor
        self.product = product
        self.surface = surface
        self.region = region
        self.reason = reason

    @property
    def coverage_key(self) -> tuple:
        return (self.vendor, self.product, self.surface, self.region)


# =============================================================================
# Vendor Pool V1.2 - Vendor/Product Mandatory Surface Registry
# =============================================================================
# Key: (vendor, product) -> set of mandatory surface names (normalized uppercase)
# These surfaces MUST be checked in a FULL_SCAN / DEEP_FULL_SCAN.
# NOT_CHECKED on any of these surfaces requires SCAN_INCOMPLETE.

VENDOR_PRODUCT_MANDATORY_SURFACES: Dict[tuple, Set[str]] = {
    # --- OpenAI ---
    ("OpenAI", "ChatGPT"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "MODEL_ECONOMICS", "PROGRAMS", "PARTNER_BUNDLE",
        "REFERRAL", "REGION", "HIDDEN_ACCOUNT",
    },
    ("OpenAI", "OpenAI API"): {
        "PRICING", "MODEL_ECONOMICS", "PROGRAMS",
        "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
    },
    # --- Anthropic ---
    ("Anthropic", "Claude"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "MODEL_ECONOMICS", "PROGRAMS", "PARTNER_BUNDLE",
    },
    ("Anthropic", "Claude Code"): {
        "PRICING", "PROGRAMS", "DOCS", "PARTNER_BUNDLE",
    },
    ("Anthropic", "Anthropic API"): {
        "PRICING", "MODEL_ECONOMICS", "PROGRAMS",
        "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
    },
    # --- Google ---
    ("Google", "Gemini"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "MODEL_ECONOMICS", "PROGRAMS", "PARTNER_BUNDLE",
    },
    ("Google", "Google AI Studio"): {
        "PRICING", "MODEL_ECONOMICS", "PROGRAMS",
        "BILLING_CONSOLE", "DOCS",
    },
    ("Google", "Vertex AI"): {
        "PRICING", "MODEL_ECONOMICS", "PROGRAMS",
        "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
    },
    # --- Microsoft ---
    ("Microsoft", "Copilot"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "PROGRAMS", "PARTNER_BUNDLE",
    },
    ("Microsoft", "Azure OpenAI"): {
        "PRICING", "MODEL_ECONOMICS", "PROGRAMS",
        "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
    },
    ("Microsoft", "GitHub Copilot"): {
        "PRICING", "SUBSCRIPTION", "PROGRAMS",
        "PARTNER_BUNDLE", "DOCS",
    },
    # --- ByteDance ---
    ("ByteDance", "Doubao"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "MODEL_ECONOMICS", "PROGRAMS",
    },
    ("ByteDance", "Volcengine Ark"): {
        "PRICING", "MODEL_ECONOMICS", "PROGRAMS",
        "BILLING_CONSOLE", "DOCS",
    },
    # --- Alibaba ---
    ("Alibaba", "Tongyi Qianwen"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "MODEL_ECONOMICS", "PROGRAMS",
    },
    ("Alibaba", "Alibaba Cloud Model Studio"): {
        "PRICING", "MODEL_ECONOMICS", "PROGRAMS",
        "BILLING_CONSOLE", "DOCS",
    },
    # --- Tencent ---
    ("Tencent", "Yuanbao"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "MODEL_ECONOMICS", "PROGRAMS",
    },
    # --- TRAE ---
    ("TRAE", "TRAE CN"): {
        "CLIENT_REWARD", "PRICING", "PROGRAMS",
    },
    ("TRAE", "TRAE IDE"): {
        "CLIENT_REWARD", "PRICING", "PROGRAMS",
    },
    # --- Cursor ---
    ("Cursor", "Cursor"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "PROGRAMS",
    },
    # --- Windsurf ---
    ("Windsurf", "Windsurf"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "PROGRAMS",
    },
    # --- DeepSeek ---
    ("DeepSeek", "DeepSeek"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "MODEL_ECONOMICS",
    },
    ("DeepSeek", "DeepSeek API"): {
        "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS",
    },
    # --- xAI ---
    ("xAI", "Grok"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "MODEL_ECONOMICS", "PROGRAMS",
    },
    ("xAI", "xAI API"): {
        "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS",
    },
    # --- Perplexity ---
    ("Perplexity", "Perplexity"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "PROGRAMS", "REFERRAL",
    },
    # --- Zhipu ---
    ("Zhipu", "ChatGLM"): {
        "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        "MODEL_ECONOMICS",
    },
    ("Zhipu", "Zhipu API"): {
        "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS",
    },
}

# Explicitly optional (never mandatory) surface categories
EXPLICITLY_OPTIONAL_SURFACES: Set[str] = {
    "COMMUNITY_FORUM", "FORUM", "COMMUNITY", "COMMUNITY_POSTS",
    "REDDIT", "DISCORD",
    "BLOG", "NEWS", "CHANGELOG", "PRESS_RELEASE",
    "THIRD_PARTY_DEAL_SITE", "SOCIAL_MEDIA", "THIRD_PARTY",
    "UNOFFICIAL_COMMUNITY", "PROMOTIONAL_EMAIL", "EXTRA_SURFACE",
}


class VendorPoolConfig:
    """Runtime interface to Vendor Pool V1.2 data."""

    @staticmethod
    def normalize_surface(surface: Optional[str]) -> str:
        if not surface:
            return ""
        return surface.strip().upper().replace("-", "_").replace(" ", "_").replace("/", "_")

    @classmethod
    def get_mandatory_surfaces(cls, vendor: str, product: str) -> Optional[Set[str]]:
        """Return the set of mandatory surfaces for a vendor/product pair.
        Returns None if the vendor/product is not registered in Vendor Pool."""
        return VENDOR_PRODUCT_MANDATORY_SURFACES.get((vendor, product))

    @classmethod
    def get_coverage_criticality(
        cls, vendor: str, product: str, surface: str
    ) -> CoverageCriticality:
        """Determine coverage criticality for a specific vendor/product/surface.

        Returns:
            MANDATORY: Surface is in vendor/product mandatory set.
            OPTIONAL: Surface is in explicitly optional set.
            UNKNOWN: Surface criticality cannot be determined.
        """
        norm_s = cls.normalize_surface(surface)
        if not norm_s:
            return CoverageCriticality.UNKNOWN

        # Check vendor/product-specific mandatory surfaces
        mandatory_set = VENDOR_PRODUCT_MANDATORY_SURFACES.get((vendor, product))
        if mandatory_set is not None:
            if norm_s in mandatory_set:
                return CoverageCriticality.MANDATORY
            # Also check if normalized surface contains a mandatory token
            for m_name in mandatory_set:
                if m_name in norm_s:
                    return CoverageCriticality.MANDATORY

        # Check explicitly optional
        if norm_s in EXPLICITLY_OPTIONAL_SURFACES:
            return CoverageCriticality.OPTIONAL
        for o_name in EXPLICITLY_OPTIONAL_SURFACES:
            if o_name in norm_s:
                return CoverageCriticality.OPTIONAL

        return CoverageCriticality.UNKNOWN

    # =========================================================================
    # Forced Review Signals
    # =========================================================================
    # In-memory store for active forced review signals.
    # In production this could be backed by DB or external config.
    _forced_review_signals: List[ForcedReviewSignal] = []

    @classmethod
    def register_forced_review_signal(cls, signal: ForcedReviewSignal):
        """Register a forced early review signal."""
        cls._forced_review_signals.append(signal)

    @classmethod
    def clear_forced_review_signals(cls):
        """Clear all forced review signals (for testing)."""
        cls._forced_review_signals.clear()

    @classmethod
    def has_forced_review_signal(
        cls, vendor: str, product: str, surface: str, region: str
    ) -> Optional[str]:
        """Check if a forced early review signal exists for this coverage key.

        Returns the reason string if a matching signal exists, None otherwise.
        """
        for sig in cls._forced_review_signals:
            if (sig.vendor == vendor and sig.product == product and
                sig.surface == surface and sig.region == region):
                return sig.reason
        return None
