"""LocalTuyaIR Remote Control integration."""
import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Tuya Remote Control from a config entry."""
    _LOGGER.debug("Setting up entry")
    # Add the remote control entity
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.REMOTE])

    # Register update listener for options flow
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Unloading")
    return await hass.config_entries.async_unload_platforms(entry, Platform.REMOTE)

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.debug("Options update for %s: %s", entry.entry_id, entry.options)
    await hass.config_entries.async_reload(entry.entry_id)
