"""climateのテスト。"""

from datetime import timedelta
from http import HTTPStatus
from typing import Any

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate.const import (
    ATTR_CURRENT_HUMIDITY,
    ATTR_CURRENT_TEMPERATURE,
    ATTR_FAN_MODE,
    ATTR_FAN_MODES,
    ATTR_HVAC_MODES,
    ATTR_MAX_TEMP,
    ATTR_MIN_TEMP,
    ATTR_SWING_MODE,
    ATTR_SWING_MODES,
    ATTR_TARGET_TEMP_STEP,
    DOMAIN as CLIMATE_DOMAIN,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_SWING_MODE,
    SERVICE_SET_TEMPERATURE,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_SUPPORTED_FEATURES,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.util.unit_system import US_CUSTOMARY_SYSTEM
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from .conftest import FakeNatureApi, entity_id_of

pytestmark = pytest.mark.usefixtures("loaded_entry")


def _entity_id(hass: HomeAssistant, appliance_id: str) -> str:
    return entity_id_of(hass, CLIMATE_DOMAIN, f"nature_remo_climate_{appliance_id}")


def _state(hass: HomeAssistant, appliance_id: str) -> State:
    state = hass.states.get(_entity_id(hass, appliance_id))
    assert state is not None
    return state


def _features(state: State) -> ClimateEntityFeature:
    return ClimateEntityFeature(state.attributes[ATTR_SUPPORTED_FEATURES])


async def _call(
    hass: HomeAssistant, service: str, appliance_id: str, **data: Any
) -> None:
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        service,
        {ATTR_ENTITY_ID: _entity_id(hass, appliance_id), **data},
        blocking=True,
    )


async def test_cooling_state(hass: HomeAssistant) -> None:
    """モード・温度範囲・風量を範囲から決め、室温湿度はRemo本体から取る。"""
    state = _state(hass, "ac-living")

    assert state.state == HVACMode.COOL
    assert state.attributes[ATTR_HVAC_MODES] == [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.DRY,
        HVACMode.HEAT,
        HVACMode.FAN_ONLY,
        HVACMode.AUTO,
    ]
    assert state.attributes[ATTR_TEMPERATURE] == 26
    assert state.attributes[ATTR_MIN_TEMP] == 16
    assert state.attributes[ATTR_MAX_TEMP] == 30
    assert state.attributes[ATTR_TARGET_TEMP_STEP] == 0.5
    assert state.attributes[ATTR_FAN_MODES] == ["auto", "1", "2", "3"]
    assert state.attributes[ATTR_FAN_MODE] == "auto"
    assert state.attributes[ATTR_CURRENT_TEMPERATURE] == 25.4
    assert state.attributes[ATTR_CURRENT_HUMIDITY] == 48


async def test_swing_hidden_when_only_empty_direction(hass: HomeAssistant) -> None:
    """上下風向が `[""]` だけの機種はSWING_MODEを出さない。"""
    state = _state(hass, "ac-living")

    assert _features(state) == (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.FAN_MODE
    )
    assert ATTR_SWING_MODES not in state.attributes


async def test_dry_with_empty_temperature(hass: HomeAssistant) -> None:
    """除湿で設定温度が空文字なら、設定温度なし・TARGET_TEMPERATUREなしにする。"""
    state = _state(hass, "ac-study")

    assert state.state == HVACMode.DRY
    assert ATTR_TEMPERATURE not in state.attributes
    assert _features(state) == (
        ClimateEntityFeature.FAN_MODE | ClimateEntityFeature.SWING_MODE
    )
    assert state.attributes[ATTR_SWING_MODES] == ["auto", "1", "2", "swing"]
    assert state.attributes[ATTR_SWING_MODE] == "auto"


async def test_power_off_state(hass: HomeAssistant) -> None:
    """button=power-offなら電源OFFとし、範囲は最後のモードのものを使う。"""
    state = _state(hass, "ac-bedroom")

    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_HVAC_MODES] == [
        HVACMode.OFF,
        HVACMode.COOL,
        HVACMode.HEAT,
    ]
    assert state.attributes[ATTR_TEMPERATURE] == 22
    assert state.attributes[ATTR_MIN_TEMP] == 16


async def test_set_hvac_mode(hass: HomeAssistant, fake_api: FakeNatureApi) -> None:
    """運転モードを送り、応答で状態を更新してからcoordinatorを更新する。"""
    get_count = fake_api.get_count

    await _call(hass, SERVICE_SET_HVAC_MODE, "ac-living", hvac_mode=HVACMode.HEAT)

    assert fake_api.posts == [("ac-living", {"operation_mode": "warm"})]
    state = _state(hass, "ac-living")
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 22
    assert fake_api.get_count == get_count + 2


async def test_set_hvac_mode_off(hass: HomeAssistant, fake_api: FakeNatureApi) -> None:
    """OFFはbutton=power-offを送る。"""
    await _call(hass, SERVICE_SET_HVAC_MODE, "ac-living", hvac_mode=HVACMode.OFF)

    assert fake_api.posts == [("ac-living", {"button": "power-off"})]
    assert _state(hass, "ac-living").state == HVACMode.OFF


async def test_switch_to_dry_returns_empty_temperature(
    hass: HomeAssistant, fake_api: FakeNatureApi
) -> None:
    """除湿に切り替えて応答のtempが空文字でも失敗しない（既存連携はValueError）。"""
    await _call(hass, SERVICE_SET_HVAC_MODE, "ac-study", hvac_mode=HVACMode.COOL)
    await _call(hass, SERVICE_SET_HVAC_MODE, "ac-study", hvac_mode=HVACMode.DRY)

    state = _state(hass, "ac-study")
    assert state.state == HVACMode.DRY
    assert ATTR_TEMPERATURE not in state.attributes
    assert not _features(state) & ClimateEntityFeature.TARGET_TEMPERATURE


async def test_off_after_dry(hass: HomeAssistant, fake_api: FakeNatureApi) -> None:
    """最後が除湿のエアコンもOFFにできる（既存連携は毎回落ちていた）。"""
    await _call(hass, SERVICE_SET_HVAC_MODE, "ac-study", hvac_mode=HVACMode.OFF)

    assert fake_api.posts == [("ac-study", {"button": "power-off"})]
    assert _state(hass, "ac-study").state == HVACMode.OFF


async def test_set_temperature(hass: HomeAssistant, fake_api: FakeNatureApi) -> None:
    """現在のモードと、範囲にあるAPIの文字列表現の温度を送る。"""
    await _call(hass, SERVICE_SET_TEMPERATURE, "ac-living", temperature=26.5)

    assert fake_api.posts == [
        ("ac-living", {"operation_mode": "cool", "temperature": "26.5"})
    ]
    assert _state(hass, "ac-living").attributes[ATTR_TEMPERATURE] == 26.5


async def test_set_temperature_with_hvac_mode(
    hass: HomeAssistant, fake_api: FakeNatureApi
) -> None:
    """hvac_modeつきなら、そのモードで温度を設定する。"""
    await _call(
        hass,
        SERVICE_SET_TEMPERATURE,
        "ac-bedroom",
        temperature=17,
        hvac_mode=HVACMode.HEAT,
    )

    assert fake_api.posts == [
        ("ac-bedroom", {"operation_mode": "warm", "temperature": "17"})
    ]
    state = _state(hass, "ac-bedroom")
    assert state.state == HVACMode.HEAT
    assert state.attributes[ATTR_TEMPERATURE] == 17


async def test_set_temperature_not_in_range(
    hass: HomeAssistant, fake_api: FakeNatureApi
) -> None:
    """範囲内でも選択肢にない温度は送らずに検証エラーにする。"""
    with pytest.raises(ServiceValidationError):
        await _call(hass, SERVICE_SET_TEMPERATURE, "ac-living", temperature=27.5)

    assert fake_api.posts == []


async def test_set_temperature_unsupported_in_dry(
    hass: HomeAssistant, fake_api: FakeNatureApi
) -> None:
    """温度設定のないモードでは温度を設定できない。"""
    with pytest.raises(ServiceValidationError):
        await _call(hass, SERVICE_SET_TEMPERATURE, "ac-study", temperature=25)

    assert fake_api.posts == []


async def test_set_unsupported_hvac_mode(
    hass: HomeAssistant, fake_api: FakeNatureApi
) -> None:
    """範囲にないモードは送らない。"""
    with pytest.raises(ServiceValidationError):
        await _call(hass, SERVICE_SET_HVAC_MODE, "ac-bedroom", hvac_mode=HVACMode.DRY)

    assert fake_api.posts == []


async def test_set_fan_mode(hass: HomeAssistant, fake_api: FakeNatureApi) -> None:
    """風量はair_volumeで送る。"""
    await _call(hass, SERVICE_SET_FAN_MODE, "ac-living", fan_mode="2")

    assert fake_api.posts == [
        ("ac-living", {"operation_mode": "cool", "air_volume": "2"})
    ]
    assert _state(hass, "ac-living").attributes[ATTR_FAN_MODE] == "2"


async def test_set_swing_mode(hass: HomeAssistant, fake_api: FakeNatureApi) -> None:
    """風向はair_directionで送る。"""
    await _call(hass, SERVICE_SET_SWING_MODE, "ac-study", swing_mode="swing")

    assert fake_api.posts == [
        ("ac-study", {"operation_mode": "dry", "air_direction": "swing"})
    ]
    assert _state(hass, "ac-study").attributes[ATTR_SWING_MODE] == "swing"


@pytest.mark.parametrize(
    "status",
    [
        HTTPStatus.UNAUTHORIZED,
        HTTPStatus.TOO_MANY_REQUESTS,
        HTTPStatus.INTERNAL_SERVER_ERROR,
    ],
)
async def test_operation_error(
    hass: HomeAssistant, fake_api: FakeNatureApi, status: HTTPStatus
) -> None:
    """操作の失敗はHomeAssistantErrorとして利用者に見せ、状態は変えない。"""
    fake_api.fail(status)

    with pytest.raises(HomeAssistantError) as exc_info:
        await _call(hass, SERVICE_SET_HVAC_MODE, "ac-living", hvac_mode=HVACMode.HEAT)

    assert not isinstance(exc_info.value, ServiceValidationError)
    assert _state(hass, "ac-living").state == HVACMode.COOL


async def test_operation_invalid_response(
    hass: HomeAssistant, fake_api: FakeNatureApi, loaded_entry: MockConfigEntry
) -> None:
    """操作APIの応答が想定外の形なら成功扱いにしない。"""
    fake_api.fail(HTTPStatus.OK, text='{"code": 0}')

    with pytest.raises(HomeAssistantError):
        await _call(hass, SERVICE_SET_HVAC_MODE, "ac-living", hvac_mode=HVACMode.HEAT)

    assert _state(hass, "ac-living").state == HVACMode.COOL


async def test_dry_with_relative_range_and_empty_temperature(
    hass: HomeAssistant, fake_api: FakeNatureApi
) -> None:
    """除湿に温度範囲があっても応答のtempが空文字なら、設定温度だけをなしにする。"""
    await _call(hass, SERVICE_SET_HVAC_MODE, "ac-living", hvac_mode=HVACMode.DRY)

    state = _state(hass, "ac-living")
    assert state.state == HVACMode.DRY
    assert _features(state) & ClimateEntityFeature.TARGET_TEMPERATURE
    assert state.attributes[ATTR_TEMPERATURE] is None
    assert state.attributes[ATTR_MIN_TEMP] == -2
    assert state.attributes[ATTR_MAX_TEMP] == 2


async def test_unavailable_when_aircon_disappears(
    hass: HomeAssistant, fake_api: FakeNatureApi, freezer: FrozenDateTimeFactory
) -> None:
    """エアコンが一覧から消えたら利用不可にする。"""
    fake_api.appliances.pop(0)

    freezer.tick(timedelta(seconds=60))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert _state(hass, "ac-living").state == STATE_UNAVAILABLE


async def test_consecutive_operations_share_refresh(
    hass: HomeAssistant, fake_api: FakeNatureApi
) -> None:
    """10秒以内の連続操作では再取得をまとめ、レート制限を消費しすぎない。"""
    get_count = fake_api.get_count

    await _call(hass, SERVICE_SET_TEMPERATURE, "ac-living", temperature=27)
    await _call(hass, SERVICE_SET_TEMPERATURE, "ac-living", temperature=28)

    assert len(fake_api.posts) == 2
    assert fake_api.get_count == get_count + 2
    assert _state(hass, "ac-living").attributes[ATTR_TEMPERATURE] == 28


async def test_set_temperature_from_fahrenheit_system(
    hass: HomeAssistant, fake_api: FakeNatureApi
) -> None:
    """HAが華氏表示でも、摂氏への変換誤差で候補の温度を拒否しない。"""
    hass.config.units = US_CUSTOMARY_SYSTEM

    # 78.8°FはHAの変換で25.999999999999996°Cになる
    await _call(hass, SERVICE_SET_TEMPERATURE, "ac-living", temperature=78.8)

    assert fake_api.posts == [
        ("ac-living", {"operation_mode": "cool", "temperature": "26"})
    ]
