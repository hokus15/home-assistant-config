"""Support for the ESIOS API Data sensor platform."""
from __future__ import annotations

from datetime import datetime
import logging
from typing import Any, Mapping

from homeassistant.components.sensor import (
    STATE_CLASS_MEASUREMENT,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_change
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import EsiosDataUpdateCoordinator
from .const import DOMAIN
from .esios_data import get_esios_id, is_hourly_price

_LOGGER = logging.getLogger(__name__)
PARALLEL_UPDATES = 1

SENSOR_TYPES: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="PVPC",
        icon="mdi:currency-eur",
        name="PVPC",
        native_unit_of_measurement="€/kWh",
        state_class=STATE_CLASS_MEASUREMENT,
    ),
    SensorEntityDescription(
        key="INYECTION",
        icon="mdi:currency-eur",
        name="Grid inyection Price",
        native_unit_of_measurement="€/kWh",
        state_class=STATE_CLASS_MEASUREMENT,
    ),
    SensorEntityDescription(
        key="CO2_GEN",
        icon="mdi:molecule-co2",
        name="CO2 intensity",
        native_unit_of_measurement="gCO2eq/kWh",
        state_class=STATE_CLASS_MEASUREMENT,
    ),
    SensorEntityDescription(
        key="CO2_FREE",
        icon="mdi:molecule-co2",
        # name="Grid fossil fuel percentage",
        name="Grid CO2 free percentage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=STATE_CLASS_MEASUREMENT,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Config entry example."""
    coordinator: EsiosDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        EsiosSensor(coordinator, description)
        for description in SENSOR_TYPES
        if get_esios_id(description.key) in coordinator.api.enabled_codes
    )


class EsiosSensor(CoordinatorEntity, SensorEntity):
    """An entity using CoordinatorEntity.

    The CoordinatorEntity class provides:
      should_poll
      async_update
      async_added_to_hass
      available

    """

    coordinator: EsiosDataUpdateCoordinator

    def __init__(
        self,
        coordinator: EsiosDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize ESIOS sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._esios_id = get_esios_id(description.key)
        self._state: StateType = None
        self._attrs: Mapping[str, Any] = {}
        self._attr_name = f"ESIOS {description.name}"
        self._attr_device_info = DeviceInfo(
            configuration_url="https://api.esios.ree.es",
            entry_type="service",
            identifiers={(DOMAIN, coordinator.entry_id)},
            manufacturer="REE",
            name="API e·sios",
        )
        self._attr_unique_id = f"{coordinator.name}-{description.key.lower()}"

    async def async_added_to_hass(self) -> None:
        """Handle entity which will be added."""
        if self._esios_id not in self.coordinator.api.enabled_codes:
            _LOGGER.critical(
                f"Adding {self._esios_id} to enabled-codes "
                f"-> {self.coordinator.api.enabled_codes}"
            )
            self.coordinator.api.enabled_codes.append(self._esios_id)
        await super().async_added_to_hass()

        # Update 'state' value in hour changes for hourly price sensors
        if is_hourly_price(self._esios_id):
            self.async_on_remove(
                async_track_time_change(
                    self.hass, self.update_current_price, second=[0], minute=[0]
                )
            )
        _LOGGER.warning("Setup of %s (%s) finished", self.name, self.entity_id)

    async def async_will_remove_from_hass(self) -> None:
        """Handle entity which will be added."""
        # TODO Supports entities being disabled and
        #  leverages Entity.entity_registry_enabled_default
        #  to disable less popular entities (docs)
        #  If the device/service API can remove entities,
        #  the integration should make sure to clean up the entity and device registry.
        if self._esios_id in self.coordinator.api.enabled_codes:
            self.coordinator.api.enabled_codes.remove(self._esios_id)
            _LOGGER.debug(
                f"Removing {self._esios_id} from enabled-codes"
                f" -> {self.coordinator.api.enabled_codes}"
            )
        await super().async_will_remove_from_hass()

    @callback
    def update_current_price(self, now: datetime) -> None:
        """Update the sensor state, by selecting the current price for this hour."""
        self.coordinator.api.state_and_attributes(now, self._esios_id)
        self.async_write_ha_state()

    @property
    def native_value(self) -> StateType:
        """Return the state."""
        self._state = self.coordinator.api.get_state(self._esios_id)
        return self._state

    @property
    def extra_state_attributes(self) -> Mapping[str, Any] | None:
        """Return the state attributes."""
        self._attrs = self.coordinator.api.get_attrs(self._esios_id)
        return self._attrs
