"""sensorのテスト。"""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.sensor import ATTR_STATE_CLASS, SensorStateClass
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    PERCENTAGE,
    STATE_UNAVAILABLE,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import async_fire_time_changed

from .conftest import FakeNatureApi, entity_id_of

pytestmark = pytest.mark.usefixtures("loaded_entry")


def _state(hass: HomeAssistant, unique_id: str) -> State:
    state = hass.states.get(entity_id_of(hass, "sensor", unique_id))
    assert state is not None
    return state


async def test_values(hass: HomeAssistant) -> None:
    """Remo本体の温度・湿度をそのまま値にする。"""
    temperature = _state(hass, "nature_remo_sensor_dev-living_te")
    humidity = _state(hass, "nature_remo_sensor_dev-living_hu")

    assert temperature.state == "25.4"
    assert temperature.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfTemperature.CELSIUS
    assert temperature.attributes[ATTR_DEVICE_CLASS] == "temperature"
    assert temperature.attributes[ATTR_STATE_CLASS] == SensorStateClass.MEASUREMENT
    # 既存連携と同じく、APIが整数で返した湿度は整数のまま
    assert humidity.state == "48"
    assert humidity.attributes[ATTR_UNIT_OF_MEASUREMENT] == PERCENTAGE
    assert humidity.attributes[ATTR_DEVICE_CLASS] == "humidity"


async def test_only_measured_values(
    hass: HomeAssistant, entity_registry: er.EntityRegistry
) -> None:
    """計測値を持つRemo本体の温度・湿度だけを作る（照度・人感は作らない）。"""
    unique_ids = sorted(
        entry.unique_id
        for entry in entity_registry.entities.values()
        if entry.domain == "sensor"
    )

    assert unique_ids == [
        "nature_remo_sensor_dev-living_hu",
        "nature_remo_sensor_dev-living_te",
        "nature_remo_sensor_dev-study_hu",
        "nature_remo_sensor_dev-study_te",
    ]


async def test_value_updates(
    hass: HomeAssistant, fake_api: FakeNatureApi, freezer: FrozenDateTimeFactory
) -> None:
    """定期更新で値を更新する。"""
    fake_api.devices[0]["newest_events"]["te"]["val"] = 27.0

    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert _state(hass, "nature_remo_sensor_dev-living_te").state == "27.0"


async def test_unavailable_when_device_disappears(
    hass: HomeAssistant, fake_api: FakeNatureApi, freezer: FrozenDateTimeFactory
) -> None:
    """Remo本体が一覧から消えたら利用不可にする。"""
    del fake_api.devices[0]

    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = _state(hass, "nature_remo_sensor_dev-living_te")
    assert state.state == STATE_UNAVAILABLE
