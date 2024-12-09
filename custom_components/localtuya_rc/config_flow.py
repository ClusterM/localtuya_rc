"""Config flow for the LocalTuyaIR Remote Control integration."""

import logging
import traceback
import voluptuous as vol
import tinytuya
from tinytuya import Contrib

from .const import (
    DOMAIN,
    DEFAULT_FRIENDLY_NAME,
    CONF_LOCAL_KEY,
    CONF_PROTOCOL_VERSION,
    CONF_CONTROL_TYPE
)

from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from homeassistant.const import CONF_NAME, CONF_HOST, CONF_DEVICE_ID

_LOGGER = logging.getLogger(__name__)


class LocalTuyaIRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for LocalTuyaIR Remote Control."""

    VERSION = 1

    def __init__(self, entry = None):
        """Initialize the config flow."""
        self.entry = entry
        # Default config
        self.config = {
            CONF_NAME: DEFAULT_FRIENDLY_NAME,
            CONF_LOCAL_KEY: '',
            CONF_PROTOCOL_VERSION: '3.3'
        }

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        return await self.async_step_pre_scan()

    async def async_step_pre_scan(self, user_input=None):
        """Handle the pre-scan step."""
        errors = {}
        if user_input is not None:
            return await self.async_step_scan()
        return self.async_show_form(
            step_id="pre_scan",
            errors=errors,
            data_schema=vol.Schema({})
        )

    async def async_step_scan(self, user_input=None):
        """Handle the scan step."""
        errors = {}
        if user_input is not None:
            if user_input[CONF_HOST] != '...':
                spl = user_input[CONF_HOST].split(' ', maxsplit=1)
                ip = spl[0]
                id = spl[1][1:-1] if len(spl) >= 2 else None
                if id in self._async_current_ids():
                    return self.async_abort(reason='already_configured')
                self.config[CONF_HOST] = ip
                self.config[CONF_DEVICE_ID] = id
            else:
                self.config[CONF_HOST] = ''
                self.config[CONF_DEVICE_ID] = ''
            return await self.async_step_config()
        try:
            devices = await self.hass.async_add_executor_job(tinytuya.deviceScan)
            for ip in devices:
                device = devices[ip]
                _LOGGER.debug(f"Device found: {device}")
            if len(devices) == 0:
                # Enter IP manually
                self.config[CONF_HOST] = ''
                self.config[CONF_DEVICE_ID] = ''
                return await self.async_step_config(errors={"base": "tuya_not_found"})
            ip_list = [f"{ip} ({devices[ip]["gwId"]})" for ip in devices] + ['...']
            schema = vol.Schema(
            {
                vol.Required(CONF_HOST): vol.In(ip_list)
            })
        except Exception:
            _LOGGER.error(traceback.format_exc())
            return self.async_abort(reason='unknown')
        return self.async_show_form(
            step_id="scan",
            errors=errors,
            data_schema=schema
        )

    def _test_connection(self, dev_id, address, local_key, version):
        _LOGGER.debug(f"Testing connection to {dev_id} at {address} with key {local_key}")
        device = Contrib.IRRemoteControlDevice(dev_id=dev_id, address=address, local_key=local_key, version=version)
        status = device.status()
        _LOGGER.debug(f"Connection test status: {status}, control type detected: {device.control_type}")
        return device, status

    async def async_step_config(self, user_input=None, errors={}):
        """Handle the config step."""
        if user_input is not None:
            # Try to connect to the device
            try:
                device, status = await self.hass.async_add_executor_job(self._test_connection, user_input[CONF_DEVICE_ID], user_input[CONF_HOST], user_input[CONF_LOCAL_KEY], user_input[CONF_PROTOCOL_VERSION])
                self.config[CONF_NAME] = user_input[CONF_NAME]
                self.config[CONF_HOST] = user_input[CONF_HOST]
                self.config[CONF_DEVICE_ID] = user_input[CONF_DEVICE_ID]
                self.config[CONF_LOCAL_KEY] = user_input[CONF_LOCAL_KEY]
                self.config[CONF_PROTOCOL_VERSION] = user_input[CONF_PROTOCOL_VERSION]
                self.config[CONF_CONTROL_TYPE] = device.control_type
                if "Error" in status:
                    errors["base"] = "cannot_connect"
                    _LOGGER.error(f"Devite test error: {status["Error"]}")
                elif not device.control_type:
                    errors["base"] = "no_control_type"
                    _LOGGER.error(f"Devite test error: control type not detected")
                else:
                    # Ok!
                    if self.entry:
                        self.hass.config_entries.async_update_entry(self.entry, data=self.config)
                    return self.async_create_entry(
                        title=self.config[CONF_NAME], data=self.config if not self.entry else {}
                    )
            except Exception as e:
                _LOGGER.error(f"Device test error, exception {type(e)}: {e}", exc_info=True)
                errors["base"] = "cannot_connect"
        schema = vol.Schema({
                vol.Required(CONF_NAME, default=self.config[CONF_NAME]): cv.string,
                vol.Required(CONF_HOST, default=self.config[CONF_HOST]): cv.string,
                vol.Required(CONF_DEVICE_ID, default=self.config[CONF_DEVICE_ID]): cv.string,
                vol.Required(CONF_LOCAL_KEY, default=self.config[CONF_LOCAL_KEY]): cv.string,
                vol.Required(CONF_PROTOCOL_VERSION, default=self.config[CONF_PROTOCOL_VERSION]): vol.In(
                    ["3.1", "3.2", "3.3", "3.4", "3.5"]
                ),
        })
        return self.async_show_form(
            step_id="config",
            errors=errors,
            data_schema=schema
        )
