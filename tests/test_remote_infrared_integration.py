"""Tests for remote.py's infrared-platform support: async_send_ir_pulses()
and async_added_to_hass() publishing itself into hass.data.

Stubs homeassistant.* like test_remote_recovery.py (no HA test harness here)
and drives async entry points with asyncio.run() (CI has no pytest-asyncio).
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REMOTE_PATH = ROOT / "custom_components" / "localtuya_rc" / "remote.py"
PACKAGE_NAME = "localtuya_rc_remote_infrared_test"


class _PlatformSchema:
    def extend(self, _schema):
        return self


class _FakeRemoteEntityBase:
    """Stand-in for homeassistant.components.remote.RemoteEntity.

    Only needs an async_added_to_hass() no-op: TuyaRC's own override calls
    super().async_added_to_hass() before doing its own work.
    """

    async def async_added_to_hass(self):
        pass


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
        RemoteEntity=_FakeRemoteEntityBase,
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


class _FakeHass:
    def __init__(self):
        self.data = {}

    async def async_add_executor_job(self, func, *args):
        return func(*args)


def _make_remote(remote_module, entry=None):
    remote = remote_module.TuyaRC(
        "Test", "device-id", "127.0.0.1", "local-key", "3.3", control_type=1, entry=entry
    )
    remote.hass = _FakeHass()
    return remote


# --- async_send_ir_pulses ---


def test_async_send_ir_pulses_calls_send_button_via_executor(remote_module):
    remote = _make_remote(remote_module)
    calls = []
    remote._send_button = lambda pulses: calls.append(pulses)

    asyncio.run(remote.async_send_ir_pulses([9000, 4500, 560]))

    assert calls == [[9000, 4500, 560]]


def test_async_send_ir_pulses_wraps_generic_exception_with_cause_preserved(remote_module):
    remote = _make_remote(remote_module)
    original = RuntimeError("boom")

    def _boom(_pulses):
        raise original

    remote._send_button = _boom

    with pytest.raises(remote_module.HomeAssistantError) as exc_info:
        asyncio.run(remote.async_send_ir_pulses([1, 2]))

    assert exc_info.value.__cause__ is original


def test_async_send_ir_pulses_does_not_double_wrap_home_assistant_error(remote_module):
    """_send_button() already raises a user-facing HomeAssistantError for the
    failure modes it knows about; async_send_ir_pulses must propagate that
    error as-is instead of wrapping it in a second, less specific one."""
    remote = _make_remote(remote_module)
    original = remote_module.HomeAssistantError("a specific, user-facing message")

    def _boom(_pulses):
        raise original

    remote._send_button = _boom

    with pytest.raises(remote_module.HomeAssistantError) as exc_info:
        asyncio.run(remote.async_send_ir_pulses([1, 2]))

    assert exc_info.value is original


# --- async_added_to_hass publishing for infrared.py ---


def test_async_added_to_hass_publishes_remote_entity_when_entry_present(remote_module):
    entry = types.SimpleNamespace(entry_id="entry-1")
    remote = _make_remote(remote_module, entry=entry)

    asyncio.run(remote.async_added_to_hass())

    assert remote.hass.data[remote_module.DOMAIN]["entry-1"]["remote_entity"] is remote


def test_async_added_to_hass_does_not_publish_without_a_config_entry(remote_module):
    """Legacy YAML platform setup (no config entry) has no infrared
    counterpart to publish for; must not populate hass.data at all."""
    remote = _make_remote(remote_module, entry=None)

    asyncio.run(remote.async_added_to_hass())

    assert remote.hass.data == {}


def test_will_remove_from_hass_clears_own_hass_data_entry(remote_module):
    entry = types.SimpleNamespace(entry_id="entry-1")
    remote = _make_remote(remote_module, entry=entry)
    asyncio.run(remote.async_added_to_hass())
    assert remote.hass.data[remote_module.DOMAIN]["entry-1"]["remote_entity"] is remote

    asyncio.run(remote.async_will_remove_from_hass())

    assert "remote_entity" not in remote.hass.data[remote_module.DOMAIN]["entry-1"]


def test_will_remove_from_hass_leaves_other_entitys_entry_alone(remote_module):
    """A stale/replaced remote entity being torn down must not clobber a
    different (newer) remote_entity already published for the same entry."""
    entry = types.SimpleNamespace(entry_id="entry-1")
    old_remote = _make_remote(remote_module, entry=entry)
    old_remote.hass.data = {remote_module.DOMAIN: {"entry-1": {"remote_entity": "someone-else"}}}

    asyncio.run(old_remote.async_will_remove_from_hass())

    assert old_remote.hass.data[remote_module.DOMAIN]["entry-1"]["remote_entity"] == "someone-else"
