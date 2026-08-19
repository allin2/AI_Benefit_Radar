"""Coverage and Scan Planning Service.

Delegates to VendorPoolConfig for Vendor/Product-specific mandatory
surface requirements per Vendor Pool V1.2 and Search Playbook V1.2.2.
"""

from typing import Optional
from ai_benefit_desk.services.vendor_pool_config import (
    VendorPoolConfig, CoverageCriticality
)


class CoveragePlanner:
    """Provides coverage planning facts and mandatory surface checks.

    Delegates to VendorPoolConfig for Vendor/Product-specific data.
    """

    @classmethod
    def normalize_surface(cls, surface: Optional[str]) -> str:
        return VendorPoolConfig.normalize_surface(surface)

    @classmethod
    def is_mandatory_surface(
        cls,
        vendor: Optional[str],
        product: Optional[str],
        surface: Optional[str]
    ) -> Optional[bool]:
        """Determines if a given vendor/product/surface is mandatory.

        Returns:
            True: Surface is MANDATORY per Vendor Pool.
            False: Surface is explicitly OPTIONAL.
            None: Criticality is UNKNOWN.
        """
        if not vendor or not product:
            return None
        crit = VendorPoolConfig.get_coverage_criticality(vendor, product, surface or "")
        if crit == CoverageCriticality.MANDATORY:
            return True
        elif crit == CoverageCriticality.OPTIONAL:
            return False
        else:
            return None
