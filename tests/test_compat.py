"""既存連携（NaNaLinks/homeassistant_nature_remo v0.2.3）からの差し替え互換のテスト。"""

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nature_remo.const import DOMAIN

from .conftest import FakeNatureApi, setup_integration

# 既存連携が登録していたentity: (platform, unique_id, entity_id, original_name)
LEGACY_ENTITIES = [
    (
        "climate",
        "nature_remo_climate_ac-living",
        "climate.nature_remo_living",
        "Nature Remo Living",
    ),
    (
        "climate",
        "nature_remo_climate_ac-study",
        "climate.nature_remo_study",
        "Nature Remo Study",
    ),
    (
        "climate",
        "nature_remo_climate_ac-bedroom",
        "climate.nature_remo_bedroom",
        "Nature Remo Bedroom",
    ),
    (
        "sensor",
        "nature_remo_sensor_dev-living_te",
        "sensor.nature_remo_living_remo_temperature",
        "Nature Remo Living Remo Temperature",
    ),
    (
        "sensor",
        "nature_remo_sensor_dev-living_hu",
        "sensor.nature_remo_living_remo_humidity",
        "Nature Remo Living Remo Humidity",
    ),
    (
        "sensor",
        "nature_remo_sensor_dev-study_te",
        "sensor.nature_remo_study_remo_temperature",
        "Nature Remo Study Remo Temperature",
    ),
    (
        "sensor",
        "nature_remo_sensor_dev-study_hu",
        "sensor.nature_remo_study_remo_humidity",
        "Nature Remo Study Remo Humidity",
    ),
]
LEGACY_DEVICES = {"dev-living": "Living Remo", "dev-study": "Study Remo"}


def _register_legacy(
    hass: HomeAssistant, entry: MockConfigEntry
) -> dict[str, dr.DeviceEntry]:
    """既存連携と同じidentifiersのデバイスと、そこにぶら下がるentityを登録する。"""
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    devices = {
        device_id: device_registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={(DOMAIN, device_id)},
            name=name,
            manufacturer="Nature",
            model="Remo/1.14.6",
        )
        for device_id, name in LEGACY_DEVICES.items()
    }
    device_of = {
        "nature_remo_climate_ac-living": "dev-living",
        "nature_remo_climate_ac-study": "dev-study",
        "nature_remo_climate_ac-bedroom": "dev-living",
    }
    for platform, unique_id, entity_id, original_name in LEGACY_ENTITIES:
        remo_id = device_of.get(unique_id) or unique_id.split("_")[3]
        entity_registry.async_get_or_create(
            platform,
            DOMAIN,
            unique_id,
            suggested_object_id=entity_id.split(".")[1],
            config_entry=entry,
            device_id=devices[remo_id].id,
            original_name=original_name,
        )
    return devices


async def test_takes_over_legacy_entities(
    hass: HomeAssistant,
    fake_api: FakeNatureApi,
    config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
) -> None:
    """unique_idが一致し、entity_idを変えずに引き継ぐ。entity名も同じ。"""
    config_entry.add_to_hass(hass)
    _register_legacy(hass, config_entry)

    await setup_integration(hass, config_entry)

    assert config_entry.state is ConfigEntryState.LOADED
    for platform, unique_id, entity_id, original_name in LEGACY_ENTITIES:
        assert entity_registry.async_get_entity_id(platform, DOMAIN, unique_id) == (
            entity_id
        )
        entry = entity_registry.async_get(entity_id)
        assert entry is not None
        assert entry.original_name == original_name
        assert not entry.has_entity_name
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state != "unavailable"
    # 新しいentityを追加で作っていない
    assert len(
        er.async_entries_for_config_entry(entity_registry, config_entry.entry_id)
    ) == (len(LEGACY_ENTITIES))


async def test_reuses_legacy_devices(
    hass: HomeAssistant,
    fake_api: FakeNatureApi,
    config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Remo本体IDのidentifiersで既存デバイスを使い、climateとsensorを同じデバイスに付ける。"""
    config_entry.add_to_hass(hass)
    devices = _register_legacy(hass, config_entry)

    await setup_integration(hass, config_entry)

    registered = dr.async_entries_for_config_entry(
        device_registry, config_entry.entry_id
    )
    assert sorted(d.id for d in registered) == sorted(d.id for d in devices.values())
    living = devices["dev-living"].id
    on_living = sorted(
        e.unique_id for e in er.async_entries_for_device(entity_registry, living)
    )
    assert on_living == [
        "nature_remo_climate_ac-bedroom",
        "nature_remo_climate_ac-living",
        "nature_remo_sensor_dev-living_hu",
        "nature_remo_sensor_dev-living_te",
    ]
    device = device_registry.async_get(living)
    assert isinstance(device, dr.DeviceEntry)
    assert device.identifiers == {(DOMAIN, "dev-living")}
    assert device.name == "Living Remo"
    assert device.manufacturer == "Nature"
    assert device.sw_version == "Remo/1.14.6"


async def test_fresh_install_identifiers(
    hass: HomeAssistant,
    loaded_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """新規導入でも同じunique_idとidentifiersで登録する。"""
    unique_ids = sorted(
        e.unique_id
        for e in er.async_entries_for_config_entry(
            entity_registry, loaded_entry.entry_id
        )
    )
    assert unique_ids == sorted(unique_id for _, unique_id, _, _ in LEGACY_ENTITIES)
    identifiers = sorted(
        identifier
        for device in dr.async_entries_for_config_entry(
            device_registry, loaded_entry.entry_id
        )
        for identifier in device.identifiers
    )
    assert identifiers == [(DOMAIN, "dev-living"), (DOMAIN, "dev-study")]
