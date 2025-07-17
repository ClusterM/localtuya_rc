"""Support for Tuya IR Remote Control."""
import logging
import asyncio
import voluptuous as vol
import homeassistant.helpers.config_validation as cv
from tinytuya import Contrib
from tinytuya.Contrib import RFRemoteControlDevice
import threading

from .const import (
    DOMAIN,
    DEFAULT_FRIENDLY_NAME,
    CONF_LOCAL_KEY,
    CONF_PROTOCOL_VERSION,
    CONF_CLOUD_INFO,
    CONF_PERSISTENT_CONNECTION,
    CODE_STORAGE_VERSION,
    CODE_STORAGE_CODES,
    NOTIFICATION_TITLE,
    DEFAULT_PERSISTENT_CONNECTION
)

from homeassistant.const import (
    CONF_NAME,
    CONF_HOST,
    CONF_DEVICE_ID,
)
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.exceptions import HomeAssistantError
from homeassistant.components.persistent_notification import async_create
from homeassistant.components.remote import (
    ATTR_COMMAND_TYPE,
    ATTR_TIMEOUT,
    ATTR_ALTERNATIVE,
    ATTR_COMMAND,
    ATTR_DEVICE,
    ATTR_DELAY_SECS,
    ATTR_NUM_REPEATS,
    ATTR_HOLD_SECS,
    PLATFORM_SCHEMA,
    RemoteEntity,
    RemoteEntityFeature,
)
from homeassistant.helpers.storage import Store

from .rc_encoder import rc_auto_encode, rc_auto_decode

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
            vol.Required(CONF_NAME, default=DEFAULT_FRIENDLY_NAME): cv.string,
            vol.Required(CONF_HOST): cv.string,
            vol.Required(CONF_DEVICE_ID): cv.string,
            vol.Required(CONF_LOCAL_KEY): cv.string,
            vol.Required(CONF_PROTOCOL_VERSION, default="3.3"): vol.In(
                ["3.1", "3.2", "3.3", "3.4", "3.5"]
            ),
            vol.Required(CONF_PERSISTENT_CONNECTION, default=DEFAULT_PERSISTENT_CONNECTION): cv.boolean,
    }
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, entry, async_add_entities, discovery_info=None):
    """Set up the Tuya IR Remote Control entry."""
    await async_setup_platform(hass, entry.data, async_add_entities, discovery_info)


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up platform."""
    if config == None:
        _LOGGER.error("Configuration is empty")
        return
    
    name = config.get(CONF_NAME, DEFAULT_FRIENDLY_NAME)
    dev_id = config.get(CONF_DEVICE_ID)
    host = config.get(CONF_HOST)
    local_key = config.get(CONF_LOCAL_KEY)
    protocol_version = config.get(CONF_PROTOCOL_VERSION)
    cloud_info = config.get(CONF_CLOUD_INFO, None)
    persistent_connection = config.get(CONF_PERSISTENT_CONNECTION, DEFAULT_PERSISTENT_CONNECTION)

    if name is None or host is None or dev_id is None or local_key is None:
        _LOGGER.error("Missing required configuration items")
        return

    _LOGGER.debug("Setting up Tuya IR Remote Control: name=%s, dev_id=%s, host=%s, local_key=%s, protocol_version=%s, persistent_connection=%s, cloud_info=%s", name, dev_id, host, local_key, protocol_version, persistent_connection, cloud_info)

    remote = TuyaRC(name, dev_id, host, local_key, protocol_version, persistent_connection, cloud_info)
    # Update availability of the device
    await hass.async_add_executor_job(remote._update_availibility)

    async_add_entities([remote])


class TuyaRC(RemoteEntity):
    def __init__(self, name, dev_id, address, local_key, protocol_version, persistent_connection=DEFAULT_PERSISTENT_CONNECTION, cloud_info=None):
        self._name = name
        self._dev_id = dev_id
        self._address = address
        self._local_key = local_key
        self._protocol_version = protocol_version
        self._persistent_connection = persistent_connection
        self._cloud_info = cloud_info
        
        self._storage = None
        self._codes = {}
        self._available = False

        self._device = None
        self._device_RF = None
        self._lock = threading.Lock()

    def _init(self):
        if self._device:
            return
        _LOGGER.debug("Initializing device %s (address: %s, local_key: %s, protocol_version: %s, persistent_connection: %s)...", self._dev_id, self._address, self._local_key, self._protocol_version, self._persistent_connection)
        self._device = Contrib.IRRemoteControlDevice(dev_id=self._dev_id, address=self._address, local_key=self._local_key, version=float(self._protocol_version), persist=self._persistent_connection)
        _LOGGER.debug("Initializing device %s (address: %s, local_key: %s, protocol_version: %s, persistent_connection: %s)...", self._dev_id, self._address, self._local_key, self._protocol_version, self._persistent_connection)
        self._device_RF = RFRemoteControlDevice.RFRemoteControlDevice(dev_id=self._dev_id, address=self._address, local_key=self._local_key, version=float(self._protocol_version), persist=self._persistent_connection)
        _LOGGER.debug("Device %s initialized.", self._dev_id)

    def _deinit(self):
        if self._device:
            self._device.close()
            self._device = None
            _LOGGER.debug("Device %s deinitialized.", self._dev_id)

    @property
    def available(self):
        return self._available

    @property
    def state(self):
        return 'online' if self._available else 'offline'

    @property
    def name(self):
        return self._name

    @property
    def unique_id(self):
        return self._dev_id

    @property
    def should_poll(self):
        return True

    @property
    def device_info(self):
        return DeviceInfo(
            name=self._name,
            manufacturer="Tuya",
            identifiers={(DOMAIN, self._dev_id)},
            connections={(DOMAIN, self._cloud_info['mac'])} if self._cloud_info and 'mac' in self._cloud_info else set(),
            model=self._cloud_info['model'] if self._cloud_info and 'model' in self._cloud_info else None,
            serial_number=self._cloud_info['sn'] if self._cloud_info and 'sn' in self._cloud_info else None,
        )

    @property
    def extra_state_attributes(self):
        # Make copy of self._cloud_info
        extra = self._cloud_info.copy() if self._cloud_info else {}
        if 'icon' in extra:
            extra['icon_url'] = extra['icon']
            del extra['icon']
        # Add some extra attributes
        extra['protocol_version'] = self._protocol_version
        if self._device:
            extra['control_type'] = self._device.control_type
        extra['learned_commands'] = str({device: str(list(commands.keys())) for device, commands in self._codes.items()})
        return extra

    @property
    def supported_features(self):
        return RemoteEntityFeature.LEARN_COMMAND | RemoteEntityFeature.DELETE_COMMAND

    async def async_will_remove_from_hass(self):
        _LOGGER.debug("Removing device %s from Home Assistant...", self._dev_id)
        self._deinit()

    def _receive_button(self, timeout):
        with self._lock:
            self._init()
            try:
                return self._device.receive_button(timeout)
            except Exception as e:
                _LOGGER.error("Failed to receive button, exception %s: %s", type(e), e, exc_info=True)
                raise HomeAssistantError("tinytuya library internal error, please check the logs.")
    
    def _send_button(self, pulses):
        with self._lock:
            try:
                self._init()
                if type(pulses) == str:
                    _LOGGER.debug("Sending command as base64: '%s'", pulses)
                    try:
                        return self._device.send_button(pulses)
                    except:
                        _LOGGER.error("Failed to send command as base64, exception %s: %s", type(e), e, exc_info=True)
                        raise HomeAssistantError("tinytuya library internal error, please check the logs.")
                else:
                    _LOGGER.debug("Sending command as pulses: '%s'", pulses)
                    b64 = Contrib.IRRemoteControlDevice.pulses_to_base64(pulses)
                    _LOGGER.debug("Converted to base64: '%s'", b64)
                    try:
                        return self._device.send_button(b64)
                    except:
                        _LOGGER.error("Failed to send command as pulses, exception %s: %s", type(e), e, exc_info=True)
                        raise HomeAssistantError("tinytuya library internal error, please check the logs.")
            except Exception as e:
                self._deinit()
                raise e
    
    def _receive_button_rf(self, timeout):
        with self._lock:
            self._init()
            try:
                return self._device_RF.rf_receive_button(timeout=timeout)
            except Exception as e:
                _LOGGER.error("Failed to receive RF button, exception %s: %s", type(e), e, exc_info=True)
                raise HomeAssistantError("tinytuya library internal rf error, please check the logs.")
    
    def _send_button_rf(self, base64):
        with self._lock:
            try:
                self._init()
                try:
                    _LOGGER.debug("Sending command as base64: '%s'", base64)
                    return self._device_RF.rf_send_button(base64)
                except Exception as e:
                    _LOGGER.error("Failed to send RF button, exception %s: %s", type(e), e, exc_info=True)
                    raise HomeAssistantError("tinytuya library internal rf error, please check the logs.")
            except Exception as e:
                self._deinit()
                raise e

    async def _async_load_storage_files(self):
        if not self._storage:
            self._storage = Store(self.hass, CODE_STORAGE_VERSION, CODE_STORAGE_CODES)
        self._codes.update(await self._storage.async_load() or {})

    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        raise HomeAssistantError("Turning on is not supported for this device.")

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        raise HomeAssistantError("Turning off is not supported for this device.")

    def _update_availibility(self):
        with self._lock:
            _LOGGER.debug("Updating device %s availibility...", self._dev_id)
            try:
                self._init()
                status = self._device.status()
                _LOGGER.debug(f"Device status: {status}")
                self._available = status and not "Error" in status
                if not self._available:
                    _LOGGER.error("Device is not available, status: %s", status)
            except Exception as e:
                self._available = False
                _LOGGER.error("Failed to update device, exception %s: %s", type(e), e, exc_info=True)
            if not self._available:
                self._deinit()
            _LOGGER.debug("Device %s is available: %s", self._dev_id, self._available)

    async def async_update(self):
        """Update the device."""
        await self.hass.async_add_executor_job(self._update_availibility)
        await self._async_load_storage_files()

    async def async_send_command(self, command, **kwargs):
        """Send a list of commands to a device."""
        device = kwargs.get(ATTR_DEVICE, None)
        repeat = kwargs.get(ATTR_NUM_REPEATS, 1)
        repeat_delay = kwargs.get(ATTR_DELAY_SECS, 0)
        hold = kwargs.get(ATTR_HOLD_SECS, 0)
        
        if hold != 0:
            raise NotImplementedError("Hold time is not supported.")
        
        try:
            await self._async_load_storage_files()
            for n in range(repeat):
                for cmd in command:
                    if device:
                        if not device in self._codes:
                            raise KeyError(f"Device '{device}' not found in the codes storage.")
                        if not cmd in self._codes[device]:
                            raise KeyError(f"Command '{cmd}' not found in the codes storage for device '{device}'.")
                        code = self._codes[device][cmd]
                        _LOGGER.debug("Sending command '%s' for device '%s', code: %s", cmd, device, code)
                    else:
                        code = cmd
                        _LOGGER.debug("Sending command, code: '%s'", code)
                    if code.startswith("rf:"):
                        await self.hass.async_add_executor_job(self._send_button_rf, code[3:])
                    else:
                        pulses = rc_auto_encode(code)
                        _LOGGER.debug("Command pulses: %s", pulses)
                        await self.hass.async_add_executor_job(self._send_button, pulses)
                    if n < repeat - 1 and repeat_delay > 0:
                        await asyncio.sleep(repeat_delay)
        except Exception as e:
            _LOGGER.error("Failed to send command, exception %s: %s", type(e), e, exc_info=True)
            raise HomeAssistantError(str(e))

    async def async_learn_command(self, **kwargs):
        """Learn a command to a device, or just show the received command code."""
        device = kwargs.get(ATTR_DEVICE, None)
        commands = kwargs.get(ATTR_COMMAND, [])
        command_type = kwargs.get(ATTR_COMMAND_TYPE, "ir")
        alternative = kwargs.get(ATTR_ALTERNATIVE, None)
        timeout = kwargs.get(ATTR_TIMEOUT, 10)

        if len(commands) != 1:
            raise ValueError("You need to specify exactly one command to learn.")

        command = commands[0]
        notification_id = "learn_command_" + self._dev_id + "_" + str(device) + "_" + command
        
        try:
            if not command: raise ValueError("You need to specify a command name to learn.")
            if command_type != "ir" and command_type != "rf": raise NotImplementedError(f'Unknown command type "{command_type}", only "ir" and "rf" is supported.')
            if alternative != None: raise ValueError('"Alternative" option is not supported.')
            if self._lock.locked():
                raise HomeAssistantError("Device is busy, please wait and try again.")
            async_create(
                self.hass,
                f'Press the "<b>{command}</b>" button.',
                title=NOTIFICATION_TITLE,
                notification_id=notification_id,
            )
            
            _LOGGER.debug(f"Waiting for button press...")
            if command_type == "ir":
                button = await self.hass.async_add_executor_job(self._receive_button, timeout)
            elif command_type == "rf":
                button = await self.hass.async_add_executor_job(self._receive_button_rf, timeout)
            _LOGGER.debug("Button pressed: %s", button)
            if button == None: raise TimeoutError("Timeout. Please try again.")
            if isinstance(button, dict) and "Error" in button:
                self._deinit()
                raise HomeAssistantError(button["Error"])
            if not isinstance(button, str):
                self._deinit()
                raise ValueError(f"Invalid response: {button}")
            
            if command_type == "ir":
                pulses = Contrib.IRRemoteControlDevice.base64_to_pulses(button)
                if len(pulses) < 4:
                    raise ValueError("This IR code is too short and seems to be invalid. Please try to learn the command again.")
                decoded = rc_auto_decode(pulses)
                decoded_raw = rc_auto_decode(pulses, force_raw=True)

                direct_code_example = f'<pre>service: remote.send_command\ntarget:\n  entity_id: {self.entity_id}\ndata:\n  command: {decoded}</pre>'
                direct_code_example_raw = f'If code above is not working, you can try to use the raw code:\n<pre>service: remote.send_command\ntarget:\n  entity_id: {self.entity_id}\ndata:\n  command: {decoded_raw}</pre>But <a href="https://github.com/ClusterM/localtuya_rc/issues">create a bug report</a> in such case, please.'
            elif command_type == "rf":
                decoded = "rf:" + button
                decoded_raw = "rfraw:" + button
                direct_code_example = f'<pre>service: remote.send_command\ntarget:\n  entity_id: {self.entity_id}\ndata:\n  command: {decoded}</pre>'
                direct_code_example_raw = f'If code above is not working, you can try to use the raw code:\n<pre>service: remote.send_command\ntarget:\n  entity_id: {self.entity_id}\ndata:\n  command: {decoded_raw}</pre>But <a href="https://github.com/ClusterM/localtuya_rc/issues">create a bug report</a> in such case, please.'
            
            if device:
                await self._async_load_storage_files()
                self._codes.setdefault(device, {}).update({command: decoded})
                await self._storage.async_save(self._codes)
                self.schedule_update_ha_state() # Update device attributes
                msg = f'Successfully learned command "<b>{command}</b>" for device "<b>{device}</b>", code:\r\n<pre>{decoded}</pre>' + \
                    (f"Raw code:<pre>{decoded_raw}</pre>" if not decoded.startswith("raw:") else "") + \
                    "\n\nNow you can use this device identifier and command name in your automations and scripts with the 'remote.send_command' service. Example:" + \
                    f'<pre>service: remote.send_command\ntarget:\n  entity_id: {self.entity_id}\ndata:\n  device: {device}\n  command: {command}</pre>' + \
                    "\n\nOr you can use the button code directly in your automations and scripts with the 'remote.send_command' service. Example:" + \
                    direct_code_example + \
                    (f"\n\n{direct_code_example_raw}" if not decoded.startswith("raw:") else "")
            else:
                msg = f'Successfully received command "{command}", code:\r\n<pre>{decoded}</pre>' + \
                    (f"Raw code:<pre>{decoded_raw}</pre>" if not decoded.startswith("raw:") else "") + \
                    "\n\nNow you can use this code in your automations and scripts with the 'remote.send_command' service. Example:" + \
                    direct_code_example + \
                    (f"\n\n{direct_code_example_raw}" if not decoded.startswith("raw:") else "")
                
            if decoded.startswith("raw:"):
                msg += "\r\n\r\n<b>Warning</b>: this command is learned in raw format, e.g. it can't be decoded using known protocol decoders. It's better to try to learn the command again but it's ok if you keep seeing this message."

            async_create(
                self.hass,
                msg,
                title=NOTIFICATION_TITLE,
                notification_id=notification_id,
            )
        except Exception as e:
            _LOGGER.error("Failed to learn command, exception %s: %s", type(e), e, exc_info=True)
            async_create(
                self.hass,
                f'Cannot learn command "{command}": {e}',
                title=NOTIFICATION_TITLE,
                notification_id=notification_id,
            )
            raise HomeAssistantError(str(e))

    async def async_delete_command(self, **kwargs):
        """Delete a command from a device."""
        device = kwargs.get(ATTR_DEVICE, None)
        commands = kwargs.get(ATTR_COMMAND, [])
        
        if not device:
            raise HomeAssistantError("You need to specify a device.")

        await self._async_load_storage_files()

        if not device in self._codes:
            raise HomeAssistantError(f"Device '{device}' not found in the codes storage.")

        deleted = False
        for command in commands:
            if device in self._codes and command in self._codes[device]:
                del self._codes[device][command]
                deleted = True
                async_create(
                    self.hass,
                    f'Successfully deleted command "{command}" for device "{device}".',
                    title=NOTIFICATION_TITLE
                )
        if not deleted:
            raise HomeAssistantError(f'Command "{command}" for device "{device}" not found.')

        # Remove device if no commands left
        if device in self._codes and not self._codes[device]:
            del self._codes[device]

        await self._storage.async_save(self._codes)
