"""Regression tests for unavailable IR bridge recovery."""

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
REMOTE_PATH = ROOT / "custom_components" / "localtuya_rc" / "remote.py"
MANIFEST_PATH = ROOT / "custom_components" / "localtuya_rc" / "manifest.json"
PACKAGE_NAME = "localtuya_rc_test"


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
    # WHY: this project has no Home Assistant test harness.
    # WHEN: remove this when one is added.
    # REAL: use Home Assistant's EntityPlatform and service-call fixtures.
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


def _status_error(code):
    return {"Error": "Device error", "Err": code, "Payload": None}


def _make_remote(remote_module, statuses, control_type=1, study_end_error=None):
    class Device:
        instance = None

        def __init__(self, **_kwargs):
            self.control_type = control_type
            self.status_calls = 0
            self.study_end_calls = 0
            self.closed = False
            self._statuses = iter(statuses)
            Device.instance = self

        def status(self):
            self.status_calls += 1
            return next(self._statuses)

        def study_end(self):
            self.study_end_calls += 1
            if study_end_error:
                raise study_end_error

        def close(self):
            self.closed = True

    remote_module.Contrib.IRRemoteControlDevice = Device
    return remote_module.TuyaRC(
        "Test",
        "device-id",
        "127.0.0.1",
        "local-key",
        "3.3",
        control_type=control_type,
    ), Device


@pytest.mark.parametrize(
    "initial_status",
    [
        _status_error("902"),
        _status_error(902),
        _status_error("900"),
        _status_error(900),
        None,
    ],
    ids=[
        "string-timeout",
        "numeric-timeout",
        "string-json",
        "numeric-json",
        "empty-response",
    ],
)
def test_reachable_silent_device_wakes_after_study_end(
    remote_module, initial_status
):
    """A reachable bridge that ignores status wakes after study_end."""
    remote, device_class = _make_remote(
        remote_module, [initial_status, {"dps": {}}]
    )
    remote._update_availibility_locked()

    assert remote.available is True
    assert device_class.instance.status_calls == 2
    assert device_class.instance.study_end_calls == 1
    assert device_class.instance.closed is False


@pytest.mark.parametrize(
    "retry_status",
    [None, _status_error("902"), _status_error("900")],
    ids=["empty-response", "timeout", "json-error"],
)
def test_silent_device_remains_unavailable_after_one_wake_retry(
    remote_module, retry_status
):
    """A wake gets one retry, then deinitializes if the bridge stays silent."""

    remote, device_class = _make_remote(remote_module, [None, retry_status])
    remote._update_availibility_locked()

    assert remote.available is False
    assert device_class.instance.status_calls == 2
    assert device_class.instance.study_end_calls == 1
    assert device_class.instance.closed is True


@pytest.mark.parametrize("error_code", ["901", "904", "905", "914"])
def test_nonrecoverable_status_errors_do_not_send_wake_command(
    remote_module, error_code
):
    """Unreachable or invalid devices must not receive a recovery command."""

    remote, device_class = _make_remote(
        remote_module, [_status_error(error_code)]
    )
    remote._update_availibility_locked()

    assert remote.available is False
    assert device_class.instance.status_calls == 1
    assert device_class.instance.study_end_calls == 0
    assert device_class.instance.closed is True


def test_unknown_control_type_does_not_send_wake_command(remote_module):
    """Auto-detection failures must not call study_end without a control type."""

    remote, device_class = _make_remote(
        remote_module, [_status_error("902")], control_type=0
    )
    remote._update_availibility_locked()

    assert remote.available is False
    assert device_class.instance.study_end_calls == 0
    assert device_class.instance.closed is True


def test_failed_wake_deinitializes_device(remote_module):
    """A failed wake attempt must retain the existing clean recovery path."""

    remote, device_class = _make_remote(
        remote_module,
        [_status_error("902")],
        study_end_error=RuntimeError("wake failed"),
    )
    remote._update_availibility_locked()

    assert remote.available is False
    assert device_class.instance.study_end_calls == 1
    assert device_class.instance.closed is True


def test_available_device_does_not_receive_wake_command(remote_module):
    """Healthy status responses must remain a single request."""

    remote, device_class = _make_remote(remote_module, [{"dps": {}}])
    remote._update_availibility_locked()

    assert remote.available is True
    assert device_class.instance.status_calls == 1
    assert device_class.instance.study_end_calls == 0


def test_platform_declares_single_parallel_request(remote_module):
    """Home Assistant must serialize this remote's polls and actions."""

    assert remote_module.PARALLEL_UPDATES == 1


def test_requires_tinytuya_timeout_error_support():
    """The recovery probe requires tinytuya's distinct timeout response."""

    manifest = json.loads(MANIFEST_PATH.read_text())
    requirement = next(
        item
        for item in manifest["requirements"]
        if item.startswith("tinytuya>=")
    )
    version = tuple(int(part) for part in requirement.split(">=", 1)[1].split("."))

    assert version >= (1, 20, 0)
