"""LocalTuyaIR Remote Control integration."""
import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# Detected via the Platform enum, not by importing
# homeassistant.components.infrared directly - that import lazily pulls in
# infrared-protocols, which isn't installed until the infrared component
# itself is set up, so importing it eagerly would break fresh installs.
INFRARED_PLATFORM_AVAILABLE = hasattr(Platform, "INFRARED")


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Tuya Remote Control from a config entry."""
    _LOGGER.debug("Setting up entry")

    # Must finish before "infrared" below: the emitter entity needs the
    # remote entity already registered in hass.data.
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.REMOTE])

    if INFRARED_PLATFORM_AVAILABLE:
        # No Platform.INFRARED enum member on older cores, so forwarded by
        # domain string instead. Isolated in its own try/except so a broken
        # infrared setup (e.g. a requirements-install failure) can't take
        # down the already-working remote entity.
        try:
            await hass.config_entries.async_forward_entry_setups(entry, ["infrared"])
        except Exception:
            _LOGGER.exception("Failed to set up the infrared emitter entity")

    # Register update listener for options flow
    entry.async_on_unload(entry.add_update_listener(update_listener))

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Unload a config entry."""
    _LOGGER.debug("Unloading")
    platforms = [Platform.REMOTE]
    if INFRARED_PLATFORM_AVAILABLE:
        platforms.append("infrared")
    unloaded = await hass.config_entries.async_unload_platforms(entry, platforms)
    if unloaded:
        hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return unloaded

async def update_listener(hass: HomeAssistant, entry: ConfigEntry):
    """Handle options update."""
    _LOGGER.debug("Options update for %s: %s", entry.entry_id, entry.options)
    await hass.config_entries.async_reload(entry.entry_id)
