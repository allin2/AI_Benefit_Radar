"""Vendor Pool V1.2 Runtime Configuration.

Single source of truth for Vendor/Product-specific mandatory surface
requirements. All data derived from canonical Vendor Pool V1.2 (Final),
Search Playbook V1.2.2 (Final), AI 福利监控规则 V1.2.1.

Design principles:
- Mandatory surfaces are per Vendor/Product (never global keyword sets).
- PROGRAMS is NOT an atomic mandatory surface. Individual programs
  (PROGRAM_STUDENT, PROGRAM_STARTUP, REFERRAL, etc.) are atomic.
- Product aliases allow fuzzy matching of real scan data to canonical keys.
- Forced review signals are persisted on ScanModel, not process memory.
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
# Mandatory surfaces use ATOMIC granularity:
#   - No "PROGRAMS" umbrella. Instead: PROGRAM_STUDENT, PROGRAM_STARTUP, etc.
#   - REFERRAL is separate from programs.
#   - PARTNER_BUNDLE, CLIENT_REWARD, HIDDEN_ACCOUNT are individual.

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
        }, {"ChatGPT Business", "ChatGPT Business / Enterprise", "Codex / ChatGPT",
            "ChatGPT + Codex + API"}),
        ProductSpec("OpenAI API", {
            "PRICING", "MODEL_ECONOMICS",
            "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
            "PROGRAM_STARTUP", "PROGRAM_RESEARCH",
        }, {"API"}),
    ],
    "Anthropic": [
        ProductSpec("Claude", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS", "PARTNER_BUNDLE",
            "PROGRAM_STARTUP", "PROGRAM_RESEARCH",
        }, {"Claude + API"}),
        ProductSpec("Claude Code", {
            "PRICING", "DOCS", "PARTNER_BUNDLE",
        }),
        ProductSpec("Anthropic API", {
            "PRICING", "MODEL_ECONOMICS",
            "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
            "PROGRAM_STARTUP", "PROGRAM_RESEARCH",
        }, {"Anthropic API / AI for Science", "Anthropic API / Startup Program"}),
    ],
    "Google": [
        ProductSpec("Gemini", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS", "PARTNER_BUNDLE",
            "PROGRAM_DEVELOPER", "PROGRAM_STARTUP",
        }, {"Gemini + AI Studio + Cloud"}),
        ProductSpec("Google AI Studio", {
            "PRICING", "MODEL_ECONOMICS",
            "BILLING_CONSOLE", "DOCS",
        }, {"Gemini API / Google AI Studio"}),
        ProductSpec("Vertex AI", {
            "PRICING", "MODEL_ECONOMICS",
            "PARTNER_BUNDLE", "BILLING_CONSOLE", "DOCS",
            "PROGRAM_STARTUP",
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
            "PROGRAM_STARTUP",
        }, {"Microsoft for Startups / Azure"}),
        ProductSpec("Azure for Students", {
            "PRICING", "PROGRAM_STUDENT",
        }),
    ],
    "GitHub": [
        ProductSpec("GitHub Copilot", {
            "PRICING", "SUBSCRIPTION",
            "PARTNER_BUNDLE", "DOCS",
            "PROGRAM_STUDENT", "PROGRAM_OPEN_SOURCE",
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
            "MODEL_ECONOMICS",
        }, {"豆包", "豆包 / Seedance 2.0"}),
        ProductSpec("Volcengine Ark", {
            "PRICING", "MODEL_ECONOMICS",
            "BILLING_CONSOLE", "DOCS",
        }, {"方舟", "方舟 Coding Plan"}),
    ],
    "Alibaba": [
        ProductSpec("Tongyi Qianwen", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS",
        }, {"Qwen"}),
        ProductSpec("Alibaba Cloud Model Studio", {
            "PRICING", "MODEL_ECONOMICS",
            "BILLING_CONSOLE", "DOCS",
        }, {"百炼 / Model Studio CN", "百炼", "百炼知识库", "Model Studio CN"}),
        ProductSpec("Model Studio International", {
            "PRICING", "MODEL_ECONOMICS",
            "BILLING_CONSOLE", "DOCS",
        }),
    ],
    "Tencent": [
        ProductSpec("Yuanbao", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS",
        }),
        ProductSpec("WorkBuddy", {
            "PRICING", "CLIENT_REWARD",
        }, {"CodeBuddy", "WorkBuddy / CodeBuddy"}),
        ProductSpec("TokenHub CN", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE",
        }),
        ProductSpec("TokenHub International", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE",
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
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS",
        }),
    ],

    # =========================================================================
    # Tier 1: European / US AI
    # =========================================================================
    "Mistral AI": [
        ProductSpec("Le Chat", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        }, {"Le Chat / Studio", "Le Chat + Studio", "Devstral 2 / Studio"}),
        ProductSpec("Mistral API", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS",
        }, {"Studio"}),
        ProductSpec("Ambassador Program", {
            "PROGRAM_AMBASSADOR",
        }),
        ProductSpec("Education Pro", {
            "PROGRAM_EDUCATION",
        }),
    ],
    "Meta": [
        ProductSpec("Llama", {
            "DOCS",
        }),
        ProductSpec("Llama Startup Program", {
            "PROGRAM_STARTUP",
        }),
    ],
    "xAI": [
        ProductSpec("Grok", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS",
        }, {"Grok 4.5", "SuperGrok Heavy"}),
        ProductSpec("xAI API", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS",
        }, {"Grok Build"}),
        ProductSpec("Grok + API + Build", {
            "PRICING", "MODEL_ECONOMICS",
        }),
    ],
    "Perplexity": [
        ProductSpec("Perplexity", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "REFERRAL",
        }),
    ],

    # =========================================================================
    # Chinese AI Vendors (Tier 2)
    # =========================================================================
    "Kimi": [
        ProductSpec("Kimi", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        }, {"Moonshot", "Kimi / Moonshot"}),
        ProductSpec("Kimi API", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS",
        }, {"Moonshot AI / Kimi API"}),
    ],
    "Zhipu": [
        ProductSpec("ChatGLM", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "MODEL_ECONOMICS",
        }, {"GLM Coding", "智谱 GLM / Zhipu AI / GLM Coding"}),
        ProductSpec("Zhipu API", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS",
        }),
    ],
    "MiniMax": [
        ProductSpec("MiniMax", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        }, {"Subscription Migration"}),
        ProductSpec("Open Platform", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS",
        }, {"Open Platform Token Plan"}),
    ],
    "Baidu": [
        ProductSpec("Qianfan", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE", "DOCS",
        }, {"千帆", "千帆 Token 套餐", "百度千帆"}),
    ],
    "StepFun": [
        ProductSpec("StepFun", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE",
        }, {"Step Plan", "StepFun / Step Plan", "阶跃星辰 / StepFun / Step Plan"}),
    ],
    "SenseTime": [
        ProductSpec("SenseNova", {
            "PRICING", "MODEL_ECONOMICS",
        }, {"SenseNova Token Plan", "商汤 / SenseNova"}),
    ],
    "Xiaomi": [
        ProductSpec("MiMo", {
            "PRICING", "MODEL_ECONOMICS",
        }, {"MiMo API", "MiMo Subscription", "小米 MiMo"}),
    ],
    "Meituan": [
        ProductSpec("LongCat", {
            "PRICING", "MODEL_ECONOMICS",
        }, {"LongCat API", "美团 / LongCat"}),
    ],
    "Kuaishou": [
        ProductSpec("Kling", {
            "PRICING", "SUBSCRIPTION",
        }, {"可灵", "Kling / KAT", "Kling / 可灵"}),
        ProductSpec("KAT-Coder", {
            "PRICING",
        }, {"KAT-Coder-Pro V2.5 → Kilo Code"}),
    ],
    "Huawei Cloud": [
        ProductSpec("AgentArts", {
            "PRICING", "MODEL_ECONOMICS", "BILLING_CONSOLE",
        }, {"AgentArts / ModelArts"}),
        ProductSpec("Developer Environment", {
            "PRICING", "PROGRAM_DEVELOPER",
        }),
        ProductSpec("OpenClaw", {
            "PRICING",
        }, {"OpenClaw / AI Assistant"}),
    ],
    "Coze": [
        ProductSpec("Coze CN", {
            "FREE_SIGNUP", "PRICING",
        }, {"扣子", "扣子 / Coze CN", "Coze CN Subscription"}),
        ProductSpec("Coze Global", {
            "FREE_SIGNUP", "PRICING",
        }, {"Coze Global API"}),
    ],

    # =========================================================================
    # Tier 1: Coding / Agent IDEs
    # =========================================================================
    "TRAE": [
        ProductSpec("TRAE CN", {
            "CLIENT_REWARD", "PRICING",
        }, {"TRAE CN Subscription", "TraeWork CN"}),
        ProductSpec("TRAE IDE", {
            "CLIENT_REWARD", "PRICING",
        }, {"TRAE Agent", "TRAE Global / Agent"}),
    ],
    "Cursor": [
        ProductSpec("Cursor", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        }, {"Cursor Free"}),
    ],
    "Windsurf": [
        ProductSpec("Windsurf", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
        }, {"Windsurf Free"}),
    ],
    "Qoder": [
        ProductSpec("Qoder", {
            "PRICING",
        }, {"Qoder Pro Trial"}),
    ],
    "Cline": [
        ProductSpec("Cline", {
            "FREE_SIGNUP", "PRICING",
        }, {"ClinePass"}),
        ProductSpec("Open Source Grant", {
            "PROGRAM_OPEN_SOURCE",
        }),
    ],
    "Continue": [
        ProductSpec("Continue", {
            "FREE_SIGNUP", "PRICING",
        }),
    ],
    "Replit": [
        ProductSpec("Replit", {
            "FREE_SIGNUP", "PRICING", "SUBSCRIPTION",
            "REFERRAL",
        }, {"Starter"}),
        ProductSpec("Startup Program", {
            "PROGRAM_STARTUP",
        }),
    ],
    "JetBrains": [
        ProductSpec("JetBrains AI", {
            "PRICING", "SUBSCRIPTION",
        }, {"AI Pro", "JetBrains AI Free"}),
    ],
    "Warp": [
        ProductSpec("Warp", {
            "FREE_SIGNUP", "PRICING",
        }),
    ],
    "Zed": [
        ProductSpec("Zed", {
            "FREE_SIGNUP", "PRICING",
        }, {"Zed Pro Trial", "Zed Student"}),
    ],
    "OpenCode": [
        ProductSpec("OpenCode", {
            "FREE_SIGNUP", "PRICING",
        }, {"OpenCode Go"}),
    ],
    "Augment Code": [
        ProductSpec("Augment Code", {
            "PRICING",
        }, {"Open Source"}),
    ],

    # =========================================================================
    # API / Inference Platforms
    # =========================================================================
    "OpenRouter": [
        ProductSpec("OpenRouter", {
            "PRICING", "MODEL_ECONOMICS", "DOCS",
        }),
    ],
    "Together AI": [
        ProductSpec("Together AI", {
            "PRICING", "MODEL_ECONOMICS", "DOCS",
        }, {"Research Credits Program", "Startup Accelerator"}),
    ],
    "Fireworks AI": [
        ProductSpec("Fireworks AI", {
            "PRICING", "MODEL_ECONOMICS", "DOCS",
        }, {"API", "GPU"}),
    ],
    "Groq": [
        ProductSpec("GroqCloud", {
            "PRICING", "MODEL_ECONOMICS", "DOCS",
        }),
    ],
    "Cerebras": [
        ProductSpec("Cerebras", {
            "PRICING", "MODEL_ECONOMICS", "DOCS",
        }, {"Inference API"}),
    ],
    "Hugging Face": [
        ProductSpec("Hugging Face", {
            "PRICING", "MODEL_ECONOMICS", "DOCS",
        }, {"Inference Providers", "ZeroGPU"}),
    ],
    "Cloudflare": [
        ProductSpec("Workers AI", {
            "PRICING", "MODEL_ECONOMICS", "DOCS",
        }),
    ],
    "SambaNova": [
        ProductSpec("SambaNova Cloud", {
            "PRICING", "MODEL_ECONOMICS", "DOCS",
        }),
    ],
    "ModelScope": [
        ProductSpec("ModelScope", {
            "PRICING", "DOCS",
        }, {"ModelScope API"}),
    ],
    "HappyShrimp": [
        ProductSpec("HappyShrimp", {
            "PRICING",
        }, {"快乐虾米 / HappyShrimp"}),
    ],

    # =========================================================================
    # Cloud / Infra
    # =========================================================================
    "AWS": [
        ProductSpec("AWS Activate", {
            "PROGRAM_STARTUP",
        }),
    ],
    "Oracle": [
        ProductSpec("OCI Free Tier", {
            "FREE_SIGNUP", "PRICING",
        }),
    ],
    "AMD": [
        ProductSpec("AMD Developer Cloud", {
            "PROGRAM_DEVELOPER",
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
        return surface.strip().upper().replace("-", "_").replace(" ", "_").replace("/", "_")

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
            # Exact match only for mandatory (prevents PROGRAMS masking atomics)
            if norm_s in mandatory_set:
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
    # These class methods provide the interface. Actual persistence is on
    # ScanModel.forced_review_requirements (JSON column).
    # ValidationService reads from the scan record, not from process memory.

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

    @staticmethod
    def check_forced_review_in_requirements(
        requirements: List[dict],
        vendor: str, product: str, surface: str, region: str
    ) -> Optional[str]:
        """Check if a forced review requirement exists in a list.
        Returns reason string if found, None otherwise."""
        for req in requirements:
            if (req.get("vendor") == vendor and req.get("product") == product and
                req.get("surface") == surface and req.get("region") == region):
                return req.get("reason", "forced review")
        return None

    # =========================================================================
    # Registry Introspection (for completeness testing)
    # =========================================================================
    @classmethod
    def get_all_registered_vendor_products(cls) -> List[Tuple[str, str]]:
        """Return all registered (vendor, canonical_product) pairs."""
        return sorted(_MANDATORY_INDEX.keys())

    @classmethod
    def get_all_registered_vendors(cls) -> Set[str]:
        """Return all registered vendor names."""
        return set(VENDOR_REGISTRY.keys())
