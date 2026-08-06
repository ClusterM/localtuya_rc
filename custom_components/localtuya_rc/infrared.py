"""Expose the Tuya IR hub as an `infrared` adapter emitter entity.

Lets brand device integrations (LG Infrared, Samsung Infrared, ...) send
commands through this hub, alongside the existing `remote` entity. Only
loaded on HA Core >= 2026.4 (see INFRARED_PLATFORM_AVAILABLE in __init__.py).
"""
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.config_entries import ConfigEntry
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import (
    async_track_entity_registry_updated_event,
    async_track_state_change_event,
)

from homeassistant.components.infrared import InfraredCommand, InfraredEmitterEntity

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# tinytuya's raw pulse encoder (Contrib.IRRemoteControlDevice.pulses_to_base64)
# packs each duration as an unsigned 16-bit int.
_MAX_PULSE_DURATION_US = 0xFFFF


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    """Set up the infrared emitter entity for this Tuya IR hub config entry."""
    remote_entity = hass.data.get(DOMAIN, {}).get(entry.entry_id, {}).get("remote_entity")
    if remote_entity is None:
        _LOGGER.debug(
            "Remote entity for entry %s is not available (disabled, or failed"
            " to set up); skipping infrared emitter setup",
            entry.entry_id,
        )
        return

    async_add_entities([TuyaIRInfraredEmitter(remote_entity)])


def _timings_to_pulses(raw_timings):
    """Convert infrared-protocols' signed timings to tinytuya's unsigned pulses.

    tinytuya infers mark/space from position, not sign, so a leading space
    is dropped and same-sign runs are merged before taking abs(). Clamped
    to _MAX_PULSE_DURATION_US since some protocols' repeat-gaps (e.g. NEC's
    ~96ms) overflow tinytuya's 16-bit encoding.

    Raises HomeAssistantError if nothing is left to send.
    """
    merged = []
    for timing in raw_timings:
        if merged and (merged[-1] < 0) == (timing < 0):
            merged[-1] += timing
        else:
            merged.append(timing)

    # Merge first so a run of leading spaces collapses to at most one entry
    # before it's dropped - otherwise a second leading space would land at
    # an even (mark) index and invert the whole frame.
    if merged and merged[0] < 0:
        merged = merged[1:]
    if not merged:
        raise HomeAssistantError("Infrared command produced no timings to send")

    return [min(abs(timing), _MAX_PULSE_DURATION_US) for timing in merged]


class TuyaIRInfraredEmitter(InfraredEmitterEntity):
    """Infrared emitter entity; delegates sends to the wrapped remote entity
    to avoid opening a second connection to the same device."""

    _attr_has_entity_name = True

    def __init__(self, remote_entity):
        super().__init__()
        self._remote = remote_entity
        self._last_available = None
        self._remove_remote_listeners = ()

    @property
    def unique_id(self):
        return f"{self._remote.unique_id}_ir_emitter"

    @property
    def available(self):
        # self._remote.hass is None once the remote entity is removed/disabled.
        return self._remote.hass is not None and self._remote.available

    @property
    def device_info(self):
        return self._remote.device_info

    async def async_added_to_hass(self):
        """Subscribe to the wrapped remote entity's state to refresh availability."""
        await super().async_added_to_hass()
        if self._remote.entity_id:
            self._last_available = self.available
            self._subscribe_to_remote(self._remote.entity_id)
        else:
            _LOGGER.warning(
                "Remote entity has no entity_id yet; %s will not track its availability",
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
        """Re-publish state when the remote entity's availability changes."""
        available = self.available
        if available != self._last_available:
            self._last_available = available
            self.async_write_ha_state()

    @callback
    def _handle_remote_entity_id_change(self, event):
        new_entity_id = event.data.get("entity_id")
        if new_entity_id:
            self._subscribe_to_remote(new_entity_id)
            self.async_write_ha_state()

    async def async_send_command(self, command: InfraredCommand) -> None:
        """Send an IR command through the wrapped remote entity."""
        if not self.available:
            raise HomeAssistantError("IR hub remote entity is unavailable")

        try:
            pulses = _timings_to_pulses(command.get_raw_timings())
        except HomeAssistantError:
            raise
        except Exception as e:
            raise HomeAssistantError(f"Invalid infrared command: {e}") from e

        await self._remote.async_send_ir_pulses(pulses)
