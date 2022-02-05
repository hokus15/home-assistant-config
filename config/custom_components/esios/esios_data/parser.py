"""ESIOS API handler for HomeAssistant. JSON parsing."""
from datetime import datetime
from itertools import groupby
from operator import itemgetter
from typing import Any, Dict

from .const import (
    ESIOS_INDICATOR_CO2_FREE_PERC,
    ESIOS_INDICATOR_CO2_GEN,
    GEOZONE_ID2NAME,
    UTC_TZ,
    EsiosIndicatorData,
    is_hourly_price,
)


def extract_indicator_data(data: Dict[str, Any]) -> EsiosIndicatorData:
    """Parse the contents of a historical indicator series json file."""
    indicator_data = data.pop("indicator")
    unit = "•".join(mag["name"] for mag in indicator_data["magnitud"])
    unit_tiempo = "•".join(mag["name"] for mag in indicator_data["tiempo"])
    unit += f"/{unit_tiempo}"
    if len(indicator_data["geos"]) == 1:
        geo_name = indicator_data["geos"][0]["geo_name"]
        unit += f" ({geo_name})"

    def _parse_dt(ts: str) -> datetime:
        return datetime.fromisoformat(ts).astimezone(UTC_TZ)

    def _value_unit_conversion(value: float) -> float:
        if is_hourly_price(indicator_data["id"]):
            # from €/MWh to €/kWh
            return round(float(value) / 1000.0, 5)
        elif indicator_data["id"] == ESIOS_INDICATOR_CO2_FREE_PERC:
            return round(float(value), 2)
        elif indicator_data["id"] == ESIOS_INDICATOR_CO2_GEN:
            # from tonCO2eq/MW to gCO2eq/kWh
            return round(1000.0 * float(value), 2)
        return value

    value_gen = groupby(
        sorted(indicator_data["values"], key=itemgetter("geo_id")),
        itemgetter("geo_id"),
    )
    parsed_data = {
        GEOZONE_ID2NAME[key]: {
            _parse_dt(item["datetime"]): _value_unit_conversion(item["value"])
            for item in list(group)
        }
        for key, group in value_gen
    }
    return EsiosIndicatorData(
        indicator=indicator_data["id"],
        name=indicator_data["name"],
        short_name=indicator_data["short_name"],
        unit=unit,
        data=parsed_data,
    )
