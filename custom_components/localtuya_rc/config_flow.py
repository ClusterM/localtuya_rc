"""Config flow for the LocalTuyaIR Remote Control integration."""

import logging
import voluptuous as vol
import tinytuya
from tinytuya import Contrib, Cloud

from .const import *

from homeassistant import config_entries
from homeassistant.core import callback
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

    def __init__(self):
        """Initialize the config flow."""
        # Default config
        self.config = {
            CONF_NAME: DEFAULT_FRIENDLY_NAME,
            CONF_DEVICE_ID: '',
            CONF_LOCAL_KEY: '',
            CONF_PROTOCOL_VERSION: 'Auto',
            CONF_CONTROL_TYPE: 'Auto',
            CONF_PERSISTENT_CONNECTION: DEFAULT_PERSISTENT_CONNECTION,
            CONF_REGION: 'eu',
            CONF_CLIENT_ID: '',
            CONF_CLIENT_SECRET: '',
            CONF_HOST: '',
        }
        self.cloud = False

    @staticmethod
    @callback
    def async_get_options_flow(entry):
        return LocalTuyaIROptionsFlow(entry)

    async def async_step_user(self, user_input=None):
        """Handle a flow initialized by the user."""
        return await self.async_step_method()

    async def async_step_method(self, user_input=None):
        """Select: use Tuya Cloud API or enter local key manually."""
        # Ask user to to obtain the local key: via the API or enter manually
        return self.async_show_menu(
            step_id="method",
            menu_options=["cloud", "ip_method"])

    def _get_cloud_devices(self, region, client_id, client_secret):
        cloud = Cloud(region, client_id, client_secret)
        status = cloud.getconnectstatus()
        return cloud, status

    async def async_step_cloud(self, user_input=None):
        """Handle the API step, enter credentials."""
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
                        return await self.async_step_ip_method()
            except Exception as e:
                _LOGGER.error("Cloud API error: %s", e, exc_info=True)
                errors["base"] = "unknown"
        schema = vol.Schema(
            {
                vol.Required(CONF_REGION, default=self.config[CONF_REGION]): vol.In(["us", "us-e", "eu", "eu-w", "in", "cn", "sg"]),
                vol.Required(CONF_CLIENT_ID, default=self.config[CONF_CLIENT_ID]): cv.string,
                vol.Required(CONF_CLIENT_SECRET, default=self.config[CONF_CLIENT_SECRET]): cv.string
            }
        )
        return self.async_show_form(
            step_id="cloud",
            errors=errors,
            data_schema=schema
        )

    async def async_step_ip_method(self, user_input=None, errors={}):
        """Ask user to scan for devices or enter the IP manually."""
        if self.cloud:
            return self.async_show_menu(
                step_id="ip_method",
                menu_options=["pre_scan", "ask_ip"])
        else:
            return self.async_show_menu(
                step_id="ip_method",
                menu_options=["pre_scan", "config"])
        
    async def async_step_ask_ip(self, user_input=None, errors={}):
        """Ask user to enter the IP manually."""
        if user_input is not None:
            self.config[CONF_HOST] = user_input[CONF_HOST]
            id = user_input[CONF_DEVICE_ID].split(' ')[-1][1:-1]
            self.config[CONF_DEVICE_ID] = id
            devices = [device for device in self.cloud_devices if device['id'] == id]
            self.config[CONF_NAME] = devices[0]['name']
            self.config[CONF_LOCAL_KEY] = devices[0]['key']
            return await self.async_step_config()
        device_list = [f"{device['name']} ({device['id']})" for device in self.cloud_devices]
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=self.config[CONF_HOST]): cv.string,
                vol.Required(CONF_DEVICE_ID): vol.In(device_list),
            }
        )
        return self.async_show_form(
            step_id="ask_ip",
            errors=errors,
            data_schema=schema
        )

    async def async_step_pre_scan(self, user_input=None, errors={}):
        """Just show a message to the user."""
        if user_input is not None:
            return await self.async_step_scan()
        return self.async_show_form(
            step_id="pre_scan",
            errors=errors,
            data_schema=vol.Schema({})
        )

    async def async_step_scan(self, user_input=None):
        """Scan local network for devices."""
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

    def _test_connection(self, dev_id, address, local_key, version, control_type=0):
        _LOGGER.debug("Testing connection to %s at %s with key %s, control_type=%s", dev_id, address, local_key, control_type)
        device = Contrib.IRRemoteControlDevice(
            dev_id=dev_id,
            address=address,
            local_key=local_key,
            version=version,
            control_type=control_type or 0,
            connection_timeout=5,
            connection_retry_delay=0.5,
            connection_retry_limit=2,
        )
        status = device.status()
        _LOGGER.debug("Connection test status: %s, control type detected: %s", status, device.control_type)
        return device, status

    @staticmethod
    def _classify_test_failure(status, exception):
        """Map a tinytuya error status / exception to a config-flow error key.

        Returns the key used in translations/*.json (e.g. "bad_key_or_version").
        Returns None when the response is actually a success.
        """
        # tinytuya error codes: see tinytuya/core/error_helper.py
        err_code_map = {
            "900": "bad_response_format",     # ERR_JSON
            "901": "cannot_connect_offline",  # ERR_CONNECT
            "902": "cannot_connect_timeout",  # ERR_TIMEOUT
            "904": "protocol_mismatch",       # ERR_PAYLOAD
            "905": "cannot_connect_offline",  # ERR_OFFLINE
            "908": "protocol_mismatch",       # ERR_DEVTYPE
            "914": "bad_key_or_version",      # ERR_KEY_OR_VER
        }
        if isinstance(status, dict) and "Error" in status:
            err = str(status.get("Err", "")).strip()
            return err_code_map.get(err, "cannot_connect")
        if exception is not None:
            # Common transport-level exceptions
            name = type(exception).__name__
            if name in ("TimeoutError", "socket.timeout"):
                return "cannot_connect_timeout"
            if name in ("ConnectionRefusedError", "ConnectionResetError",
                        "ConnectionAbortedError", "OSError"):
                return "cannot_connect_offline"
            return "cannot_connect"
        return None

    async def async_step_config(self, user_input=None, errors={}):
        """Last config step"""
        if user_input is not None:
            self.config[CONF_NAME] = user_input[CONF_NAME]
            self.config[CONF_HOST] = user_input[CONF_HOST]
            self.config[CONF_DEVICE_ID] = user_input[CONF_DEVICE_ID]
            self.config[CONF_LOCAL_KEY] = user_input[CONF_LOCAL_KEY]
            self.config[CONF_PERSISTENT_CONNECTION] = user_input[CONF_PERSISTENT_CONNECTION]
            self.config[CONF_PROTOCOL_VERSION] = user_input[CONF_PROTOCOL_VERSION]
            self.config[CONF_CONTROL_TYPE] = user_input[CONF_CONTROL_TYPE]
            # If user explicitly chose a control_type, pass it to the device
            # constructor so tinytuya skips its own (sometimes flaky) detection
            # and uses the supplied value as authoritative.
            ct_input = user_input[CONF_CONTROL_TYPE]
            ct_param = 0 if ct_input == "Auto" else int(ct_input)
            # Bruteforce the protocol version (in order of preference)
            try_versions = TUYA_VERSIONS if user_input[CONF_PROTOCOL_VERSION] == "Auto" else [user_input[CONF_PROTOCOL_VERSION]]
            version_ok = None
            device = None
            # Track the most informative failure across all attempts so that
            # the UI can display a specific message instead of a generic one.
            last_failure = "cannot_connect"
            last_status = None
            last_exception = None
            for version in try_versions:
                _LOGGER.debug("Trying protocol version %s", version)
                status = None
                try:
                    device, status = await self.hass.async_add_executor_job(
                        self._test_connection,
                        user_input[CONF_DEVICE_ID],
                        user_input[CONF_HOST],
                        user_input[CONF_LOCAL_KEY],
                        version,
                        ct_param,
                    )
                except Exception as e:
                    _LOGGER.error("Device test error, exception %s: %s", type(e), e, exc_info=True)
                    last_exception = e
                    last_status = None
                    last_failure = self._classify_test_failure(None, e) or last_failure
                    continue
                last_status = status
                last_exception = None
                classified = self._classify_test_failure(status, None)
                if classified is None:
                    version_ok = version
                    break
                last_failure = classified
            if not version_ok:
                errors["base"] = last_failure
                _LOGGER.error(
                    "Cannot connect to device using any protocol version "
                    "(last_failure=%s, last_status=%s, last_exception=%s)",
                    last_failure, last_status, last_exception,
                )
            elif not device.control_type:
                errors["base"] = "no_control_type"
                _LOGGER.error(f"Device test error: control type not detected")
            elif self.config[CONF_DEVICE_ID] in self._async_current_ids():
                return self.async_abort(reason="already_configured")
            else:
                # Ok!
                self.config[CONF_PROTOCOL_VERSION] = version_ok
                self.config[CONF_CONTROL_TYPE] = device.control_type
                if self.cloud and 'key' in self.cloud_info:
                    del self.cloud_info['key'] # to protect the key
                self.config[CONF_CLOUD_INFO] = self.cloud_info if self.cloud else None
                _LOGGER.debug("Config: %s", self.config)
                await self.async_set_unique_id(self.config[CONF_DEVICE_ID])
                return self.async_create_entry(title=self.config[CONF_NAME], data=self.config)
        versions_sorted = TUYA_VERSIONS.copy()
        versions_sorted.sort()
        # control_type default: keep the user's previous textual choice if any,
        # or convert a numeric value (e.g. from a prior successful detection)
        # back to its UI string form.
        ct_default = self.config.get(CONF_CONTROL_TYPE, "Auto")
        if isinstance(ct_default, int):
            ct_default = str(ct_default) if ct_default in (1, 2) else "Auto"
        schema = vol.Schema({
            vol.Required(CONF_NAME, default=self.config[CONF_NAME]): cv.string,
            vol.Required(CONF_HOST, default=self.config[CONF_HOST]): cv.string,
            vol.Required(CONF_DEVICE_ID, default=self.config[CONF_DEVICE_ID]): cv.string,
            vol.Required(CONF_LOCAL_KEY, default=self.config[CONF_LOCAL_KEY]): cv.string,
            vol.Required(CONF_PROTOCOL_VERSION, default=self.config[CONF_PROTOCOL_VERSION]): vol.In(["Auto"] + versions_sorted),
            vol.Required(CONF_CONTROL_TYPE, default=ct_default): vol.In(["Auto", "1", "2"]),
            vol.Required(CONF_PERSISTENT_CONNECTION, default=self.config[CONF_PERSISTENT_CONNECTION]): cv.boolean
        })
        return self.async_show_form(
            step_id="config",
            errors=errors,
            data_schema=schema
        )


    async def async_step_reconfigure(self, user_input=None):
        """Handle reconfiguration of the device (e.g. IP change)."""
        entry = self._get_reconfigure_entry()
        self.config = dict(entry.data)
        return self.async_show_menu(
            step_id="reconfigure",
            menu_options=["reconfigure_scan", "reconfigure_manual"])

    async def async_step_reconfigure_scan(self, user_input=None):
        """Scan network to find the device at a new IP."""
        entry = self._get_reconfigure_entry()
        config = dict(entry.data)
        dev_id = config[CONF_DEVICE_ID]
        local_key = config[CONF_LOCAL_KEY]
        protocol_version = config[CONF_PROTOCOL_VERSION]

        try:
            scan_devices = await self.hass.async_add_executor_job(tinytuya.deviceScan)
        except Exception as e:
            _LOGGER.error("Scan error: %s", e, exc_info=True)
            return self.async_show_form(
                step_id="reconfigure_scan",
                errors={"base": "unknown"},
                data_schema=vol.Schema({})
            )

        # Find our device by ID
        new_ip = None
        for ip, found_device in scan_devices.items():
            if found_device.get("gwId") == dev_id:
                new_ip = ip
                break

        if not new_ip:
            return self.async_show_form(
                step_id="reconfigure_scan",
                errors={"base": "tuya_not_found"},
                data_schema=vol.Schema({})
            )

        # Test connection at the new IP
        try:
            device, status = await self.hass.async_add_executor_job(
                self._test_connection, dev_id, new_ip, local_key, float(protocol_version))
        except Exception as e:
            _LOGGER.error("Connection test error at %s: %s", new_ip, e, exc_info=True)
            return self.async_show_form(
                step_id="reconfigure_scan",
                errors={"base": self._classify_test_failure(None, e) or "cannot_connect"},
                data_schema=vol.Schema({})
            )

        classified = self._classify_test_failure(status, None)
        if classified is not None:
            return self.async_show_form(
                step_id="reconfigure_scan",
                errors={"base": classified},
                data_schema=vol.Schema({})
            )

        config[CONF_HOST] = new_ip
        if device.control_type:
            config[CONF_CONTROL_TYPE] = device.control_type
        return self.async_update_reload_and_abort(entry, data=config, reason="reconfigure_successful")

    async def async_step_reconfigure_manual(self, user_input=None):
        """Allow user to manually enter a new IP address."""
        entry = self._get_reconfigure_entry()
        config = dict(entry.data)
        errors = {}
        default_host = config[CONF_HOST]

        if user_input is not None:
            new_ip = user_input[CONF_HOST]
            default_host = new_ip
            dev_id = config[CONF_DEVICE_ID]
            local_key = config[CONF_LOCAL_KEY]
            protocol_version = config[CONF_PROTOCOL_VERSION]

            # Test connection at the new IP
            status = None
            device = None
            try:
                device, status = await self.hass.async_add_executor_job(
                    self._test_connection, dev_id, new_ip, local_key, float(protocol_version))
            except Exception as e:
                _LOGGER.error("Connection test error at %s: %s", new_ip, e, exc_info=True)
                errors["base"] = self._classify_test_failure(None, e) or "cannot_connect"

            if "base" not in errors:
                classified = self._classify_test_failure(status, None)
                if classified is not None:
                    errors["base"] = classified

            if not errors:
                config[CONF_HOST] = new_ip
                if device is not None and device.control_type:
                    config[CONF_CONTROL_TYPE] = device.control_type
                return self.async_update_reload_and_abort(entry, data=config, reason="reconfigure_successful")

        schema = vol.Schema({
            vol.Required(CONF_HOST, default=default_host): cv.string,
        })
        return self.async_show_form(
            step_id="reconfigure_manual",
            errors=errors,
            data_schema=schema
        )


class LocalTuyaIROptionsFlow(config_entries.OptionsFlow):
    """Options flow for LocalTuyaIR Remote Control."""
    
    def __init__(self, entry):
        """Initialize the options flow."""
        self.entry = entry
        self.config = dict(entry.data.items())
        _LOGGER.debug("Options flow init, current config: %s", self.config)

    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            self.config[CONF_PERSISTENT_CONNECTION] = user_input[CONF_PERSISTENT_CONNECTION]
            # Translate the control_type UI value back to the integer stored
            # in entry.data. "Auto" clears the cached value so tinytuya will
            # re-run its own auto-detection on next setup.
            ct_input = user_input.get(CONF_CONTROL_TYPE, "Auto")
            self.config[CONF_CONTROL_TYPE] = 0 if ct_input == "Auto" else int(ct_input)
            _LOGGER.debug("Config updated: %s", self.config)
            self.hass.config_entries.async_update_entry(self.entry, data=self.config)
            return self.async_create_entry(data=self.config)

        ct_default = self.config.get(CONF_CONTROL_TYPE, 0)
        ct_default = str(ct_default) if ct_default in (1, 2) else "Auto"
        options_schema = vol.Schema({
            vol.Required(CONF_PERSISTENT_CONNECTION, default=self.config.get(CONF_PERSISTENT_CONNECTION, DEFAULT_PERSISTENT_CONNECTION)): cv.boolean,
            vol.Required(CONF_CONTROL_TYPE, default=ct_default): vol.In(["Auto", "1", "2"]),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema
        )
