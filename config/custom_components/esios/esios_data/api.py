"""ESIOS API handler for HomeAssistant."""
import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any, Dict, List, Mapping, Optional, Union, cast
import zoneinfo

import aiohttp

from .const import (
    ATTRIBUTION,
    ESIOS_BASE_URL,
    ESIOS_HEADERS,
    ESIOS_INDICATOR_PVPC,
    GEOZONES,
    INDICATOR_IS_GEOZONED,
    REFERENCE_TZ,
    UTC_TZ,
    EsiosIndicatorData,
    get_delta_update,
    get_esios_id,
    get_esios_key,
    is_hourly_price,
)
from .parser import extract_indicator_data
from .prices import make_price_sensor_attributes
from .pvpc_tariff import get_current_and_next_tariff_periods

_LOGGER = logging.getLogger(__name__)


class EsiosAuthError(Exception):
    """Custom Exception for unauthorized API requests."""


def _ensure_utc_time(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return datetime(*ts.timetuple()[:6], tzinfo=UTC_TZ)
    elif str(ts.tzinfo) != str(UTC_TZ):
        return ts.astimezone(UTC_TZ)
    return ts


class EsiosApiData:
    """
    Data handler for multiple ESIOS indicators using an auth token.

    - Values are stored in `Dict[datetime, float]`,
    with timestamps in UTC and smaller units like €/kWh or grCO2/kWh
    (from units in MW / tonCO2, etc.)
    """

    def __init__(
        self,
        api_token: str,
        zone: str,
        indicators: List[str],
        websession: aiohttp.ClientSession,
        local_timezone: Union[str, zoneinfo.ZoneInfo] = REFERENCE_TZ,
    ):
        """Set up Esios API handler."""
        self.session = websession
        self.api_token = api_token
        self.geo_zone = zone
        self._local_timezone = zoneinfo.ZoneInfo(str(local_timezone))

        codes = [get_esios_id(ind) for ind in indicators]
        self.enabled_codes = codes
        self.data: Dict[int, EsiosIndicatorData] = {}
        # self.data: Dict[int, Optional[EsiosIndicatorData]] = {
        #     ind: None for ind in codes
        # }
        self.sensor_states: Dict[int, Optional[float]] = {ind: None for ind in codes}
        self.sensor_attributes: Dict[int, Dict[str, Any]] = {ind: {} for ind in codes}
        self.last_update: Dict[int, datetime] = {}
        _LOGGER.debug(
            "Esios setup with variables: %s",
            list(map(get_esios_key, self.enabled_codes)),
        )

    @property
    def update_interval(self) -> timedelta:
        """Get desired update_interval for enabled ESIOS indicators."""
        return min(
            get_delta_update(ind) / (1 if is_hourly_price(ind) else 2)
            for ind in self.enabled_codes
        )

    def _needs_fetch(self, indicator: int, now: datetime) -> bool:
        last_ts = self.last_update.get(indicator)
        if not last_ts:
            return True

        # TODO if price and afternoon -> fetch, else no fetch
        if is_hourly_price(indicator) and now.hour < 19:
            actual_time = now.astimezone(self._local_timezone)
            actual_last_ts = last_ts.astimezone(self._local_timezone)
            if actual_last_ts.date() >= actual_time.date():
                _LOGGER.debug(
                    "Avoid fetch for %s price variable", get_esios_key(indicator)
                )
                return False

        if last_ts + get_delta_update(indicator) > _ensure_utc_time(now):
            _LOGGER.debug("Avoid fetch for %s variable", get_esios_key(indicator))
            return False
        return True

    async def _api_call(
        self,
        indicator: int,
        start_date: datetime,
        end_date: datetime,
    ) -> Optional[EsiosIndicatorData]:
        url = (
            f"{ESIOS_BASE_URL}/indicators/{indicator}"
            f"?start_date={start_date.date()}&end_date={end_date.date()}"
        )
        headers = {
            **ESIOS_HEADERS,
            "Authorization": f"Token token={self.api_token}",
        }
        _LOGGER.debug("Calling to '%s'", url)
        try:
            resp = await self.session.get(url, headers=headers)
            if resp.status < 400:
                data = await resp.json()
                return extract_indicator_data(data)
            elif resp.status in (401, 403):
                _LOGGER.error(
                    "Auth error with '%s' -> Headers:  %s",
                    url,
                    resp.headers,
                )
                raise EsiosAuthError(f"Bad auth token: {resp.status}: {resp.content}")
        except (KeyError, IndexError) as exc:
            _LOGGER.error("Bad try in url: '%s': %s", url, exc)
        _LOGGER.warning("No results for '%s' :(", url)
        return None

    async def fetch_data(self) -> Mapping[int, EsiosIndicatorData]:
        """Make all needed calls to Esios API and process all data."""
        now = datetime.utcnow()
        current_hour = now.replace(microsecond=0, second=0, minute=0)
        # TODO review time intervals for other timezones, adjust by hour?
        start, end = current_hour, current_hour + timedelta(days=2)
        tasks = {
            indicator: self._api_call(indicator, start, end)
            for indicator in self.enabled_codes
            if self._needs_fetch(indicator, now)
        }
        if not tasks:
            _LOGGER.debug(
                "No data to fetch yet (enabled: %s)",
                list(map(get_esios_key, self.enabled_codes)),
            )
            return self.data

        _LOGGER.debug("Fetching data for %s", list(map(get_esios_key, tasks.keys())))
        results = await asyncio.gather(*tasks.values())

        for indicator, last_results in zip(tasks.keys(), results):
            if last_results is None:
                # TODO refine this
                _LOGGER.error("ERROR with %s", get_esios_key(indicator))
                continue

            if indicator not in self.data:
                _LOGGER.debug(
                    "Getting 1st data for esios ind=%s", get_esios_key(indicator)
                )
                self.data[indicator] = cast(EsiosIndicatorData, last_results)
            elif self.data[indicator] != last_results:
                _LOGGER.debug("Getting new data for ind=%s", get_esios_key(indicator))
                self.data[indicator]["data"] = {
                    geozone: {
                        **self.data[indicator]["data"][geozone],
                        **last_results["data"][geozone],
                    }
                    for geozone in last_results["data"].keys()
                }
            else:
                _LOGGER.debug("No new data for ind=%s", get_esios_key(indicator))
                continue

            self.last_update[indicator] = _ensure_utc_time(now)
            self.state_and_attributes(current_hour, indicator)

        return self.data

    def state_and_attributes(self, utc_now: datetime, indicator: int) -> bool:
        """Process sensor attributes and set current state."""
        utc_time = _ensure_utc_time(utc_now.replace(minute=0, second=0, microsecond=0))
        actual_time = utc_time.astimezone(self._local_timezone)
        ind_data = self.data[indicator]
        assert ind_data is not None
        attributes: Dict[str, Any] = {
            "attribution": ATTRIBUTION,
            "Esios name": ind_data["short_name"],
            "Esios code": indicator,
        }
        current_values = ind_data["data"][self._get_geozone_id(indicator)]
        if (
            current_values is not None
            and len(current_values) > 25
            and actual_time.hour < 20
        ):
            # there are 'today' and 'next day' values, but 'today' has expired
            max_age = (
                utc_time.astimezone(REFERENCE_TZ).replace(hour=0).astimezone(UTC_TZ)
            )
            ind_data["data"] = {
                geozone: {
                    key_ts: price
                    for key_ts, price in ind_data["data"][geozone].items()
                    if key_ts >= max_age
                }
                for geozone in ind_data["data"].keys()
            }

        # set current state for indicator
        updated_values = ind_data["data"][self._get_geozone_id(indicator)]
        try:
            if is_hourly_price(indicator):
                self.sensor_states[indicator] = updated_values[utc_time]
                _LOGGER.info(
                    f"Setting state for {get_esios_key(indicator)} "
                    f"-> {self.sensor_states[indicator]}"
                )
            else:
                # historic data series, current value is the last one
                last_ts, last_value = list(updated_values.items())[-1]
                self.sensor_states[indicator] = last_value
                attributes["last_update"] = last_ts.isoformat()
                self.last_update[indicator] = _ensure_utc_time(last_ts)
                _LOGGER.info(
                    f"Setting state for {get_esios_key(indicator)} "
                    f"-> {self.sensor_states[indicator]}"
                    f" (last_ts: {last_ts})"
                )
        except (KeyError, IndexError) as exc:
            _LOGGER.error("%s not found in %s -> %s", utc_time, updated_values, exc)
            self.sensor_states[indicator] = None
            self.sensor_attributes[indicator] = attributes
            return False

        if is_hourly_price(indicator):
            if indicator == ESIOS_INDICATOR_PVPC:
                # add 2.0TD period attributes
                local_time = utc_time.astimezone(self._local_timezone)
                (
                    current_period,
                    next_period,
                    delta,
                ) = get_current_and_next_tariff_periods(
                    local_time, zone_ceuta_melilla=self.geo_zone in GEOZONES[-2:]
                )
                attributes["period"] = current_period
                attributes["next_period"] = next_period
                attributes["hours_to_next_period"] = int(delta.total_seconds()) // 3600
                # price_attrs["available_power"] = (
                #     power_valley if current_period == "P3" else power
                # )
            # generate price attributes
            price_attrs = make_price_sensor_attributes(
                updated_values, utc_time, self._local_timezone
            )

            attributes = {**attributes, **price_attrs}
        else:
            # TODO attributes for other kind of sensors ?
            # values = self.get_values(indicator)
            attributes = {
                **attributes,
                "full_name": ind_data["name"],
                "short_name": ind_data["short_name"],
                "unit": ind_data["unit"],
                # "values": {ts.isoformat(): val for ts, val in values.items()}
            }

        self.sensor_attributes[indicator] = attributes
        return True

    def _get_geozone_id(self, indicator: int) -> str:
        """Prices accessor for multiple ESIOS indicators."""
        # assert indicator in self.data and self.data[indicator] is not None
        # assert self.data[indicator] is not None
        ind_data = self.data[indicator]
        assert ind_data is not None
        geozones = list(ind_data["data"].keys())
        if INDICATOR_IS_GEOZONED[indicator]:
            assert self.geo_zone in geozones
            return self.geo_zone
        assert len(geozones) == 1
        return geozones[0]

    def get_values(self, indicator: int) -> Dict[datetime, float]:
        """Values accessor for multiple ESIOS indicators."""
        # assert indicator in self.data
        ind_data = self.data[indicator]
        assert ind_data is not None
        return ind_data["data"][self._get_geozone_id(indicator)]

    def get_attrs(self, indicator: int) -> Dict[str, Any]:
        """Attributes accessor for multiple ESIOS indicators."""
        # assert indicator in self.sensor_attributes
        return self.sensor_attributes[indicator]

    def get_state(self, indicator: int) -> Optional[float]:
        """State accessor for multiple ESIOS indicators, defaults to PVPC."""
        # assert indicator in self.sensor_states
        return self.sensor_states[indicator]


# if __name__ == "__main__":
#     from pprint import pprint
#
#     esios = EsiosApiData(
#         api_token="5850e7063a8a852f1d245883170fc15628408072d9fe23ef964487d4f1fd9a74",
#         zone="Península",
#         indicators=[
#             "PVPC",
#             "INYECTION",
#             "CO2_GEN",
#             "CO2_FREE",
#         ],
#     )
#     asyncio.run(esios.fetch_data())
#     pprint(esios.get_values(ESIOS_INDICATOR_PVPC))
#     pprint(esios.get_values(ESIOS_INDICATOR_INYECTION_PRICE))
#     pprint(esios.get_state(ESIOS_INDICATOR_PVPC))
#     pprint(esios.get_state(ESIOS_INDICATOR_INYECTION_PRICE))
#     pprint(esios.sensor_states)
#     pprint(esios.sensor_attributes)
