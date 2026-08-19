"""Vendor Pool V1.2 Runtime Configuration.

Single source of truth for Vendor/Product-specific mandatory surface
requirements. All data derived from canonical Vendor Pool V1.2 (Final),
Search Playbook V1.2.2 (Final), AI 福利监控规则 V1.2.1.

Design principles:
- Mandatory surfaces are per Vendor/Product (never global keyword sets).
- PROGRAMS is NOT an atomic mandatory surface. Individual programs
  (PROGRAM_STUDENT, PROGRAM_STARTUP, REFERRAL, etc.) are atomic.
- Product aliases allow fuzzy matching of real scan data to canonical keys.
- Region-specific products (CN vs International) are preserved separately.
- Forced review signals are persisted on ScanModel (DB) and match full coverage key.
"""
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum


class CoverageCriticality(Enum):
    """Three-state coverage criticality."""
    MANDATORY = "MANDATORY"
    OPTIONAL = "OPTIONAL"
    UNKNOWN = "UNKNOWN"


# =============================================================================
# Product Spec: canonical product key -> mandatory surfaces + aliases
# =============================================================================
class ProductSpec:
    """Defines a canonical product with mandatory surfaces and name aliases."""
    __slots__ = ('canonical_name', 'mandatory_surfaces', 'aliases')

    def __init__(self, canonical_name: str, mandatory_surfaces: Set[str],
                 aliases: Optional[Set[str]] = None):
        self.canonical_name = canonical_name
        self.mandatory_surfaces = mandatory_surfaces
        self.aliases = aliases or set()


# =============================================================================
# Vendor Pool V1.2 — Complete Canonical Registry
# =============================================================================
# Each vendor maps to a list of ProductSpec.
# Mandatory surfaces use ATOMIC granularity.
# Region-specific products (CN / International) are preserved as distinct specs.

VENDOR_REGISTRY: Dict[str, List[ProductSpec]] = {
    # =========================================================================
    # Tier 1: Major AI Platforms
    # =========================================================================
    "OpenAI": [
        ProductSpec("ChatGPT", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS", "PARTNER_BUNDLE",
            "REFERRAL", "REGION", "HIDDEN_ACCOUNT",
            "PROGRAM_STUDENT", "PROGRAM_STARTUP", "PROGRAM_RESEARCH",
            "PROGRAM_DEVELOPER", "PROGRAM_EDUCATION",
            "CREDITS", "WALLET_GRANT",
        }, {"ChatGPT Business", "ChatGPT Business / Enterprise", "Codex / ChatGPT",
            "ChatGPT + Codex + API"}),
        ProductSpec("OpenAI API", {
            "PRICING", "MODEL_ECONOMICS",
            "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
            "PROGRAM_STARTUP", "PROGRAM_RESEARCH",
            "FREE_TIER", "CREDITS",
        }, {"API"}),
    ],
    "Anthropic": [
        ProductSpec("Claude", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS", "PARTNER_BUNDLE",
            "PROGRAM_STARTUP", "PROGRAM_RESEARCH",
            "FREE_TIER",
        }, {"Claude + API"}),
        ProductSpec("Claude Code", {
            "PRICING", "DOCS", "PARTNER_BUNDLE", "FREE_TIER",
        }),
        ProductSpec("Anthropic API", {
            "PRICING", "MODEL_ECONOMICS",
            "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
            "PROGRAM_STARTUP", "PROGRAM_RESEARCH",
            "FREE_TIER",
        }, {"Anthropic API / AI for Science", "Anthropic API / Startup Program"}),
    ],
    "Google": [
        ProductSpec("Gemini", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS", "PARTNER_BUNDLE",
            "PROGRAM_DEVELOPER", "PROGRAM_STARTUP",
            "FREE_TIER", "HIDDEN_ACCOUNT",
        }, {"Gemini + AI Studio + Cloud"}),
        ProductSpec("Google AI Studio", {
            "PRICING", "MODEL_ECONOMICS",
            "BILLING_CONSOLE", "DOCS", "FREE_TIER",
        }, {"Gemini API / Google AI Studio"}),
        ProductSpec("Vertex AI", {
            "PRICING", "MODEL_ECONOMICS",
            "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
            "PROGRAM_STARTUP", "FREE_TIER",
        }),
        ProductSpec("Gemini CLI", {
            "PRICING", "DOCS",
        }),
        ProductSpec("Google Developer Program", {
            "PRICING", "PROGRAM_DEVELOPER",
        }, {"Google Developer Program / AI Pro / Ultra"}),
        ProductSpec("Google for Startups", {
            "PROGRAM_STARTUP",
        }),
    ],
    "Microsoft": [
        ProductSpec("Copilot", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "PARTNER_BUNDLE",
            "PROGRAM_STUDENT", "PROGRAM_DEVELOPER",
        }, {"Copilot + Azure"}),
        ProductSpec("Azure OpenAI", {
            "PRICING", "MODEL_ECONOMICS",
            "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
            "PROGRAM_STARTUP", "FREE_TIER",
        }, {"Microsoft for Startups / Azure"}),
        ProductSpec("Azure for Students", {
            "PRICING", "PROGRAM_STUDENT",
        }),
    ],
    "GitHub": [
        ProductSpec("GitHub Copilot", {
            "PRICING", "SUBSCRIPTION",
            "PARTNER_BUNDLE", "DOCS",
            "PROGRAM_STUDENT", "PROGRAM_OPEN_SOURCE", "PROGRAM_TEACHER",
            "FREE_TIER",
        }, {"Copilot + Models", "Copilot Pro / Pro+ / Max"}),
        ProductSpec("GitHub Copilot Free", {
            "FREE_SIGNUP", "PRICING",
        }),
        ProductSpec("Student Developer Pack", {
            "PROGRAM_STUDENT",
        }, {"Copilot Student", "Student Developer Pack → Camber"}),
    ],

    # =========================================================================
    # Tier 1: Chinese AI Platforms
    # =========================================================================
    "ByteDance": [
        ProductSpec("Doubao", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS", "DAILY_LOGIN", "CREDITS", "ACTIVITY",
        }, {"豆包", "豆包 / Seedance 2.0"}),
        ProductSpec("Volcengine Ark", {
            "PRICING", "MODEL_ECONOMICS",
            "BILLING_CONSOLE", "DOCS", "FREE_TIER", "COUPON", "TOKEN_PLAN",
        }, {"方舟", "方舟 Coding Plan"}),
    ],
    "Alibaba": [
        ProductSpec("Tongyi Qianwen", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS", "DAILY_CHECKIN", "CREDITS",
        }, {"Qwen"}),
        ProductSpec("Alibaba Cloud Model Studio CN", {
            "PRICING", "MODEL_ECONOMICS",
            "BILLING_CONSOLE", "DOCS", "FREE_TIER", "TOKEN_GRANT", "TOKEN_PLAN", "COUPON",
        }, {"百炼 / Model Studio CN", "百炼", "百炼知识库", "Model Studio CN", "Alibaba Cloud Model Studio"}),
        ProductSpec("Model Studio International", {
            "PRICING", "MODEL_ECONOMICS",
            "BILLING_CONSOLE", "DOCS", "FREE_TIER",
        }),
    ],
    "Tencent": [
        ProductSpec("Yuanbao", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS", "ACTIVITY",
        }),
        ProductSpec("WorkBuddy", {
            "PRICING", "CLIENT_REWARD", "CHECKIN", "TASK", "DAILY_LOGIN", "CREDITS", "INVITE",
        }, {"CodeBuddy", "WorkBuddy / CodeBuddy"}),
        ProductSpec("TokenHub CN", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "FREE_TIER", "DISCOUNT",
        }),
        ProductSpec("TokenHub International", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "FREE_TIER",
        }),
        ProductSpec("ADP CN", {
            "PRICING", "PROGRAM_DEVELOPER",
        }),
        ProductSpec("ADP International", {
            "PRICING", "PROGRAM_DEVELOPER",
        }),
    ],
    "DeepSeek": [
        ProductSpec("DeepSeek", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS",
        }),
        ProductSpec("DeepSeek API", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS", "FREE_TIER",
        }),
    ],

    # =========================================================================
    # Tier 1: European / US AI
    # =========================================================================
    "Mistral AI": [
        ProductSpec("Le Chat", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION", "FREE_TIER",
        }, {"Le Chat / Studio", "Le Chat + Studio", "Devstral 2 / Studio"}),
        ProductSpec("Mistral API", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS", "FREE_TIER",
        }, {"Studio"}),
        ProductSpec("Ambassador Program", {
            "PROGRAM_AMBASSADOR",
        }),
        ProductSpec("Education Pro", {
            "PROGRAM_EDUCATION", "PROGRAM_STUDENT", "PROGRAM_TEACHER",
        }),
    ],
    "Meta": [
        ProductSpec("Llama", {
            "DOCS", "FREE_TIER",
        }),
        ProductSpec("Llama Startup Program", {
            "PROGRAM_STARTUP",
        }),
    ],
    "xAI": [
        ProductSpec("Grok", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS", "FREE_TIER",
        }, {"Grok 4.5", "SuperGrok Heavy"}),
        ProductSpec("xAI API", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS", "FREE_TIER",
        }, {"Grok Build"}),
        ProductSpec("Grok + API + Build", {
            "PRICING", "MODEL_ECONOMICS", "FREE_TIER",
        }),
    ],
    "Perplexity": [
        ProductSpec("Perplexity", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "REFERRAL", "STUDENT_DEAL",
        }),
    ],

    # =========================================================================
    # Chinese AI Vendors (Tier 2)
    # =========================================================================
    "Kimi": [
        ProductSpec("Kimi", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION", "REFERRAL", "CREDITS", "ACTIVITY",
        }, {"Moonshot", "Kimi / Moonshot"}),
        ProductSpec("Kimi API", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS", "FREE_TIER", "CREDITS",
        }, {"Moonshot AI / Kimi API"}),
    ],
    "Zhipu": [
        ProductSpec("ChatGLM", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS", "GLM_CODING",
        }, {"GLM Coding", "智谱 GLM / Zhipu AI / GLM Coding"}),
        ProductSpec("Zhipu API", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS", "FREE_TIER", "CREDITS",
        }),
    ],
    "MiniMax": [
        ProductSpec("MiniMax", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION", "MIGRATION", "CREDITS",
        }, {"Subscription Migration"}),
        ProductSpec("Open Platform", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS", "FREE_TIER", "TOKEN_PLAN", "MIGRATION",
        }, {"Open Platform Token Plan"}),
    ],
    "Baidu": [
        ProductSpec("Qianfan", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS", "FREE_TIER", "TOKEN_PLAN", "COUPON",
        }, {"千帆", "千帆 Token 套餐", "百度千帆"}),
    ],
    "StepFun": [
        ProductSpec("StepFun", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "FREE_TIER", "STEP_PLAN",
        }, {"Step Plan", "StepFun / Step Plan", "阶跃星辰 / StepFun / Step Plan"}),
    ],
    "SenseTime": [
        ProductSpec("SenseNova", {
            "PRICING", "MODEL_ECONOMICS", "FREE_TIER", "TOKEN_PLAN",
        }, {"SenseNova Token Plan", "商汤 / SenseNova"}),
    ],
    "Xiaomi": [
        ProductSpec("MiMo", {
            "PRICING", "MODEL_ECONOMICS", "FREE_TIER", "SUBSCRIPTION",
        }, {"MiMo API", "MiMo Subscription", "小米 MiMo"}),
    ],
    "Meituan": [
        ProductSpec("LongCat", {
            "PRICING", "MODEL_ECONOMICS", "FREE_TIER",
        }, {"LongCat API", "美团 / LongCat"}),
    ],
    "Kuaishou": [
        ProductSpec("Kling", {
            "PRICING", "SUBSCRIPTION", "FREE_SIGNUP", "DAILY_CREDITS", "CHECKIN",
        }, {"可灵", "Kling / KAT", "Kling / 可灵"}),
        ProductSpec("KAT-Coder", {
            "PRICING", "FREE_TIER", "INVITE",
        }, {"KAT-Coder-Pro V2.5 → Kilo Code"}),
    ],
    "Huawei Cloud": [
        ProductSpec("AgentArts", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "FREE_TIER",
        }, {"AgentArts / ModelArts"}),
        ProductSpec("Developer Environment", {
            "PRICING", "PROGRAM_DEVELOPER", "FREE_COMPUTE",
        }),
        ProductSpec("OpenClaw", {
            "PRICING", "FREE_TIER",
        }, {"OpenClaw / AI Assistant"}),
    ],
    "Coze": [
        ProductSpec("Coze CN", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION", "CREDITS", "BOT_REWARD", "API_CREDITS",
        }, {"扣子", "扣子 / Coze CN", "Coze CN Subscription"}),
        ProductSpec("Coze Global", {
            "FREE_SIGNUP", "PRICING", "CREDITS", "BOT_REWARD", "API_CREDITS",
        }, {"Coze Global API"}),
    ],

    # =========================================================================
    # Tier 1: Coding / Agent IDEs
    # =========================================================================
    "TRAE": [
        ProductSpec("TRAE CN", {
            "CLIENT_REWARD", "PRICING", "CHECKIN", "TASK", "INVITE", "PROGRAMS", "PROGRAM_DEVELOPER",
        }, {"TRAE CN Subscription", "TraeWork CN"}),
        ProductSpec("TRAE IDE", {
            "CLIENT_REWARD", "PRICING", "CHECKIN", "TASK", "INVITE", "PROGRAMS", "PROGRAM_DEVELOPER",
        }, {"TRAE Agent", "TRAE Global / Agent"}),
    ],
    "Cursor": [
        ProductSpec("Cursor", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION", "PROGRAM_STUDENT", "REFERRAL", "USAGE_LIMITS",
        }, {"Cursor Free"}),
    ],
    "Windsurf": [
        ProductSpec("Windsurf", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION", "PROGRAM_STUDENT", "REFERRAL", "USAGE_LIMITS",
        }, {"Windsurf Free"}),
    ],
    "Qoder": [
        ProductSpec("Qoder", {
            "EVENTS", "CREDITS", "DAILY_RESET", "FREE_CALLS", "SUBSCRIPTION_USAGE",
            "MODEL_DISCOUNT", "MODEL_MULTIPLIER", "ACTIVITY", "ACCOUNT", "PRICING", "FREE_TIER",
        }, {"Qoder Pro Trial"}),
    ],
    "Cline": [
        ProductSpec("Cline", {
            "FREE_SIGNUP", "PRICING", "FREE_TIER",
        }, {"ClinePass"}),
        ProductSpec("Open Source Grant", {
            "PROGRAM_OPEN_SOURCE", "GRANT",
        }),
    ],
    "Continue": [
        ProductSpec("Continue", {
            "FREE_SIGNUP", "PRICING", "DOCS",
        }),
    ],
    "Replit": [
        ProductSpec("Replit", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "REFERRAL", "CREDITS",
        }, {"Starter"}),
        ProductSpec("Startup Program", {
            "PROGRAM_STARTUP", "CREDITS",
        }),
    ],
    "JetBrains": [
        ProductSpec("JetBrains AI", {
            "PRICING", "SUBSCRIPTION", "FREE_TIER", "PROGRAM_STUDENT",
        }, {"AI Pro", "JetBrains AI Free"}),
    ],
    "Warp": [
        ProductSpec("Warp", {
            "FREE_SIGNUP", "PRICING", "REFERRAL",
        }),
    ],
    "Zed": [
        ProductSpec("Zed", {
            "FREE_SIGNUP", "PRICING", "PROGRAM_STUDENT", "PRO_TRIAL",
        }, {"Zed Pro Trial", "Zed Student"}),
    ],
    "OpenCode": [
        ProductSpec("OpenCode", {
            "FREE_SIGNUP", "PRICING", "FREE_TIER",
        }, {"OpenCode Go"}),
    ],
    "Augment Code": [
        ProductSpec("Augment Code", {
            "PRICING", "PROGRAM_OPEN_SOURCE", "FREE_TIER",
        }, {"Open Source"}),
    ],

    # =========================================================================
    # Region-Separated / Community Tools
    # =========================================================================
    "HappyShrimp": [
        ProductSpec("HappyShrimp CN", {
            "PRICING", "FREE_SIGNUP", "CREDITS", "CHECKIN",
        }, {"HappyShrimp", "快乐虾米 / HappyShrimp"}),
        ProductSpec("HappyShrimp International", {
            "PRICING", "FREE_SIGNUP", "CREDITS",
        }),
    ],

    # =========================================================================
    # API / Inference Platforms
    # =========================================================================
    "OpenRouter": [
        ProductSpec("OpenRouter", {
            "PRICING", "MODEL_ECONOMICS", "DOCS", "FREE_TIER",
        }),
    ],
    "Together AI": [
        ProductSpec("Together AI", {
            "PRICING", "MODEL_ECONOMICS", "DOCS", "PROGRAM_STARTUP", "PROGRAM_RESEARCH", "FREE_TIER",
        }, {"Research Credits Program", "Startup Accelerator"}),
    ],
    "Fireworks AI": [
        ProductSpec("Fireworks AI", {
            "PRICING", "MODEL_ECONOMICS", "DOCS", "FREE_TIER",
        }, {"API", "GPU"}),
    ],
    "Groq": [
        ProductSpec("GroqCloud", {
            "PRICING", "MODEL_ECONOMICS", "DOCS", "FREE_TIER",
        }),
    ],
    "Cerebras": [
        ProductSpec("Cerebras", {
            "PRICING", "MODEL_ECONOMICS", "DOCS", "FREE_TIER",
        }, {"Inference API"}),
    ],
    "Hugging Face": [
        ProductSpec("Hugging Face", {
            "PRICING", "MODEL_ECONOMICS", "DOCS", "FREE_TIER",
        }, {"Inference Providers", "ZeroGPU"}),
    ],
    "Cloudflare": [
        ProductSpec("Workers AI", {
            "PRICING", "MODEL_ECONOMICS", "DOCS", "FREE_TIER",
        }),
    ],
    "SambaNova": [
        ProductSpec("SambaNova Cloud", {
            "PRICING", "MODEL_ECONOMICS", "DOCS", "FREE_TIER",
        }),
    ],
    "ModelScope": [
        ProductSpec("ModelScope", {
            "PRICING", "DOCS", "FREE_TIER",
        }, {"ModelScope API"}),
    ],

    # =========================================================================
    # Cloud / Infra
    # =========================================================================
    "AWS": [
        ProductSpec("AWS Activate", {
            "PROGRAM_STARTUP", "CREDITS",
        }),
    ],
    "Oracle": [
        ProductSpec("OCI Free Tier", {
            "FREE_SIGNUP", "PRICING", "FREE_TIER",
        }),
    ],
    "AMD": [
        ProductSpec("AMD Developer Cloud", {
            "PROGRAM_DEVELOPER", "FREE_COMPUTE",
        }, {"AI Developer Program / AMD Developer Cloud"}),
    ],
}

# Vendor name aliases (Chinese names -> canonical)
VENDOR_ALIASES: Dict[str, str] = {
    "字节跳动": "ByteDance",
    "豆包": "ByteDance",
    "火山引擎": "ByteDance",
    "阿里云": "Alibaba",
    "阿里巴巴": "Alibaba",
    "腾讯": "Tencent",
    "腾讯云": "Tencent",
    "腾讯 TokenHub / ADP": "Tencent",
    "百度": "Baidu",
    "百度千帆": "Baidu",
    "智谱": "Zhipu",
    "智谱 GLM": "Zhipu",
    "商汤": "SenseTime",
    "小米": "Xiaomi",
    "小米 MiMo": "Xiaomi",
    "美团": "Meituan",
    "快手": "Kuaishou",
    "华为云": "Huawei Cloud",
    "阶跃星辰": "StepFun",
    "Moonshot": "Kimi",
    "Coze CN": "Coze",
    "Coze Global": "Coze",
    "TRAE CN": "TRAE",
    "TRAE Global": "TRAE",
    "WorkBuddy": "Tencent",
    "CodeBuddy": "Tencent",
    "HappyShrimp CN": "HappyShrimp",
    "HappyShrimp International": "HappyShrimp",
}

# Explicitly optional (never mandatory) surface categories
EXPLICITLY_OPTIONAL_SURFACES: Set[str] = {
    "COMMUNITY_FORUM", "FORUM", "COMMUNITY", "COMMUNITY_POSTS",
    "REDDIT", "DISCORD",
    "BLOG", "NEWS", "CHANGELOG", "PRESS_RELEASE",
    "THIRD_PARTY_DEAL_SITE", "SOCIAL_MEDIA", "THIRD_PARTY",
    "UNOFFICIAL_COMMUNITY", "PROMOTIONAL_EMAIL", "EXTRA_SURFACE",
}


# =============================================================================
# Build lookup indices at module load time
# =============================================================================
# (vendor, product) -> Set[mandatory_surface]
_MANDATORY_INDEX: Dict[Tuple[str, str], Set[str]] = {}
# (vendor, alias) -> canonical product name
_PRODUCT_ALIAS_INDEX: Dict[Tuple[str, str], str] = {}

def _build_indices():
    """Build lookup indices from VENDOR_REGISTRY at module load."""
    for vendor, products in VENDOR_REGISTRY.items():
        for ps in products:
            key = (vendor, ps.canonical_name)
            _MANDATORY_INDEX[key] = ps.mandatory_surfaces
            # Index aliases
            for alias in ps.aliases:
                _PRODUCT_ALIAS_INDEX[(vendor, alias)] = ps.canonical_name
            # Also map through vendor aliases
            for v_alias, v_canonical in VENDOR_ALIASES.items():
                if v_canonical == vendor:
                    alias_key = (v_alias, ps.canonical_name)
                    if alias_key not in _MANDATORY_INDEX:
                        _MANDATORY_INDEX[alias_key] = ps.mandatory_surfaces
                    for p_alias in ps.aliases:
                        _PRODUCT_ALIAS_INDEX[(v_alias, p_alias)] = ps.canonical_name

_build_indices()


class VendorPoolConfig:
    """Runtime interface to Vendor Pool V1.2 data.

    All mandatory surface lookups go through this class.
    Forced review signals are persisted on ScanModel (DB), not process memory.
    """

    @staticmethod
    def normalize_surface(surface: Optional[str]) -> str:
        if not surface:
            return ""
        s = surface.strip().upper().replace("-", "_").replace(" ", "_").replace("/", "_")
        if s == "CHECK_IN":
            return "CHECKIN"
        return s

    @classmethod
    def _resolve_vendor_product(cls, vendor: str, product: str) -> Optional[Tuple[str, str]]:
        """Resolve vendor/product to canonical key, checking aliases."""
        # Direct match
        if (vendor, product) in _MANDATORY_INDEX:
            return (vendor, product)
        # Try product alias
        canonical_product = _PRODUCT_ALIAS_INDEX.get((vendor, product))
        if canonical_product and (vendor, canonical_product) in _MANDATORY_INDEX:
            return (vendor, canonical_product)
        # Try vendor alias
        canonical_vendor = VENDOR_ALIASES.get(vendor)
        if canonical_vendor:
            if (canonical_vendor, product) in _MANDATORY_INDEX:
                return (canonical_vendor, product)
            cp = _PRODUCT_ALIAS_INDEX.get((canonical_vendor, product))
            if cp and (canonical_vendor, cp) in _MANDATORY_INDEX:
                return (canonical_vendor, cp)
        return None

    @classmethod
    def get_mandatory_surfaces(cls, vendor: str, product: str) -> Optional[Set[str]]:
        """Return mandatory surfaces for a vendor/product pair.
        Returns None if the vendor/product is not registered."""
        resolved = cls._resolve_vendor_product(vendor, product)
        if resolved:
            return _MANDATORY_INDEX.get(resolved)
        return None

    @classmethod
    def get_coverage_criticality(
        cls, vendor: str, product: str, surface: str
    ) -> CoverageCriticality:
        """Determine coverage criticality for a specific vendor/product/surface.

        Returns:
            MANDATORY: Surface is in vendor/product mandatory set.
            OPTIONAL: Surface is in explicitly optional set.
            UNKNOWN: Surface criticality cannot be determined.

        Uses exact match for mandatory (no substring). Substring match
        only for explicitly optional surfaces.
        """
        norm_s = cls.normalize_surface(surface)
        if not norm_s:
            return CoverageCriticality.UNKNOWN

        resolved = cls._resolve_vendor_product(vendor, product)
        if resolved:
            mandatory_set = _MANDATORY_INDEX.get(resolved, set())
            # Exact match (including CHECKIN / CHECK_IN alias support)
            if norm_s in mandatory_set:
                return CoverageCriticality.MANDATORY
            if norm_s == "CHECKIN" and "CHECK_IN" in mandatory_set:
                return CoverageCriticality.MANDATORY
            if norm_s == "CHECK_IN" and "CHECKIN" in mandatory_set:
                return CoverageCriticality.MANDATORY

        # Check explicitly optional (exact + substring for optional is fine)
        if norm_s in EXPLICITLY_OPTIONAL_SURFACES:
            return CoverageCriticality.OPTIONAL
        for o_name in EXPLICITLY_OPTIONAL_SURFACES:
            if o_name in norm_s:
                return CoverageCriticality.OPTIONAL

        return CoverageCriticality.UNKNOWN

    # =========================================================================
    # Forced Review Signals — DB-persisted via ScanModel
    # =========================================================================

    @staticmethod
    def build_forced_review_entry(
        vendor: str, product: str, surface: str, region: str, reason: str
    ) -> dict:
        """Build a forced review requirement dict for storage."""
        return {
            "vendor": vendor,
            "product": product,
            "surface": surface,
            "region": region,
            "reason": reason,
        }

    @classmethod
    def check_forced_review_in_requirements(
        cls,
        requirements: List[dict],
        vendor: str, product: str, surface: str, region: str
    ) -> Optional[str]:
        """Check if a forced review requirement exists in a list.
        Returns reason string if found, None otherwise.

        Matching semantics:
        1. Exact match on (vendor, product, surface, region)
        2. Broad match if requirement specifies region="UNKNOWN" or surface="UNKNOWN"
        3. Vendor / product alias resolution.
        """
        canonical_vendor = VENDOR_ALIASES.get(vendor, vendor)

        for req in requirements:
            req_v = req.get("vendor")
            req_p = req.get("product")
            req_s = req.get("surface")
            req_r = req.get("region")

            req_v_canon = VENDOR_ALIASES.get(req_v, req_v)
            if req_v_canon != canonical_vendor:
                continue

            # Product matching
            if req_p and req_p != "UNKNOWN":
                if req_p != product:
                    canon_p = _PRODUCT_ALIAS_INDEX.get((canonical_vendor, product), product)
                    req_canon_p = _PRODUCT_ALIAS_INDEX.get((req_v_canon, req_p), req_p)
                    if canon_p != req_canon_p:
                        continue

            # Surface matching: exact or broad (UNKNOWN)
            norm_surface = cls.normalize_surface(surface)
            norm_req_s = cls.normalize_surface(req_s) if req_s else ""
            surface_match = (
                req_s == "UNKNOWN" or
                req_s == surface or
                norm_req_s == norm_surface
            )

            # Region matching: exact or broad (UNKNOWN)
            # Note: GLOBAL is an explicit region, only UNKNOWN acts as wildcard broad region
            region_match = (req_r == "UNKNOWN" or req_r == region)

            if surface_match and region_match:
                return req.get("reason", "forced review")

        return None

    # =========================================================================
    # Registry Introspection (for parity contract testing)
    # =========================================================================
    @classmethod
    def get_all_registered_vendor_products(cls) -> List[Tuple[str, str]]:
        """Return all registered (vendor, canonical_product) pairs."""
        return sorted(_MANDATORY_INDEX.keys())

    @classmethod
    def get_all_registered_vendors(cls) -> Set[str]:
        """Return all registered vendor names."""
        return set(VENDOR_REGISTRY.keys())
