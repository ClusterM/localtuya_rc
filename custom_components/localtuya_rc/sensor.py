"""Expose the Tuya IR hub's built-in temperature/humidity sensor, if present.

Only some hubs (Tuya category "wnykq") bundle this sensor; see
TuyaRC.temp_humidity_supported in remote.py.
"""
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.helpers.event import (
    async_track_entity_registry_updated_event,
    async_track_state_change_event,
)

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up temperature/humidity sensors for this Tuya IR hub, if supported."""
    remote_entity = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("remote_entity")
    if remote_entity is None:
        _LOGGER.debug(
            "Remote entity for entry %s is not available (disabled, or failed"
            " to set up); skipping sensor setup",
            entry.entry_id,
        )
        return

    if not remote_entity.temp_humidity_supported:
        _LOGGER.debug(
            "Device for entry %s does not report a temperature/humidity"
            " sensor; skipping sensor setup",
            entry.entry_id,
        )
        return

    async_add_entities(
        [
            TuyaIRTemperatureSensor(remote_entity),
            TuyaIRHumiditySensor(remote_entity),
        ]
    )


class _TuyaIRSensorEntity(SensorEntity):
    """Base for sensors that mirror a value cached on the wrapped remote
    entity, to avoid opening a second connection to the same device.

    should_poll=False: the remote entity's own poll refreshes the cached
    value and mirrors it into its extra_state_attributes, which fires a
    state_changed event whenever the value actually changes.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, remote_entity):
        super().__init__()
        self._remote = remote_entity
        self._remove_remote_listeners = ()

    @property
    def available(self):
        # self._remote.hass is None once the remote entity is removed/disabled.
        return self._remote.hass is not None and self._remote.available

    @property
    def device_info(self):
        return self._remote.device_info

    async def async_added_to_hass(self):
        """Subscribe to the wrapped remote entity's state to mirror updates."""
        await super().async_added_to_hass()
        if self._remote.entity_id:
            self._subscribe_to_remote(self._remote.entity_id)
        else:
            _LOGGER.warning(
                "Remote entity has no entity_id yet; %s will not track its state",
                self.entity_id,
            )

    def _subscribe_to_remote(self, entity_id):
        """(Re-)subscribe to the remote entity's state and registry events.

        Re-run on rename (see _handle_remote_entity_id_change) since
        async_track_state_change_event filters on a fixed entity_id.
        """
        for unsub in self._remove_remote_listeners:
            unsub()

        unsub_state = async_track_state_change_event(
            self.hass, [entity_id], self._handle_remote_state_change
        )
        unsub_registry = async_track_entity_registry_updated_event(
            self.hass, entity_id, self._handle_remote_entity_id_change
        )
        self._remove_remote_listeners = (unsub_state, unsub_registry)
        self.async_on_remove(unsub_state)
        self.async_on_remove(unsub_registry)

    @callback
    def _handle_remote_state_change(self, event):
        """Re-publish our own state whenever the remote entity's changes."""
        self.async_write_ha_state()

    @callback
    def _handle_remote_entity_id_change(self, event):
        new_entity_id = event.data.get("entity_id")
        if new_entity_id:
            self._subscribe_to_remote(new_entity_id)
            self.async_write_ha_state()


class TuyaIRTemperatureSensor(_TuyaIRSensorEntity):
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def unique_id(self):
        return f"{self._remote.unique_id}_temperature"

    @property
    def native_value(self):
        return self._remote.temperature


class TuyaIRHumiditySensor(_TuyaIRSensorEntity):
    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE

    @property
    def unique_id(self):
        return f"{self._remote.unique_id}_humidity"

    @property
    def native_value(self):
        return self._remote.humidity
