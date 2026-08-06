"""Tests for the infrared (adapter) platform.

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
INFRARED_PATH = ROOT / "custom_components" / "localtuya_rc" / "infrared.py"
PACKAGE_NAME = "localtuya_rc_infrared_test"


def _install_module(monkeypatch, name, **attributes):
    module = types.ModuleType(name)
    module.__dict__.update(attributes)
    monkeypatch.setitem(sys.modules, name, module)
    return module


class _Unsub:
    """Counting no-op unsub callable, so tests can assert an old
    subscription was actually torn down before a new one is made."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1


class FakeInfraredEmitterEntity:
    """Stand-in for homeassistant.components.infrared.InfraredEmitterEntity."""

    entity_id = None  # unset until the entity platform assigns it, like real Entity

    def __init__(self):
        self.hass = None
        self._on_remove_callbacks = []
        self.write_calls = 0

    async def async_added_to_hass(self):
        pass

    def async_on_remove(self, callback_):
        self._on_remove_callbacks.append(callback_)

    def async_write_ha_state(self):
        self.write_calls += 1


class FakeRemote:
    """Stand-in for the TuyaRC remote entity that infrared.py wraps."""

    def __init__(self, unique_id="device-id", available=True, entity_id="remote.test", hass=object()):
        self.unique_id = unique_id
        self.available = available
        self.entity_id = entity_id
        self.hass = hass
        self.device_info = {"identifiers": {("localtuya_rc", unique_id)}}
        self.sent_pulses = None

    async def async_send_ir_pulses(self, pulses):
        self.sent_pulses = pulses


class FakeCommand:
    """Stand-in for infrared_protocols.commands.Command."""

    def __init__(self, timings):
        self._timings = timings

    def get_raw_timings(self):
        return list(self._timings)


@pytest.fixture
def infrared_module(monkeypatch):
    homeassistant = _install_module(monkeypatch, "homeassistant")
    homeassistant.__path__ = []
    helpers = _install_module(monkeypatch, "homeassistant.helpers")
    helpers.__path__ = []
    components = _install_module(monkeypatch, "homeassistant.components")
    components.__path__ = []

    _install_module(
        monkeypatch,
        "homeassistant.core",
        HomeAssistant=object,
        callback=lambda func: func,
    )
    _install_module(monkeypatch, "homeassistant.config_entries", ConfigEntry=object)

    class HomeAssistantError(Exception):
        """Minimal Home Assistant error type for the unit under test."""

    _install_module(
        monkeypatch,
        "homeassistant.exceptions",
        HomeAssistantError=HomeAssistantError,
    )

    tracked_calls = []
    state_unsubs = []
    tracked_registry_calls = []
    registry_unsubs = []

    def _fake_track_state_change_event(hass, entity_ids, action):
        tracked_calls.append((hass, entity_ids, action))
        unsub = _Unsub()
        state_unsubs.append(unsub)
        return unsub

    def _fake_track_entity_registry_updated_event(hass, entity_id, action):
        tracked_registry_calls.append((hass, entity_id, action))
        unsub = _Unsub()
        registry_unsubs.append(unsub)
        return unsub

    _install_module(
        monkeypatch,
        "homeassistant.helpers.event",
        async_track_state_change_event=_fake_track_state_change_event,
        async_track_entity_registry_updated_event=_fake_track_entity_registry_updated_event,
    )
    _install_module(
        monkeypatch,
        "homeassistant.components.infrared",
        InfraredCommand=FakeCommand,
        InfraredEmitterEntity=FakeInfraredEmitterEntity,
    )

    package = _install_module(monkeypatch, PACKAGE_NAME)
    package.__path__ = []
    _install_module(monkeypatch, f"{PACKAGE_NAME}.const", DOMAIN="localtuya_rc")

    spec = importlib.util.spec_from_file_location(
        f"{PACKAGE_NAME}.infrared", INFRARED_PATH
    )
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    module._tracked_calls = tracked_calls
    module._state_unsubs = state_unsubs
    module._tracked_registry_calls = tracked_registry_calls
    module._registry_unsubs = registry_unsubs
    return module


# --- _timings_to_pulses (the signed -> unsigned conversion) ---


def test_timings_abs_converts_signs(infrared_module):
    assert infrared_module._timings_to_pulses([9000, -4500, 560, -1690, 560]) == [
        9000,
        4500,
        560,
        1690,
        560,
    ]


def test_timings_drops_leading_space(infrared_module):
    """A leading space has nothing to merge into and must be dropped."""
    assert infrared_module._timings_to_pulses([-300, 9000, -4500]) == [9000, 4500]


def test_timings_merges_consecutive_same_sign_entries(infrared_module):
    """Position determines mark/space, so adjacent same-sign entries collapse."""
    assert infrared_module._timings_to_pulses([100, 200, -50, -50, 300]) == [
        300,
        100,
        300,
    ]


def test_timings_clamps_to_16_bit_unsigned_max(infrared_module):
    """E.g. NEC's ~96ms repeat-gap exceeds tinytuya's 16-bit encoding."""
    assert infrared_module._timings_to_pulses([9000, -96000]) == [
        9000,
        infrared_module._MAX_PULSE_DURATION_US,
    ]


def test_timings_drops_multiple_leading_spaces_without_inverting_frame(infrared_module):
    """A run of leading spaces must merge into one before being dropped, or
    the second space lands at an even (mark) index and inverts the frame."""
    assert infrared_module._timings_to_pulses([-300, -200, 9000, -4500]) == [9000, 4500]


def test_timings_raises_when_nothing_left_to_send(infrared_module):
    with pytest.raises(infrared_module.HomeAssistantError):
        infrared_module._timings_to_pulses([])

    with pytest.raises(infrared_module.HomeAssistantError):
        # A single leading space and nothing else.
        infrared_module._timings_to_pulses([-500])

    with pytest.raises(infrared_module.HomeAssistantError):
        # All-space input merges into one leading space, then drops to empty.
        infrared_module._timings_to_pulses([-100, -200])


# --- TuyaIRInfraredEmitter ---


def test_unique_id_is_derived_from_remote_and_distinct(infrared_module):
    remote = FakeRemote(unique_id="device-id")
    entity = infrared_module.TuyaIRInfraredEmitter(remote)

    assert entity.unique_id == "device-id_ir_emitter"
    assert entity.unique_id != remote.unique_id


def test_available_mirrors_remote_availability(infrared_module):
    remote = FakeRemote(available=False)
    entity = infrared_module.TuyaIRInfraredEmitter(remote)
    assert entity.available is False

    remote.available = True
    assert entity.available is True


def test_available_is_false_when_remote_has_no_hass(infrared_module):
    """A disabled/removed remote entity's hass becomes None."""
    remote = FakeRemote(available=True, hass=None)
    entity = infrared_module.TuyaIRInfraredEmitter(remote)

    assert entity.available is False


def test_device_info_delegates_to_remote(infrared_module):
    remote = FakeRemote()
    entity = infrared_module.TuyaIRInfraredEmitter(remote)
    assert entity.device_info is remote.device_info


def test_send_command_converts_signed_timings_to_unsigned_pulses(infrared_module):
    remote = FakeRemote()
    entity = infrared_module.TuyaIRInfraredEmitter(remote)
    command = FakeCommand([9000, -4500, 560, -1690, 560])

    asyncio.run(entity.async_send_command(command))

    assert remote.sent_pulses == [9000, 4500, 560, 1690, 560]


def test_send_command_raises_when_remote_unavailable(infrared_module):
    remote = FakeRemote(available=False)
    entity = infrared_module.TuyaIRInfraredEmitter(remote)
    command = FakeCommand([9000, -4500])

    with pytest.raises(infrared_module.HomeAssistantError):
        asyncio.run(entity.async_send_command(command))

    assert remote.sent_pulses is None


def test_send_command_wraps_non_home_assistant_errors(infrared_module):
    class BrokenCommand:
        def get_raw_timings(self):
            raise ValueError("malformed command")

    remote = FakeRemote()
    entity = infrared_module.TuyaIRInfraredEmitter(remote)

    with pytest.raises(infrared_module.HomeAssistantError):
        asyncio.run(entity.async_send_command(BrokenCommand()))

    assert remote.sent_pulses is None


def test_added_to_hass_subscribes_to_remote_entity_state(infrared_module):
    remote = FakeRemote(entity_id="remote.living_room", available=True)
    entity = infrared_module.TuyaIRInfraredEmitter(remote)
    entity.hass = object()

    asyncio.run(entity.async_added_to_hass())

    assert len(infrared_module._tracked_calls) == 1
    hass, entity_ids, action = infrared_module._tracked_calls[0]
    assert entity_ids == ["remote.living_room"]

    # Availability unchanged: must not write state on every poll cycle.
    assert entity.write_calls == 0
    action(None)
    assert entity.write_calls == 0

    # Availability actually changes: must write state exactly once.
    remote.available = False
    action(None)
    assert entity.write_calls == 1
    action(None)
    assert entity.write_calls == 1


def test_added_to_hass_skips_subscription_without_remote_entity_id(infrared_module):
    remote = FakeRemote(entity_id=None)
    entity = infrared_module.TuyaIRInfraredEmitter(remote)
    entity.hass = object()

    asyncio.run(entity.async_added_to_hass())

    assert infrared_module._tracked_calls == []


def test_added_to_hass_resubscribes_on_remote_entity_rename(infrared_module):
    """async_track_state_change_event filters on a fixed entity_id, so a
    rename of the wrapped remote entity must tear down the old subscription
    and re-subscribe under the new entity_id, not go silently stale."""
    remote = FakeRemote(entity_id="remote.old_id", available=True)
    entity = infrared_module.TuyaIRInfraredEmitter(remote)
    entity.hass = object()

    asyncio.run(entity.async_added_to_hass())

    assert len(infrared_module._tracked_registry_calls) == 1
    _, watched_entity_id, registry_action = infrared_module._tracked_registry_calls[0]
    assert watched_entity_id == "remote.old_id"
    old_state_unsub = infrared_module._state_unsubs[0]
    old_registry_unsub = infrared_module._registry_unsubs[0]

    registry_action(types.SimpleNamespace(data={"entity_id": "remote.new_id"}))

    assert old_state_unsub.calls == 1
    assert old_registry_unsub.calls == 1
    assert [entity_ids for _, entity_ids, _ in infrared_module._tracked_calls] == [
        ["remote.old_id"],
        ["remote.new_id"],
    ]
    assert [eid for _, eid, _ in infrared_module._tracked_registry_calls] == [
        "remote.old_id",
        "remote.new_id",
    ]
    assert entity.write_calls == 1


# --- async_setup_entry wiring ---


def test_setup_entry_adds_emitter_when_remote_entity_present(infrared_module):
    remote = FakeRemote()
    hass = types.SimpleNamespace(data={"localtuya_rc": {"entry-1": {"remote_entity": remote}}})
    entry = types.SimpleNamespace(entry_id="entry-1")
    added = []

    asyncio.run(infrared_module.async_setup_entry(hass, entry, added.append))

    assert len(added) == 1
    (entities,) = added
    assert len(entities) == 1
    assert isinstance(entities[0], infrared_module.TuyaIRInfraredEmitter)
    assert entities[0]._remote is remote


def test_setup_entry_skips_when_remote_entity_missing(infrared_module):
    hass = types.SimpleNamespace(data={})
    entry = types.SimpleNamespace(entry_id="entry-1")
    added = []

    asyncio.run(infrared_module.async_setup_entry(hass, entry, added.append))

    assert added == []
