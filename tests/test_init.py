"""セットアップと定期更新のテスト。"""

from http import HTTPStatus

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
)

from custom_components.nature_remo.const import UPDATE_INTERVAL

from .conftest import FakeNatureApi, entity_id_of


async def test_setup_and_unload(
    hass: HomeAssistant,
    fake_api: FakeNatureApi,
    loaded_entry: MockConfigEntry,
    aioclient_mock: AiohttpClientMocker,
) -> None:
    """既存連携が作ったentryをそのまま読み込み、外せる。"""
    assert loaded_entry.state is ConfigEntryState.LOADED
    # 1回の更新で /1/devices と /1/appliances を1回ずつ取得する
    assert [str(url) for _, url, _, _ in aioclient_mock.mock_calls] == [
        "https://api.nature.global/1/devices",
        "https://api.nature.global/1/appliances",
    ]

    assert await hass.config_entries.async_unload(loaded_entry.entry_id)
    # 直前のassertでmypyが状態をLOADEDに絞り込むため、型を広げて読み直す
    state: ConfigEntryState = loaded_entry.state
    assert state is ConfigEntryState.NOT_LOADED


async def test_setup_retry_on_api_error(
    hass: HomeAssistant, fake_api: FakeNatureApi, config_entry: MockConfigEntry
) -> None:
    """初回取得に失敗したら再試行待ちにする。"""
    fake_api.fail(HTTPStatus.INTERNAL_SERVER_ERROR)
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_update_failure_marks_unavailable(
    hass: HomeAssistant,
    fake_api: FakeNatureApi,
    loaded_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """更新に失敗したらentityを利用不可にし、回復したら戻す。"""
    entity_ids = [
        entity_id_of(hass, "climate", "nature_remo_climate_ac-living"),
    ]
    fake_api.fail(HTTPStatus.TOO_MANY_REQUESTS)

    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state == "unavailable"

    fake_api.failure = None
    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    for entity_id in entity_ids:
        state = hass.states.get(entity_id)
        assert state is not None
        assert state.state != "unavailable"


async def test_update_interval(
    hass: HomeAssistant,
    fake_api: FakeNatureApi,
    loaded_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """60秒ごとに2リクエストで更新する（5分で10回、制限の30回に収まる）。"""
    assert fake_api.get_count == 2

    freezer.tick(UPDATE_INTERVAL)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert UPDATE_INTERVAL.total_seconds() == 60
    assert fake_api.get_count == 4
