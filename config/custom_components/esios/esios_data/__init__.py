"""
Num requests comparison.

           legacy     with-auth-token
PVPC       2*(24+4)    2 (start + first get of next-day)
Inyection   ---        2 (start + first get of next-day)
CO2/Others  ---        24 * 6 (freq ~10min)
"""

from .api import EsiosApiData, EsiosAuthError
from .const import (
    ESIOS_IDS,
    GEOZONES,
    HA_IMPLEMENTED_IDS,
    EsiosIndicatorData,
    get_esios_id,
    is_hourly_price,
)

__all__ = (
    "ESIOS_IDS",
    "EsiosApiData",
    "EsiosAuthError",
    "EsiosIndicatorData",
    "GEOZONES",
    "get_esios_id",
    "HA_IMPLEMENTED_IDS",
    "is_hourly_price",
)
