"""Tests for the sensor platform (temperature/humidity).

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
SENSOR_PATH = ROOT / "custom_components" / "localtuya_rc" / "sensor.py"
PACKAGE_NAME = "localtuya_rc_sensor_test"


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


class FakeSensorEntity:
    """Stand-in for homeassistant.components.sensor.SensorEntity."""

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
    """Stand-in for the TuyaRC remote entity that sensor.py wraps."""

    def __init__(
        self,
        unique_id="device-id",
        available=True,
        entity_id="remote.test",
        hass=object(),
        temperature=23.1,
        humidity=65,
        temp_humidity_supported=True,
    ):
        self.unique_id = unique_id
        self.available = available
        self.entity_id = entity_id
        self.hass = hass
        self.device_info = {"identifiers": {("localtuya_rc", unique_id)}}
        self.temperature = temperature
        self.humidity = humidity
        self.temp_humidity_supported = temp_humidity_supported


@pytest.fixture
def sensor_module(monkeypatch):
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
    _install_module(
        monkeypatch,
        "homeassistant.const",
        PERCENTAGE="%",
        UnitOfTemperature=types.SimpleNamespace(CELSIUS="°C"),
    )

    _install_module(
        monkeypatch,
        "homeassistant.components.sensor",
        SensorDeviceClass=types.SimpleNamespace(TEMPERATURE="temperature", HUMIDITY="humidity"),
        SensorEntity=FakeSensorEntity,
        SensorStateClass=types.SimpleNamespace(MEASUREMENT="measurement"),
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

    package = _install_module(monkeypatch, PACKAGE_NAME)
    package.__path__ = []
    _install_module(monkeypatch, f"{PACKAGE_NAME}.const", DOMAIN="localtuya_rc")

    spec = importlib.util.spec_from_file_location(f"{PACKAGE_NAME}.sensor", SENSOR_PATH)
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    module._tracked_calls = tracked_calls
    module._state_unsubs = state_unsubs
    module._tracked_registry_calls = tracked_registry_calls
    module._registry_unsubs = registry_unsubs
    return module


# --- TuyaIRTemperatureSensor / TuyaIRHumiditySensor ---


def test_unique_ids_are_derived_from_remote_and_distinct(sensor_module):
    remote = FakeRemote(unique_id="device-id")
    temp = sensor_module.TuyaIRTemperatureSensor(remote)
    humidity = sensor_module.TuyaIRHumiditySensor(remote)

    assert temp.unique_id == "device-id_temperature"
    assert humidity.unique_id == "device-id_humidity"
    assert temp.unique_id != humidity.unique_id


def test_native_value_reads_through_to_remote(sensor_module):
    remote = FakeRemote(temperature=21.5, humidity=48)
    temp = sensor_module.TuyaIRTemperatureSensor(remote)
    humidity = sensor_module.TuyaIRHumiditySensor(remote)

    assert temp.native_value == 21.5
    assert humidity.native_value == 48


def test_available_mirrors_remote_availability(sensor_module):
    remote = FakeRemote(available=False)
    entity = sensor_module.TuyaIRTemperatureSensor(remote)
    assert entity.available is False

    remote.available = True
    assert entity.available is True


def test_available_is_false_when_remote_has_no_hass(sensor_module):
    """A disabled/removed remote entity's hass becomes None."""
    remote = FakeRemote(available=True, hass=None)
    entity = sensor_module.TuyaIRHumiditySensor(remote)

    assert entity.available is False


def test_device_info_delegates_to_remote(sensor_module):
    remote = FakeRemote()
    entity = sensor_module.TuyaIRTemperatureSensor(remote)
    assert entity.device_info is remote.device_info


def test_added_to_hass_subscribes_to_remote_entity_state_and_mirrors_updates(
    sensor_module,
):
    remote = FakeRemote(entity_id="remote.living_room")
    entity = sensor_module.TuyaIRTemperatureSensor(remote)
    entity.hass = object()

    asyncio.run(entity.async_added_to_hass())

    assert len(sensor_module._tracked_calls) == 1
    _hass, entity_ids, action = sensor_module._tracked_calls[0]
    assert entity_ids == ["remote.living_room"]

    # Every remote state change re-publishes our own state, unlike
    # infrared.py's availability-only tracking - the cached value changes
    # on nearly every poll.
    assert entity.write_calls == 0
    action(None)
    assert entity.write_calls == 1
    action(None)
    assert entity.write_calls == 2


def test_added_to_hass_skips_subscription_without_remote_entity_id(sensor_module):
    remote = FakeRemote(entity_id=None)
    entity = sensor_module.TuyaIRHumiditySensor(remote)
    entity.hass = object()

    asyncio.run(entity.async_added_to_hass())

    assert sensor_module._tracked_calls == []


def test_added_to_hass_resubscribes_on_remote_entity_rename(sensor_module):
    """async_track_state_change_event filters on a fixed entity_id, so a
    rename of the wrapped remote entity must tear down the old subscription
    and re-subscribe under the new entity_id, not go silently stale."""
    remote = FakeRemote(entity_id="remote.old_id")
    entity = sensor_module.TuyaIRTemperatureSensor(remote)
    entity.hass = object()

    asyncio.run(entity.async_added_to_hass())

    assert len(sensor_module._tracked_registry_calls) == 1
    _, watched_entity_id, registry_action = sensor_module._tracked_registry_calls[0]
    assert watched_entity_id == "remote.old_id"
    old_state_unsub = sensor_module._state_unsubs[0]
    old_registry_unsub = sensor_module._registry_unsubs[0]

    registry_action(types.SimpleNamespace(data={"entity_id": "remote.new_id"}))

    assert old_state_unsub.calls == 1
    assert old_registry_unsub.calls == 1
    assert [entity_ids for _, entity_ids, _ in sensor_module._tracked_calls] == [
        ["remote.old_id"],
        ["remote.new_id"],
    ]
    assert entity.write_calls == 1


# --- async_setup_entry wiring ---


def test_setup_entry_adds_sensors_when_supported(sensor_module):
    remote = FakeRemote(temp_humidity_supported=True)
    hass = types.SimpleNamespace(data={"localtuya_rc": {"entry-1": {"remote_entity": remote}}})
    entry = types.SimpleNamespace(entry_id="entry-1")
    added = []

    asyncio.run(sensor_module.async_setup_entry(hass, entry, added.append))

    assert len(added) == 1
    (entities,) = added
    assert len(entities) == 2
    assert isinstance(entities[0], sensor_module.TuyaIRTemperatureSensor)
    assert isinstance(entities[1], sensor_module.TuyaIRHumiditySensor)
    assert entities[0]._remote is remote
    assert entities[1]._remote is remote


def test_setup_entry_skips_when_remote_entity_missing(sensor_module):
    hass = types.SimpleNamespace(data={})
    entry = types.SimpleNamespace(entry_id="entry-1")
    added = []

    asyncio.run(sensor_module.async_setup_entry(hass, entry, added.append))

    assert added == []


def test_setup_entry_skips_when_device_does_not_support_sensor(sensor_module):
    remote = FakeRemote(temp_humidity_supported=False)
    hass = types.SimpleNamespace(data={"localtuya_rc": {"entry-1": {"remote_entity": remote}}})
    entry = types.SimpleNamespace(entry_id="entry-1")
    added = []

    asyncio.run(sensor_module.async_setup_entry(hass, entry, added.append))

    assert added == []
