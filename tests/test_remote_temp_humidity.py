"""Tests for remote.py's temperature/humidity DP handling: capturing DPs
101/102 from status(), the temperature/humidity/temp_humidity_supported
properties, and persisting detection to the config entry.

Stubs homeassistant.* like test_remote_recovery.py (no HA test harness here).
"""

import importlib.util
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REMOTE_PATH = ROOT / "custom_components" / "localtuya_rc" / "remote.py"
PACKAGE_NAME = "localtuya_rc_temp_humidity_test"


class _PlatformSchema:
    def extend(self, _schema):
        return self


def _install_module(monkeypatch, name, **attributes):
    module = types.ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.fixture
def remote_module(monkeypatch):
    homeassistant = _install_module(monkeypatch, "homeassistant")
    homeassistant.__path__ = []
    helpers = _install_module(monkeypatch, "homeassistant.helpers")
    helpers.__path__ = []
    components = _install_module(monkeypatch, "homeassistant.components")
    components.__path__ = []

    _install_module(
        monkeypatch,
        "voluptuous",
        Required=lambda value, **_kwargs: value,
        In=lambda values: values,
    )
    _install_module(
        monkeypatch,
        "homeassistant.helpers.config_validation",
        string=str,
        boolean=bool,
    )
    _install_module(
        monkeypatch,
        "homeassistant.const",
        CONF_NAME="name",
        CONF_HOST="host",
        CONF_DEVICE_ID="device_id",
    )
    _install_module(monkeypatch, "homeassistant.helpers.entity", DeviceInfo=dict)

    class HomeAssistantError(Exception):
        """Minimal Home Assistant error type for the unit under test."""

    _install_module(
        monkeypatch,
        "homeassistant.exceptions",
        HomeAssistantError=HomeAssistantError,
    )
    _install_module(
        monkeypatch,
        "homeassistant.components.persistent_notification",
        async_create=lambda *_args, **_kwargs: None,
    )
    _install_module(
        monkeypatch,
        "homeassistant.components.remote",
        ATTR_COMMAND_TYPE="command_type",
        ATTR_TIMEOUT="timeout",
        ATTR_ALTERNATIVE="alternative",
        ATTR_COMMAND="command",
        ATTR_DEVICE="device",
        ATTR_DELAY_SECS="delay_secs",
        ATTR_NUM_REPEATS="num_repeats",
        ATTR_HOLD_SECS="hold_secs",
        PLATFORM_SCHEMA=_PlatformSchema(),
        RemoteEntity=type("RemoteEntity", (), {}),
        RemoteEntityFeature=types.SimpleNamespace(LEARN_COMMAND=1, DELETE_COMMAND=2),
    )
    _install_module(monkeypatch, "homeassistant.helpers.storage", Store=object)

    contrib = types.SimpleNamespace(IRRemoteControlDevice=object)
    tinytuya = _install_module(
        monkeypatch, "tinytuya", Contrib=contrib, ERR_JSON=900, ERR_TIMEOUT=902
    )
    tinytuya.__path__ = []
    _install_module(
        monkeypatch,
        "tinytuya.Contrib",
        RFRemoteControlDevice=types.SimpleNamespace(RFRemoteControlDevice=object),
    )

    package = _install_module(monkeypatch, PACKAGE_NAME)
    package.__path__ = []
    _install_module(
        monkeypatch,
        f"{PACKAGE_NAME}.const",
        DOMAIN="localtuya_rc",
        DEFAULT_FRIENDLY_NAME="Tuya IR Remote Control",
        CONF_LOCAL_KEY="local_key",
        CONF_PROTOCOL_VERSION="protocol_version",
        CONF_CONTROL_TYPE="control_type",
        CONF_CLOUD_INFO="cloud_info",
        CONF_PERSISTENT_CONNECTION="persistent_connection",
        CONF_HAS_TEMP_HUMIDITY_SENSOR="has_temp_humidity_sensor",
        CODE_STORAGE_VERSION=1,
        CODE_STORAGE_CODES="localtuya_rc_codes",
        NOTIFICATION_TITLE="Tuya IR Remote Control",
        DEFAULT_PERSISTENT_CONNECTION=False,
    )
    _install_module(
        monkeypatch,
        f"{PACKAGE_NAME}.rc_encoder",
        rc_auto_encode=lambda value: value,
        rc_auto_decode=lambda value, **_kwargs: value,
    )

    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.remote", REMOTE_PATH
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


class _FakeDevice:
    """Stand-in for tinytuya's Contrib.IRRemoteControlDevice."""

    instance = None

    def __init__(self, statuses, control_type=1):
        self.control_type = control_type
        self.status_calls = 0
        self.closed = False
        self._statuses = iter(statuses)
        _FakeDevice.instance = self

    def status(self):
        self.status_calls += 1
        return next(self._statuses)

    def study_end(self):
        pass

    def close(self):
        self.closed = True


class _FakeConfigEntries:
    def __init__(self):
        self.updated_entries = []

    def async_update_entry(self, entry, data):
        entry.data = data
        self.updated_entries.append((entry, data))


class _FakeHass:
    def __init__(self):
        self.config_entries = _FakeConfigEntries()
        self.loop = types.SimpleNamespace(call_soon_threadsafe=lambda fn: fn())


def _make_remote(remote_module, statuses, entry=None, control_type=1):
    device = _FakeDevice(list(statuses), control_type=control_type)
    remote_module.Contrib.IRRemoteControlDevice = lambda **_kwargs: device
    remote = remote_module.TuyaRC(
        "Test",
        "device-id",
        "127.0.0.1",
        "local-key",
        "3.3",
        control_type=control_type,
        entry=entry,
    )
    return remote, device


# --- capturing dps from status() ---


def test_update_availibility_captures_temp_and_humidity_dps(remote_module):
    remote, _device = _make_remote(
        remote_module, [{"dps": {"101": 231, "102": 65, "201": "..."}}]
    )

    remote._update_availibility_locked()

    assert remote.temperature == 23.1
    assert remote.humidity == 65
    assert remote.temp_humidity_supported is True


def test_temperature_and_humidity_are_none_without_matching_dps(remote_module):
    remote, _device = _make_remote(remote_module, [{"dps": {"201": "..."}}])

    remote._update_availibility_locked()

    assert remote.temperature is None
    assert remote.humidity is None
    assert remote.temp_humidity_supported is False


def test_dps_are_not_cleared_by_a_later_transient_failure(remote_module):
    """A momentary unavailable poll must not wipe out previously known
    sensor values - the entities should keep showing the last known reading
    (while going unavailable), not flip to unknown."""
    remote, _device = _make_remote(
        remote_module,
        [{"dps": {"101": 231, "102": 65}}, None],
    )

    remote._update_availibility_locked()
    assert remote.temperature == 23.1

    remote._update_availibility_locked()
    assert remote.available is False
    assert remote.temperature == 23.1


# --- extra_state_attributes mirroring (drives sensor.py's state tracking) ---


def test_extra_state_attributes_include_temp_and_humidity_when_supported(remote_module):
    remote, _device = _make_remote(
        remote_module, [{"dps": {"101": 231, "102": 65}}]
    )
    remote._update_availibility_locked()

    attrs = remote.extra_state_attributes

    assert attrs["temperature"] == 23.1
    assert attrs["humidity"] == 65


def test_extra_state_attributes_omit_temp_and_humidity_when_unsupported(remote_module):
    remote, _device = _make_remote(remote_module, [{"dps": {}}])
    remote._update_availibility_locked()

    attrs = remote.extra_state_attributes

    assert "temperature" not in attrs
    assert "humidity" not in attrs


# --- persisting detection to the config entry ---


def test_persists_has_temp_humidity_sensor_once_detected(remote_module):
    entry = types.SimpleNamespace(data={}, entry_id="entry-1")
    remote, _device = _make_remote(
        remote_module, [{"dps": {"101": 231, "102": 65}}], entry=entry
    )
    remote.hass = _FakeHass()

    remote._update_availibility_locked()

    assert entry.data["has_temp_humidity_sensor"] is True


def test_does_not_persist_when_dps_absent(remote_module):
    entry = types.SimpleNamespace(data={}, entry_id="entry-1")
    remote, _device = _make_remote(remote_module, [{"dps": {}}], entry=entry)
    remote.hass = _FakeHass()

    remote._update_availibility_locked()

    assert "has_temp_humidity_sensor" not in entry.data


def test_temp_humidity_supported_survives_offline_poll_once_persisted(remote_module):
    """Once the sensor has been detected and persisted, a later poll that
    can't reach the device (e.g. it's offline at HA startup) must still
    report the device as sensor-capable, so sensor.py keeps the entities."""
    entry = types.SimpleNamespace(
        data={"has_temp_humidity_sensor": True}, entry_id="entry-1"
    )
    remote, _device = _make_remote(remote_module, [None], entry=entry)

    remote._update_availibility_locked()

    assert remote.available is False
    assert remote.temp_humidity_supported is True


def test_does_not_repersist_when_already_persisted(remote_module):
    # control_type is pre-matched to the fake device's so _persist_control_type
    # also no-ops, isolating the assertion to has_temp_humidity_sensor.
    entry = types.SimpleNamespace(
        data={"has_temp_humidity_sensor": True, "control_type": 1},
        entry_id="entry-1",
    )
    remote, _device = _make_remote(
        remote_module, [{"dps": {"101": 231, "102": 65}}], entry=entry
    )
    remote.hass = _FakeHass()

    remote._update_availibility_locked()

    assert remote.hass.config_entries.updated_entries == []
