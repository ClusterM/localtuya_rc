"""Tuya Remote Control integration."""
import logging
import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry):
    """Set up Tuya Remote Control from a config entry."""

    _LOGGER.debug(f"async_setup_entry, entry={entry}")

    # Add the remote control entity
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.REMOTE])

    return True
