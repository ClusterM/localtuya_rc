"""Tests for __init__.py's platform-forwarding order, INFRARED_PLATFORM_AVAILABLE
detection, and unload/hass.data cleanup.

Stubs homeassistant.* like test_remote_recovery.py (no HA test harness here)
and drives async entry points with asyncio.run() (CI has no pytest-asyncio).
"""

import asyncio
import importlib.util
import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT_PATH = ROOT / "custom_components" / "localtuya_rc" / "__init__.py"
PACKAGE_NAME = "localtuya_rc_init_test"


def _install_module(monkeypatch, name, **attributes):
    module = types.ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    return module


def _load_init_module(monkeypatch, *, has_infrared_platform):
    """Import __init__.py fresh, with Platform.INFRARED present or absent.

    INFRARED_PLATFORM_AVAILABLE is computed once at import time, so each
    scenario needs its own module instance rather than reusing a fixture.
    """
    homeassistant = _install_module(monkeypatch, "homeassistant")
    homeassistant.__path__ = []
    helpers = _install_module(monkeypatch, "homeassistant.helpers")
    helpers.__path__ = []

    _install_module(monkeypatch, "voluptuous")
    _install_module(monkeypatch, "homeassistant.helpers.config_validation")
    _install_module(monkeypatch, "homeassistant.core", HomeAssistant=object)
    _install_module(monkeypatch, "homeassistant.config_entries", ConfigEntry=object)

    platform_kwargs = {"REMOTE": "remote"}
    if has_infrared_platform:
        # Real HA's generated Platform enum gains INFRARED in the same
        # release that ships homeassistant.components.infrared.
        platform_kwargs["INFRARED"] = "infrared"
    _install_module(
        monkeypatch,
        "homeassistant.const",
        Platform=types.SimpleNamespace(**platform_kwargs),
    )

    package = _install_module(monkeypatch, PACKAGE_NAME)
    package.__path__ = []
    _install_module(monkeypatch, f"{PACKAGE_NAME}.const", DOMAIN="localtuya_rc")

    spec = importlib.util.spec_from_file_location(f"{PACKAGE_NAME}.__init__", INIT_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    return module


class _FakeConfigEntries:
    def __init__(self, unload_result=True, fail_platforms=()):
        self.forward_calls = []
        self.unload_calls = []
        self._unload_result = unload_result
        self._fail_platforms = fail_platforms

    async def async_forward_entry_setups(self, _entry, platforms):
        self.forward_calls.append(list(platforms))
        if any(p in self._fail_platforms for p in platforms):
            raise RuntimeError("boom")

    async def async_unload_platforms(self, _entry, platforms):
        self.unload_calls.append(list(platforms))
        return self._unload_result

    async def async_reload(self, _entry_id):
        pass


class _FakeHass:
    def __init__(self, unload_result=True, fail_platforms=()):
        self.data = {}
        self.config_entries = _FakeConfigEntries(
            unload_result=unload_result, fail_platforms=fail_platforms
        )


class _FakeEntry:
    def __init__(self, entry_id="entry-1"):
        self.entry_id = entry_id
        self.data = {}
        self.options = {}

    def async_on_unload(self, _func):
        pass

    def add_update_listener(self, _listener):
        return lambda: None


# --- feature detection ---


def test_infrared_platform_available_true_when_platform_enum_has_infrared(monkeypatch):
    module = _load_init_module(monkeypatch, has_infrared_platform=True)
    assert module.INFRARED_PLATFORM_AVAILABLE is True


def test_infrared_platform_available_false_when_platform_enum_lacks_infrared(monkeypatch):
    module = _load_init_module(monkeypatch, has_infrared_platform=False)
    assert module.INFRARED_PLATFORM_AVAILABLE is False


# --- async_setup_entry forwarding ---


def test_setup_entry_forwards_remote_then_infrared_separately_and_in_order(monkeypatch):
    """Two separate awaited calls, not one combined list: infrared.py's
    async_setup_entry looks up hass.data[...]["remote_entity"], which is
    only populated once the "remote" platform's entities have actually been
    added (see TuyaRC.async_added_to_hass in remote.py) - so "remote" must
    be forwarded and fully finish before "infrared" is forwarded at all."""
    module = _load_init_module(monkeypatch, has_infrared_platform=True)
    hass = _FakeHass()
    entry = _FakeEntry()

    asyncio.run(module.async_setup_entry(hass, entry))

    assert hass.config_entries.forward_calls == [
        [module.Platform.REMOTE],
        ["infrared"],
    ]


def test_setup_entry_survives_a_failed_infrared_forward(monkeypatch):
    """A broken infrared setup (e.g. a requirements-install failure) must
    not take down the config entry - "remote" already succeeded above it."""
    module = _load_init_module(monkeypatch, has_infrared_platform=True)
    hass = _FakeHass(fail_platforms=["infrared"])
    entry = _FakeEntry()

    result = asyncio.run(module.async_setup_entry(hass, entry))

    assert result is True
    assert hass.config_entries.forward_calls == [
        [module.Platform.REMOTE],
        ["infrared"],
    ]


def test_setup_entry_forwards_only_remote_when_infrared_unavailable(monkeypatch):
    module = _load_init_module(monkeypatch, has_infrared_platform=False)
    hass = _FakeHass()
    entry = _FakeEntry()

    asyncio.run(module.async_setup_entry(hass, entry))

    assert hass.config_entries.forward_calls == [[module.Platform.REMOTE]]


# --- async_unload_entry ---


def test_unload_entry_unloads_both_platforms_and_pops_data_on_success(monkeypatch):
    module = _load_init_module(monkeypatch, has_infrared_platform=True)
    hass = _FakeHass(unload_result=True)
    hass.data[module.DOMAIN] = {"entry-1": {"remote_entity": object()}}
    entry = _FakeEntry()

    result = asyncio.run(module.async_unload_entry(hass, entry))

    assert result is True
    assert hass.config_entries.unload_calls == [[module.Platform.REMOTE, "infrared"]]
    assert "entry-1" not in hass.data[module.DOMAIN]


def test_unload_entry_only_unloads_remote_when_infrared_unavailable(monkeypatch):
    module = _load_init_module(monkeypatch, has_infrared_platform=False)
    hass = _FakeHass(unload_result=True)
    entry = _FakeEntry()

    asyncio.run(module.async_unload_entry(hass, entry))

    assert hass.config_entries.unload_calls == [[module.Platform.REMOTE]]


def test_unload_entry_retains_hass_data_when_unload_fails(monkeypatch):
    module = _load_init_module(monkeypatch, has_infrared_platform=True)
    hass = _FakeHass(unload_result=False)
    hass.data[module.DOMAIN] = {"entry-1": {"remote_entity": object()}}
    entry = _FakeEntry()

    result = asyncio.run(module.async_unload_entry(hass, entry))

    assert result is False
    assert "entry-1" in hass.data[module.DOMAIN]
