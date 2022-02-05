"""The ESIOS API Data integration."""
from __future__ import annotations

import logging
from typing import Any, Mapping

from aiohttp.client_exceptions import ClientError
from async_timeout import timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_TOKEN, CONF_ZONE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import (
    ConfigEntryAuthFailed,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import DOMAIN
from .esios_data import (
    ESIOS_IDS,
    HA_IMPLEMENTED_IDS,
    EsiosApiData,
    EsiosAuthError,
    EsiosIndicatorData,
)

_LOGGER = logging.getLogger(__name__)
PLATFORMS: list[str] = ["sensor"]


def make_esios_api(hass: HomeAssistant, data: Mapping[str, Any]) -> EsiosApiData:
    """Instantiate API handler object."""
    esios_indicators = [
        esios_key
        for esios_key, config_key in zip(ESIOS_IDS, HA_IMPLEMENTED_IDS)
        if data.get(config_key)
    ]
    return EsiosApiData(
        api_token=data[CONF_API_TOKEN],
        zone=data[CONF_ZONE],
        indicators=esios_indicators,
        local_timezone=hass.config.time_zone,
        websession=async_get_clientsession(hass),
    )


async def update_esios_data(api: EsiosApiData) -> Mapping[int, EsiosIndicatorData]:
    """Update data via library."""
    try:
        async with timeout(5):
            return await api.fetch_data()
    except ClientError as err:
        raise UpdateFailed from err
    except EsiosAuthError as err:
        raise ConfigEntryAuthFailed from err


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up ESIOS API Data from a config entry."""
    coordinator = EsiosDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    hass.config_entries.async_setup_platforms(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle options update."""
    if any(
        entry.data.get(attrib) != entry.options.get(attrib)
        for attrib in HA_IMPLEMENTED_IDS
    ):
        # update entry replacing data with modified options
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, **entry.options}
        )
        await hass.config_entries.async_reload(entry.entry_id)


class EsiosDataUpdateCoordinator(
    DataUpdateCoordinator[Mapping[int, EsiosIndicatorData]]
):
    """Class to manage fetching ESIOS data API."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize."""
        self.api = make_esios_api(hass, entry.data)
        update_interval = self.api.update_interval
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=update_interval)
        self._entry = entry
        _LOGGER.debug("Esios API data will be updated every %s", update_interval)

    @property
    def entry_id(self) -> str:
        """Return entry ID."""
        return self._entry.entry_id

    async def _async_update_data(self) -> Mapping[int, EsiosIndicatorData]:
        """Update data via library."""
        return await update_esios_data(self.api)
