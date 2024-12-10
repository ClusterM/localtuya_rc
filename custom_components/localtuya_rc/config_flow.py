"""Config flow for the LocalTuyaIR Remote Control integration."""

import logging
import voluptuous as vol
import tinytuya
from tinytuya import Contrib, Cloud

from .const import (
    DOMAIN,
    DEFAULT_FRIENDLY_NAME,
    CONF_LOCAL_KEY,
    CONF_PROTOCOL_VERSION,
    CONF_CLOUD_INFO
)

from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv
from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_DEVICE_ID,
    CONF_REGION,
    CONF_CLIENT_ID,
    CONF_CLIENT_SECRET
)

_LOGGER = logging.getLogger(__name__)

class LocalTuyaIRConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for LocalTuyaIR Remote Control."""

    VERSION = 1

    def __init__(self, entry = None):
        """Initialize the config flow."""
        # Default config
        self.config = {
            CONF_NAME: DEFAULT_FRIENDLY_NAME,
            CONF_LOCAL_KEY: '',
            CONF_PROTOCOL_VERSION: '3.3',
            CONF_REGION: 'eu',
            CONF_CLIENT_ID: '',
            CONF_CLIENT_SECRET: '',
        }
        self.cloud = False

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        return await self.async_step_method()

    async def async_step_method(self, user_input=None):
        """Handle the method step."""
        # Ask user to to obtain the local key: via the API or enter manually
        return self.async_show_menu(
            step_id="method",
            menu_options=["cloud", "pre_scan"])

    def _get_cloud_devices(self, region, client_id, client_secret):
        cloud = Cloud(region, client_id, client_secret)
        status = cloud.getconnectstatus()
        return cloud, status

    async def async_step_cloud(self, user_input=None):
        """Handle the api step."""
        errors = {}
        if user_input is not None:
            try:
                self.config[CONF_REGION] = user_input[CONF_REGION]
                self.config[CONF_CLIENT_ID] = user_input[CONF_CLIENT_ID]
                self.config[CONF_CLIENT_SECRET] = user_input[CONF_CLIENT_SECRET]
                cloud, status = await self.hass.async_add_executor_job(self._get_cloud_devices, user_input[CONF_REGION], user_input[CONF_CLIENT_ID], user_input[CONF_CLIENT_SECRET])
                if not status:
                    errors["base"] = "cloud_error"
                elif 'Err' in status and status['Err'] == '911':
                    errors["base"] = "cloud_unauthorized"
                else:
                    devices = await self.hass.async_add_executor_job(cloud.getdevices)
                    if not devices:
                        errors["base"] = "cloud_no_devices"
                    else:
                        self.cloud_devices = devices
                        self.cloud = True
                        return await self.async_step_pre_scan()
            except Exception as e:
                _LOGGER.error("Cloud API error: %s", e, exc_info=True)
                errors["base"] = "unknown"
        schema = vol.Schema(
            {
                vol.Required(CONF_REGION, default=self.config[CONF_REGION]): vol.In(["us", "us-e", "eu", "eu-w", "in", "cn"]),
                vol.Required(CONF_CLIENT_ID, default=self.config[CONF_CLIENT_ID]): cv.string,
                vol.Required(CONF_CLIENT_SECRET, default=self.config[CONF_CLIENT_SECRET]): cv.string
            }
        )
        return self.async_show_form(
            step_id="cloud",
            errors=errors,
            data_schema=schema
        )

    async def async_step_pre_scan(self, user_input=None, errors={}):
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
            spl = user_input[CONF_HOST].split(' ', maxsplit=1)
            ip = spl[0]
            self.config[CONF_HOST] = ip
            self.config[CONF_DEVICE_ID] = self.scan_devices[ip]["gwId"]
            if self.cloud:
                for device in self.cloud_devices:
                    if device['id'] == self.config[CONF_DEVICE_ID]:
                        self.cloud_info = device
                        self.config[CONF_NAME] = device['name']
                        self.config[CONF_LOCAL_KEY] = device['key']
                        break
            return await self.async_step_config()
        try:
            self.scan_devices = await self.hass.async_add_executor_job(tinytuya.deviceScan)
            for ip in self.scan_devices:
                device = self.scan_devices[ip]
                _LOGGER.debug("Device found: %s", device)
            if len(self.scan_devices) == 0:
                return await self.async_step_pre_scan(errors={"base": "tuya_not_found"})
            if not self.cloud:
                ip_list = [f"{ip} ({self.scan_devices[ip]["gwId"]})" for ip in self.scan_devices]
            else:
                ip_list = []
                for ip in self.scan_devices:
                    for device in self.cloud_devices:
                        if device['id'] == self.scan_devices[ip]["gwId"]:
                            ip_list.append(f"{ip} - {device['name']}")
                            break
                if len(ip_list) == 0:
                    return await self.async_step_pre_scan(errors={"base": "tuya_not_found"})
            schema = vol.Schema(
            {
                vol.Required(CONF_HOST): vol.In(ip_list)
            })
        except Exception as e:
            _LOGGER.error("Scan error: %s", e, exc_info=True)
            return self.async_abort(reason='unknown')
        return self.async_show_form(
            step_id="scan",
            errors=errors,
            data_schema=schema
        )

    def _test_connection(self, dev_id, address, local_key, version):
        _LOGGER.debug("Testing connection to %s at %s with key %s", dev_id, address, local_key)
        device = Contrib.IRRemoteControlDevice(dev_id=dev_id, address=address, local_key=local_key, version=version)
        status = device.status()
        _LOGGER.debug("Connection test status: %s, control type detected: %s", status, device.control_type)
        return device, status

    async def async_step_config(self, user_input=None, errors={}):
        """Handle the config step."""
        if user_input is not None:
            self.config[CONF_NAME] = user_input[CONF_NAME]
            self.config[CONF_HOST] = user_input[CONF_HOST]
            self.config[CONF_DEVICE_ID] = user_input[CONF_DEVICE_ID]
            self.config[CONF_LOCAL_KEY] = user_input[CONF_LOCAL_KEY]
            self.config[CONF_PROTOCOL_VERSION] = None
            # Bruteforce the protocol version (in order of preference)
            for version in [3.3, 3.4, 3.5, 3.2, 3.1]:
                _LOGGER.debug("Trying protocol version %s", version)
                try:
                    device, status = await self.hass.async_add_executor_job(self._test_connection, user_input[CONF_DEVICE_ID], user_input[CONF_HOST], user_input[CONF_LOCAL_KEY], version)
                except Exception as e:
                    _LOGGER.error("Device test error, exception %s: %s", type(e), e, exc_info=True)
                    continue
                _LOGGER.debug("Connection test status: %s", status)
                if "Error" not in status:
                    self.config[CONF_PROTOCOL_VERSION] = version
                    break
            if not self.config[CONF_PROTOCOL_VERSION]:
                errors["base"] = "cannot_connect"
                _LOGGER.error(f"Cannot connect to device using any protocol version")
            elif not device.control_type:
                errors["base"] = "no_control_type"
                _LOGGER.error(f"Device test error: control type not detected")
            elif self.config[CONF_DEVICE_ID] in self._async_current_ids():
                return self.async_abort(reason="already_configured")
            else:
                # Ok!
                if self.cloud and 'key' in self.cloud_info:
                    del self.cloud_info['key']
                self.config[CONF_CLOUD_INFO] = self.cloud_info if self.cloud else None
                _LOGGER.debug("Config: %s", self.config)
                await self.async_set_unique_id(self.config[CONF_DEVICE_ID])
                return self.async_create_entry(title=self.config[CONF_NAME], data=self.config)
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=self.config[CONF_NAME]): cv.string,
            vol.Required(CONF_HOST, default=self.config[CONF_HOST]): cv.string,
            vol.Required(CONF_DEVICE_ID, default=self.config[CONF_DEVICE_ID]): cv.string,
            vol.Required(CONF_LOCAL_KEY, default=self.config[CONF_LOCAL_KEY]): cv.string,
        })
        return self.async_show_form(
            step_id="config",
            errors=errors,
            data_schema=schema
        )
